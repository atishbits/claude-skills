import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import costs  # noqa: E402


class TestCosts(unittest.TestCase):
    def test_weighted_er(self):
        meta = {"A": {"expense_ratio_pct": 0.59, "er_basis": "post_2026_04"},
                "B": {"expense_ratio_pct": 0.17, "er_basis": "post_2026_04"}}
        r = costs.weighted_er([{"isin": "A", "value": 100000}, {"isin": "B", "value": 100000}], meta)
        self.assertAlmostEqual(r["weighted_er_pct"], 0.38, places=3)
        self.assertAlmostEqual(r["annual_cost_inr"], 760.0, places=2)
        self.assertFalse(r["mixed_basis"])
        self.assertAlmostEqual(r["by_fund"][0]["share_of_cost_pct"], 77.6, places=1)

    def test_missing_er_listed_not_zeroed(self):
        r = costs.weighted_er([{"isin": "A", "value": 100}, {"isin": "C", "value": 100}],
                              {"A": {"expense_ratio_pct": 0.5}})
        self.assertEqual(r["missing_er"], ["C"])
        self.assertAlmostEqual(r["weighted_er_pct"], 0.5)  # over funds with a known ER

    def test_mixed_basis_flagged(self):
        meta = {"A": {"expense_ratio_pct": 0.5, "er_basis": "pre_2026_04"},
                "B": {"expense_ratio_pct": 0.2, "er_basis": "post_2026_04"}}
        r = costs.weighted_er([{"isin": "A", "value": 1}, {"isin": "B", "value": 1}], meta)
        self.assertTrue(r["mixed_basis"])

    def test_switch_breakeven_closed_form(self):
        v, c = 100000, 2000
        expect = math.log(v / (v - c)) / math.log((1.10 - 0.0010) / (1.10 - 0.0059))
        got = costs.switch_breakeven(v, 1000, 1000, 10, 0.59, 0.10)
        self.assertAlmostEqual(got, expect, delta=0.1)
        self.assertEqual(costs.switch_breakeven(v, 0, 0, 10, 0.59, 0.10), 0)
        self.assertIsNone(costs.switch_breakeven(v, 0, 1000, 10, 0.10, 0.59))

    def test_exit_load_only_young_lots(self):
        lots = [{"date": "2025-06-01", "units": 10, "cost_per_unit": 10},
                {"date": "2026-10-01", "units": 5, "cost_per_unit": 10}]
        self.assertAlmostEqual(costs.exit_load_inr(lots, "2026-10-25", 1.0, 365, 20.0), 1.0)
        self.assertEqual(costs.exit_load_inr(lots, "2026-10-25", 0, 365, 20.0), 0)


if __name__ == "__main__":
    unittest.main()
