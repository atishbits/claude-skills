import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import tax  # noqa: E402

RULES = common.load_tax_rules()
PERSON = {"slab_pct": 30.0, "surcharge_multiplier": 1.15, "cess": 1.04,
          "effective_slab_pct": 35.88, "ltcg_multiplier": 1.196}
K = ("p", "f1", "INF000X01AA1")


def tx(date, type_, amount, units, isin="INF000X01AA1"):
    return {"date": date, "source": "p", "folio_ref": "f1", "isin": isin, "type": type_,
            "amount": amount, "units": units}


class TestProfileAndHurdle(unittest.TestCase):
    def test_import_tax_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "tp.json")
            with open(p, "w") as f:
                json.dump({"people": {"me": {"other_tax_pct": 0.30, "surcharge_multiplier": 1.15}}}, f)
            r = tax.import_tax_profile(p, "me", cess=1.04)
            self.assertAlmostEqual(r["effective_slab_pct"], 35.88, places=2)
            self.assertAlmostEqual(r["ltcg_multiplier"], 1.196, places=3)
            with open(p, "w") as f:
                json.dump({"people": {"me": {"fd_tax_pct": 0.30, "surcharge_multiplier": 1.25}}}, f)
            r = tax.import_tax_profile(p, "me", cess=1.04)
            self.assertAlmostEqual(r["ltcg_multiplier"], 1.196, places=3)  # surcharge capped at 15%
            with self.assertRaises(ValueError):
                tax.import_tax_profile(p, "someone_else")

    def test_fd_hurdle_user_like(self):
        self.assertAlmostEqual(tax.fd_hurdle(6.5, 35.88), 4.168, places=2)

    def test_required_pretax_equity_5y(self):
        r = tax.required_pretax(4.168, 5, "equity", RULES, PERSON)
        self.assertAlmostEqual(r, 4.84, places=1)

    def test_required_pretax_debt_equals_fd_rate(self):
        # slab-taxed at exit: needs about the FD rate (deferral helps a little)
        r = tax.required_pretax(4.168, 3, "specified_debt", RULES, PERSON)
        self.assertTrue(6.0 < r < 6.5, r)


class TestLots(unittest.TestCase):
    def test_fifo_partial_sell(self):
        lots = tax.lots([tx("2024-01-01", "buy", 1000, 10), tx("2025-01-01", "buy", 1200, 10),
                         tx("2025-06-01", "sell", 2100, 15)])
        self.assertEqual(len(lots[K]), 1)
        self.assertAlmostEqual(lots[K][0]["units"], 5.0)
        self.assertAlmostEqual(lots[K][0]["cost_per_unit"], 120.0)
        self.assertEqual(lots[K][0]["date"], "2025-01-01")

    def test_same_day_buy_counted_before_sell(self):
        lots = tax.lots([tx("2025-06-01", "sell", 50, 5), tx("2025-06-01", "buy", 100, 10)])
        self.assertAlmostEqual(lots[K][0]["units"], 5.0)

    def test_oversell_raises(self):
        with self.assertRaises(ValueError):
            tax.lots([tx("2024-01-01", "buy", 1000, 10), tx("2025-06-01", "sell", 2100, 11)])

    def test_switch_in_and_reinvest_create_lots(self):
        lots = tax.lots([tx("2024-01-01", "switch_in", 1000, 10),
                         tx("2024-02-01", "dividend_reinvest", 50, 0.5)])
        self.assertEqual(len(lots[K]), 2)

    def test_same_day_identical_purchases_both_lots(self):
        lots = tax.lots([tx("2026-02-16", "buy", 100, 1), tx("2026-02-16", "buy", 100, 1)])
        self.assertAlmostEqual(sum(l["units"] for l in lots[K]), 2.0)


