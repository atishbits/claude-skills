import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyse  # noqa: E402
import common  # noqa: E402
import ingest  # noqa: E402

SKILL = os.path.join(os.path.dirname(__file__), "..", "..")
PROFILE = common.load_json(os.path.join(SKILL, "profile-template.json"))


def t(date, amount, category, bucket=None, payee="SHOP", desc="", account="card-1", holder=""):
    return {"date": date, "amount": str(amount), "category": category,
            "bucket": bucket or ("income" if category in ("income", "interest") else "spend"),
            "payee": payee, "description": desc or payee, "account": account, "holder": holder}


class TestHelpers(unittest.TestCase):
    def test_monthly_totals(self):
        m = analyse.monthly([t("2026-04-02", -100, "fuel"), t("2026-04-09", -50, "fuel"),
                             t("2026-05-01", -30, "dining"), t("2026-05-02", 10, "refund"),
                             t("2026-05-01", 999, "income")])
        self.assertEqual(m, {"2026-04": {"fuel": 150.0}, "2026-05": {"dining": 30.0, "refund": -10.0}})

    def test_rates_exclude_transfers_and_card_payments(self):
        r = analyse.rates([t("2026-04-01", 100000, "income"),
                           t("2026-04-02", -30000, "shopping"),
                           t("2026-04-03", -20000, "investment:fd", "invest"),
                           t("2026-04-03", 5000, "investment:fd", "invest"),
                           t("2026-04-04", -10000, "tax", "tax"),
                           t("2026-04-04", -5000, "family_transfer", "family"),
                           t("2026-04-05", -40000, "card_payment", "excluded"),
                           t("2026-04-05", -7000, "own_transfer", "own_moved_out")])
        self.assertEqual((r["income"], r["spend"], r["invest_net"], r["tax"], r["family"],
                          r["own_moved_out"]), (100000.0, 30000.0, 15000.0, 10000.0, 5000.0, 7000.0))
        self.assertAlmostEqual(r["savings_rate"], 0.55)
        self.assertAlmostEqual(r["investing_rate"], 0.15)

    def test_recurring_monthly_and_mandate(self):
        rows = [t(d, -499, "subscriptions", payee="STREAMCO") for d in
                ["2026-05-05", "2026-06-05", "2026-07-06", "2026-08-05"]]
        rows += [t("2026-08-10", -1200, "insurance", payee="LIFECO", desc="NACH/LIFECO/premium")]
        rows += [t("2026-06-01", -80, "dining", payee="CAFE"), t("2026-07-20", -300, "dining", payee="CAFE"),
                 t("2026-08-02", -90, "dining", payee="CAFE")]
        r = {x["payee"]: x for x in analyse.recurring(rows, "2026-08-20")}
        self.assertEqual(set(r), {"STREAMCO", "LIFECO"})
        self.assertEqual(r["STREAMCO"]["cadence"], "monthly")
        self.assertAlmostEqual(r["STREAMCO"]["yearly_cost"], 499 * 12)
        self.assertTrue(r["STREAMCO"]["active"])
        self.assertEqual(r["LIFECO"]["cadence"], "mandate")

    def test_recurring_inactive_when_stopped(self):
        rows = [t(d, -499, "subscriptions", payee="STREAMCO") for d in
                ["2026-01-05", "2026-02-05", "2026-03-05"]]
        self.assertFalse(analyse.recurring(rows, "2026-08-20")[0]["active"])

    def test_fees_total(self):
        f = analyse.fees([t("2026-04-01", -590, "fees_charges", desc="ANNUAL FEE"),
                          t("2026-04-02", -18, "fees_charges", desc="GST"),
                          t("2026-04-02", -100, "fuel")])
        self.assertEqual(f["total"], 608.0)
        self.assertEqual(len(f["items"]), 2)

    def test_anomaly_kinds(self):
        hist = [t("2026-03-0%d" % d, -1000, "groceries", payee="GROCER") for d in (1, 2, 3)]
        rows = [
            t("2026-04-01", -250, "dining", payee="CAFE"), t("2026-04-01", -250, "dining", payee="CAFE"),
            t("2026-04-02", -1, "uncategorised", payee="ODD"),
            t("2026-04-03", -30000, "uncategorised", payee="NEWGUY"),
            t("2026-04-04", -3500, "groceries", payee="GROCER"),
            t("2026-04-04", -2500, "groceries", payee="GROCER"),
            t("2026-04-05", -800, "shopping", payee="WEBSHOP", desc="WEBSHOP USD 9.99"),
        ]
        a = analyse.anomalies(rows, PROFILE, hist + rows)
        kinds = sorted((x["kind"], x["payee"]) for x in a)
        self.assertEqual(kinds, [("duplicate", "CAFE"), ("foreign", "WEBSHOP"), ("new_payee_large", "NEWGUY"),
                                 ("outlier", "GROCER"), ("tiny_debit", "ODD")])

    def test_rates_report_other_money_in(self):
        r = analyse.rates([t("2026-04-01", 100000, "income"),
                           t("2026-04-02", 7000, "uncategorised", "other_in")])
        self.assertEqual((r["income"], r["other_in"], r["spend"]), (100000.0, 7000.0, 0.0))

    def test_anomalies_ignore_non_spend_and_card_bills(self):
        hist = [t("2026-03-0%d" % d, -1000, "investment:stocks", "invest", payee="BROKER") for d in (1, 2, 3)]
        hist += [t("2026-03-0%d" % d, -1000, "card_spend_unexpanded", payee="BILLAPP") for d in (1, 2, 3)]
        rows = [t("2026-04-01", -10000, "investment:stocks", "invest", payee="BROKER"),
                t("2026-04-01", -10000, "investment:stocks", "invest", payee="BROKER"),
                t("2026-04-02", -35000, "card_spend_unexpanded", payee="BILLAPP"),
                t("2026-04-02", -35000, "card_spend_unexpanded", payee="BILLAPP"),
                t("2026-04-03", -49000, "tax", "tax", payee="TAXDEPT"),
                t("2026-04-03", -49000, "tax", "tax", payee="TAXDEPT")]
        self.assertEqual(analyse.anomalies(rows, PROFILE, hist + rows), [])

    def test_mix_flags_concentration(self):
        h = [{"asset_type": "fd", "name": "FD A", "value_inr": "600000"},
             {"asset_type": "stocks", "name": "Stock X", "value_inr": "300000"},
             {"asset_type": "mf", "name": "Fund Y", "value_inr": "100000"}]
        m = analyse.mix(h, [t("2026-04-01", -1000, "investment:mf", "invest")], PROFILE)
        self.assertEqual(m["by_type"]["fd"]["share_pct"], 60.0)
        self.assertIn({"kind": "type_over_cap", "name": "fd", "share_pct": 60.0}, m["flags"])
        self.assertIn({"kind": "holding_over_cap", "name": "FD A", "share_pct": 60.0}, m["flags"])
        self.assertEqual(m["flows_by_type"], {"mf": 1000.0})
        self.assertTrue(analyse.mix([], [], PROFILE)["holdings_missing"])

    def test_spend_12m_annualises_short_history(self):
        rows = [t("2026-05-10", -1000, "fuel", payee="FUELCO"), t("2026-07-10", -2000, "fuel", payee="FUELCO"),
                t("2026-07-11", -500, "dining")]
        s = analyse.spend_12m(rows, "2026-10-25")
        self.assertTrue(s["annualised"])
        self.assertEqual(s["months_covered"], 6)
        self.assertEqual(s["by_category"]["fuel"], 6000.0)
        self.assertEqual(len(s["fuel_txns"]), 2)
        self.assertEqual(s["factor"], 2.0)

    def test_addon_spend_counted_and_marked(self):
        rows = [t("2026-04-01", -100, "fuel"), t("2026-04-02", -300, "shopping", holder="Spouse")]
        self.assertEqual(analyse.rates(rows)["spend"], 400.0)
        self.assertEqual(analyse.addon_spend(rows), {"Spouse": {"2026-04": 300.0}})


