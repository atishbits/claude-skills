import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import ingest  # noqa: E402
import positions  # noqa: E402
from helpers import ALPHA, BETA, sample_report  # noqa: E402


def snapshot(as_of="2026-10-02"):
    return ingest.build_snapshot(sample_report(), common.load_config(), as_of, "abc")


class TestPositions(unittest.TestCase):
    def test_one_row_per_holding_ordered_by_last_payment(self):
        rows = positions.positions(snapshot())["positions"]
        self.assertEqual([r["isin"] for r in rows], [BETA, ALPHA])

    def test_received_and_to_come_are_summed_per_bond(self):
        alpha = positions.positions(snapshot())["positions"][1]
        self.assertEqual(alpha["invested"], 20000.0)
        self.assertEqual(alpha["bought"], "2026-01-01")
        self.assertEqual(alpha["received"], {"principal": 0.0, "interest_net": 360.0,
                                             "tds": 40.0, "total": 360.0})
        self.assertEqual(alpha["to_come"], {"principal": 0.0, "interest_net": 360.0,
                                            "tds": 40.0, "total": 360.0})
        self.assertEqual(alpha["next_payment"], {"date": "2026-10-15", "amount": 180.0})
        self.assertEqual(alpha["last_payment_date"], "2026-11-15")

    def test_principal_dates_and_net(self):
        beta = positions.positions(snapshot())["positions"][0]
        self.assertEqual(beta["received"]["total"], 0.0)
        self.assertEqual(beta["principal_dates"], [{"date": "2026-10-30", "principal": 5000.0}])
        self.assertEqual(beta["net_if_all_paid"], -4750.0)

    def test_scheduled_payment_before_the_report_date_is_past_due(self):
        out = positions.positions(snapshot("2026-10-20"))
        alpha = out["positions"][1]
        self.assertEqual(alpha["past_due"], 180.0)
        self.assertEqual(alpha["next_payment"], {"date": "2026-11-15", "amount": 180.0})
        self.assertEqual(alpha["to_come"]["total"], 360.0)
        self.assertEqual(out["totals"]["past_due"], 180.0)

    def test_xirr_of_one_year_at_ten_percent(self):
        self.assertEqual(positions.xirr([("2026-01-01", -1000.0), ("2027-01-01", 1100.0)]), 10.0)

    def test_xirr_counts_interim_payments_by_date(self):
        rate = positions.xirr([("2026-01-01", -1000.0), ("2026-07-02", 50.0),
                               ("2027-01-01", 1050.0)])
        self.assertEqual(rate, 10.25)

    def test_xirr_is_none_without_an_outlay_or_a_return(self):
        self.assertIsNone(positions.xirr([("2026-01-01", -1000.0)]))
        self.assertIsNone(positions.xirr([("2026-01-01", 1000.0), ("2027-01-01", 5.0)]))
        self.assertIsNone(positions.xirr([]))

    def test_return_adds_tds_back_and_applies_the_tax_rate(self):
        snap = snapshot()
        snap["purchases"] = [{"isin": BETA, "date": "2026-10-30", "invested": 10000.0}]
        snap["expected_cashflows"] = [{"isin": BETA, "issuer": "Beta Capital", "date": "2027-10-30",
                                       "amount": 10900.0, "principal": 10000.0,
                                       "interest_net": 900.0, "tds": 100.0}]
        beta = positions.positions(snap, tax_rate_pct=30.0)["positions"][0]
        self.assertEqual(beta["return_pct"], 10.0)
        self.assertEqual(beta["post_tax_return_pct"], 7.0)
        self.assertIsNone(positions.positions(snap)["positions"][0]["post_tax_return_pct"])

    def test_rating_comes_from_recorded_facts(self):
        facts = [{"isin": ALPHA, "rating": "A-", "rating_scope": "issuer", "agency": "CARE",
                  "outlook": "Negative"}]
        rows = positions.positions(snapshot(), facts)["positions"]
        self.assertEqual((rows[1]["rating"], rows[1]["rating_scope"], rows[1]["outlook"]),
                         ("A-", "issuer", "Negative"))
        self.assertIsNone(rows[0]["rating"])

    def test_table_has_a_row_per_bond_and_a_total(self):
        facts = [{"isin": ALPHA, "rating": "A-", "rating_scope": "issuer", "outlook": "Negative"}]
        result = positions.positions(snapshot(), facts, 30.0)
        rows = positions.table_rows(result)
        self.assertEqual([r[0] for r in rows], ["Beta Capital", "Alpha Finance", "Total"])
        self.assertTrue(all(len(r) == len(positions.HEADER) for r in rows))
        self.assertEqual(rows[0][2], "unrated")
        self.assertEqual(rows[1][2:4], ["A- (issuer)", "Negative"])
        self.assertEqual(rows[0][13], "5000.0 on 2026-10-30")
        self.assertEqual(rows[1][13], "none scheduled")
        self.assertEqual(rows[2][5], 30000.0)

    def test_many_principal_payments_are_summarised(self):
        dates = [{"date": f"2027-0{m}-21", "principal": 100.0} for m in range(1, 6)]
        self.assertEqual(positions._principal_text(dates), "5 payments, 2027-01-21 to 2027-05-21")

    def test_markdown_states_both_bases(self):
        text = positions.render_markdown(positions.positions(snapshot(), tax_rate_pct=30.0))
        self.assertIn("| Beta Capital |", text)
        self.assertIn("TDS is tax already paid", text)
        self.assertIn("x (1 - 30.0%)", text)

    def test_totals_add_the_rows(self):
        totals = positions.positions(snapshot())["totals"]
        self.assertEqual(totals["invested"], 30000.0)
        self.assertEqual(totals["received"]["total"], 360.0)
        self.assertEqual(totals["to_come"], {"principal": 5000.0, "interest_net": 610.0,
                                             "tds": 40.0, "total": 5610.0})


if __name__ == "__main__":
    unittest.main()
