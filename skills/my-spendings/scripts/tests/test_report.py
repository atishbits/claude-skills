import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import report  # noqa: E402

A = {
    "as_of": "2026-10-25", "from": "2026-04-25", "to": "2026-10-25", "rows": 10,
    "accounts": ["card-1", "savings-main"], "coverage": {"savings-main": [["2026-04-25", "2026-10-25"]]},
    "monthly": {"2026-09": {"fuel": 3000.0, "card_spend_unexpanded": 20000.0},
                "2026-10": {"fuel": 2500.0, "dining": 800.0}},
    "rates": {"income": 200000.0, "spend": 26300.0, "invest_net": 50000.0, "tax": 10000.0,
              "family": 5000.0, "own_moved_out": 0.0, "savings_rate": 0.7941, "investing_rate": 0.25},
    "recurring": [{"payee": "STREAMCO", "category": "subscriptions", "cadence": "monthly",
                   "typical": 499.0, "yearly_cost": 5988.0, "first": "2026-05-05", "last": "2026-10-05",
                   "count": 6, "active": True, "mandate": False, "account": "card-1"}],
    "fees": {"total": 590.0, "items": [{"date": "2026-09-01", "account": "card-1",
                                        "description": "ANNUAL FEE", "amount": 590.0}]},
    "anomalies": [{"kind": "tiny_debit", "payee": "ODD", "date": "2026-10-01", "account": "card-1",
                   "amount": -1.0, "description": "ODD"}],
    "mix": {"holdings_missing": True, "flows_by_type": {"fd": 50000.0}, "by_type": {}, "flags": []},
    "spend_12m": {"months_covered": 6, "annualised": True, "factor": 2.0, "by_category": {},
                  "by_account": {}, "by_holder": {"self": 1.0, "Spouse": 2.0}, "fuel_txns": []},
    "addon_spend": {"Spouse": {"2026-10": 1200.0}},
    "warnings": [], "uncategorised": [{"payee": "ZQX", "count": 2, "total": -900.0}],
    "top_payees": [{"payee": "FUELCO", "category": "fuel", "count": 4, "total": 5500.0}],
}


class TestReport(unittest.TestCase):
    def test_report_sections_in_order(self):
        md = report.render(A)
        heads = [l for l in md.splitlines() if l.startswith("## ")]
        self.assertEqual(heads, ["## Spending", "## Savings vs investing", "## Flags for review",
                                 "## Decisions", "## Terms used"])

    def test_report_calls_out_unexpanded_and_addons(self):
        md = report.render(A)
        self.assertIn("not broken down", md)
        self.assertIn("Spouse", md)
        self.assertIn("STREAMCO", md)
        self.assertIn("ZQX", md)

    def test_report_has_adviser_line_and_terms(self):
        md = report.render(A)
        self.assertIn("not advice from a licensed financial adviser", md)
        self.assertIn("**Savings rate**", md)

    def test_summary_max_15_lines(self):
        s = report.summary(A)
        self.assertLessEqual(len(s.splitlines()), 15)
        self.assertIn("79.4%", s)


if __name__ == "__main__":
    unittest.main()