class TestRun(unittest.TestCase):
    def test_run_writes_json_with_all_sections(self):
        root = tempfile.mkdtemp()
        try:
            p = common.paths(root)
            os.makedirs(p["skill_data"])
            shutil.copy(os.path.join(SKILL, "accounts-template.json"), p["accounts"])
            shutil.copy(os.path.join(SKILL, "profile-template.json"), p["profile"])
            ingest.merge(p["ledger"], [
                {"date": "2026-04-01", "account": "savings-main", "amount": 100000, "description": "SALARY EXAMPLE CORP"},
                {"date": "2026-04-02", "account": "savings-main", "amount": -2000, "description": "UPI/FUELCO/PETROL"},
                {"date": "2026-04-03", "account": "savings-main", "amount": -20000, "description": "UPI/CARDPAY/x"},
            ], "x.csv")
            a = analyse.run(root, "2026-04-30")
            for k in ["as_of", "from", "to", "accounts", "monthly", "rates", "recurring", "fees",
                      "anomalies", "mix", "spend_12m", "addon_spend", "warnings", "uncategorised",
                      "top_payees", "coverage"]:
                self.assertIn(k, a)
            self.assertEqual(a["rates"]["spend"], 22000.0)
            self.assertTrue(os.path.exists(os.path.join(p["skill_data"], "analysis-2026-04-30.json")))
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