class TestUnrealised(unittest.TestCase):
    def run_u(self, rows, nav, as_of, cls="equity", gf=None):
        return tax.unrealised(tax.lots(rows), {"INF000X01AA1": nav}, as_of, RULES,
                              {"INF000X01AA1": cls}, PERSON, gf)

    def test_equity_lt_boundary(self):
        u = self.run_u([tx("2025-10-25", "buy", 100, 1)], 150, "2026-10-25")
        self.assertEqual((u["by_holding"][K]["st_gain"], u["by_holding"][K]["lt_gain"]), (50, 0))
        u = self.run_u([tx("2025-10-24", "buy", 100, 1)], 150, "2026-10-25")
        self.assertEqual((u["by_holding"][K]["st_gain"], u["by_holding"][K]["lt_gain"]), (0, 50))

    def test_hybrid_needs_24_months(self):
        u = self.run_u([tx("2025-01-01", "buy", 100, 1)], 150, "2026-10-25", "hybrid_gold_intl")
        self.assertEqual(u["by_holding"][K]["st_gain"], 50)

    def test_grandfathering(self):
        u = self.run_u([tx("2017-06-01", "buy", 50, 1)], 100, "2026-10-25",
                       gf={"INF000X01AA1": 80})
        self.assertAlmostEqual(u["by_holding"][K]["lt_gain"], 20)

    def test_totals_exemption_and_loss_setoff(self):
        rows = [tx("2020-01-01", "buy", 100000, 1000),               # LT gain 200000 at 300
                tx("2026-09-01", "buy", 40000, 100, isin="INF000X01BB2")]  # ST loss 10000 at 300
        lots = tax.lots(rows)
        u = tax.unrealised(lots, {"INF000X01AA1": 300, "INF000X01BB2": 300}, "2026-10-25", RULES,
                           {"INF000X01AA1": "equity", "INF000X01BB2": "equity"}, PERSON)
        t = u["totals"]
        self.assertEqual(t["equity_st_net"], 0)
        self.assertEqual(t["equity_lt_net"], 190000)
        self.assertAlmostEqual(t["equity_lt_taxable_after_exemption"], 65000)
        self.assertAlmostEqual(t["tax_if_all_sold"], round(65000 * 0.125 * 1.196, 2))

    def test_holding_tax(self):
        h = {"tax_class": "equity", "st_gain": 100.0, "lt_gain": 1000.0}
        self.assertAlmostEqual(tax.holding_tax(h, RULES, PERSON),
                               round((100 * 0.20 + 1000 * 0.125) * 1.196, 2))
        self.assertEqual(tax.holding_tax({"tax_class": "equity", "st_gain": -5, "lt_gain": 0},
                                         RULES, PERSON), 0)

    def test_st_loss_only_absorbs_positive_lt_gain(self):
        rows = [tx("2020-01-01", "buy", 1000, 10),                       # LT loss 200 at 80
                tx("2026-09-01", "buy", 1000, 10, isin="INF000X01BB2")]   # ST loss 200 at 80
        u = tax.unrealised(tax.lots(rows), {"INF000X01AA1": 80, "INF000X01BB2": 80}, "2026-10-25",
                           RULES, {"INF000X01AA1": "equity", "INF000X01BB2": "equity"}, PERSON)
        self.assertEqual(u["totals"]["equity_st_net"], -200)
        self.assertEqual(u["totals"]["equity_lt_net"], -200)
        rows = [tx("2020-01-01", "buy", 1000, 10),                       # LT gain 50 at 105
                tx("2026-09-01", "buy", 1000, 10, isin="INF000X01BB2")]   # ST loss 200 at 80
        u = tax.unrealised(tax.lots(rows), {"INF000X01AA1": 105, "INF000X01BB2": 80}, "2026-10-25",
                           RULES, {"INF000X01AA1": "equity", "INF000X01BB2": "equity"}, PERSON)
        self.assertEqual(u["totals"]["equity_st_net"], -150)
        self.assertEqual(u["totals"]["equity_lt_net"], 0)

    def test_losses_never_make_tax_negative(self):
        rows = [tx("2026-09-01", "buy", 1000, 10)]
        u = tax.unrealised(tax.lots(rows), {"INF000X01AA1": 80}, "2026-10-25", RULES,
                           {"INF000X01AA1": "equity"}, PERSON)
        self.assertEqual(u["totals"]["tax_if_all_sold"], 0)

    def test_pre_april_2023_debt_gets_long_term_rate(self):
        old = self.run_u([tx("2023-03-31", "buy", 100, 1)], 150, "2026-10-25", "specified_debt")
        new = self.run_u([tx("2023-04-01", "buy", 100, 1)], 150, "2026-10-25", "specified_debt")
        self.assertEqual(old["by_holding"][K]["lt_gain"], 50)
        self.assertAlmostEqual(old["totals"]["tax_if_all_sold"], round(50 * 0.125 * 1.196, 2))
        self.assertEqual(new["by_holding"][K]["st_gain"], 50)
        self.assertAlmostEqual(new["totals"]["tax_if_all_sold"], round(50 * 0.3588, 2))

    def test_debt_taxed_at_slab(self):
        u = self.run_u([tx("2024-01-01", "buy", 100, 1)], 120, "2026-10-25", "specified_debt")
        self.assertAlmostEqual(u["totals"]["tax_if_all_sold"], round(20 * 0.3588, 2))


if __name__ == "__main__":
    unittest.main()
