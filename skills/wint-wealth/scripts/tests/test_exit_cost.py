import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import exit_cost  # noqa: E402

CONFIG = common.load_config()
PROFILE = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
ALPHA = "INE000A07011"


def holding(**over):
    base = {"issuer": "Alpha Finance", "isin": ALPHA, "current_value": 22000.0, "invested": 20000.0,
            "principal_repaid": None, "maturity_date": "2027-12-31", "upcoming_interest": 2400.0,
            "upcoming_principal": 20000.0}
    base.update(over)
    return base


PURCHASES = [{"isin": ALPHA, "date": "2025-06-01"}, {"isin": ALPHA, "date": "2025-09-01"},
             {"isin": "INE000B07022", "date": "2024-01-01"}]


class TestEstimate(unittest.TestCase):
    def test_deduction_gain_and_both_tax_cases(self):
        out = exit_cost.estimate(holding(), PURCHASES, None, CONFIG, PROFILE, "2026-10-02")
        self.assertEqual(out["deduction"], 220.0)
        self.assertEqual(out["proceeds_estimate"], 21780.0)
        self.assertEqual(out["cost_remaining"], 20000.0)
        self.assertEqual(out["gain"], 1780.0)
        self.assertEqual(out["months_held"], 16.0)
        self.assertIsNone(out["listed"])
        self.assertEqual(out["tax_if_listed"], 222.5)     # 12.5% after 12 months
        self.assertEqual(out["tax_if_unlisted"], 534.0)   # 30% slab
        self.assertEqual(out["net_if_listed"], 21557.5)
        self.assertEqual(out["net_if_unlisted"], 21246.0)

    def test_listed_but_held_under_twelve_months_is_slab(self):
        out = exit_cost.estimate(holding(), [{"isin": ALPHA, "date": "2026-06-01"}],
                                 {"listed": True}, CONFIG, PROFILE, "2026-10-02")
        self.assertIs(out["listed"], True)
        self.assertEqual(out["tax_if_listed"], 534.0)

    def test_loss_has_no_tax(self):
        out = exit_cost.estimate(holding(current_value=20000.0), PURCHASES, None, CONFIG, PROFILE,
                                 "2026-10-02")
        self.assertEqual(out["gain"], -200.0)
        self.assertEqual(out["tax_if_listed"], 0.0)
        self.assertEqual(out["tax_if_unlisted"], 0.0)

    def test_principal_already_repaid_lowers_cost(self):
        out = exit_cost.estimate(holding(principal_repaid=5000.0, current_value=15500.0), PURCHASES,
                                 None, CONFIG, PROFILE, "2026-10-02")
        self.assertEqual(out["cost_remaining"], 15000.0)

    def test_unknown_purchase_date(self):
        out = exit_cost.estimate(holding(), [], {"listed": True}, CONFIG, PROFILE, "2026-10-02")
        self.assertIsNone(out["months_held"])
        self.assertEqual(out["tax_if_listed"], 534.0)  # cannot show long-term, so slab

    def test_result_is_conditional_on_a_buyer(self):
        out = exit_cost.estimate(holding(), PURCHASES, None, CONFIG, PROFILE, "2026-10-02")
        self.assertIn("buyer", out["conditional"])
        self.assertEqual(out["hold_to_maturity"], {"maturity_date": "2027-12-31",
                                                   "upcoming_interest": 2400.0,
                                                   "upcoming_principal": 20000.0})



class TestConfigAge(unittest.TestCase):
    def test_old_config_entries_are_reported_with_the_estimate(self):
        import copy
        fresh = exit_cost.estimate(holding(), PURCHASES, None, CONFIG, PROFILE, "2026-10-02")
        self.assertEqual(fresh["config_warnings"], [])
        old = copy.deepcopy(CONFIG)
        old["portal"]["early_exit_deduction_pct"]["as_of"] = "2024-01-01"
        stale = exit_cost.estimate(holding(), PURCHASES, None, old, PROFILE, "2026-10-02")
        self.assertTrue(any("early_exit_deduction_pct" in w for w in stale["config_warnings"]))



class TestLots(unittest.TestCase):
    def test_each_lot_is_taxed_on_its_own_holding_period(self):
        lots = [{"isin": ALPHA, "date": "2025-06-01", "units": 1.0},
                {"isin": ALPHA, "date": "2026-06-01", "units": 1.0}]
        out = exit_cost.estimate(holding(units=2.0), lots, {"listed": True}, CONFIG, PROFILE,
                                 "2026-10-02")
        # gain 1780 split equally: 890 at 12.5% (held 16 months) + 890 at 30% (held 4 months)
        self.assertEqual(out["tax_if_listed"], 378.25)
        self.assertEqual(out["tax_if_unlisted"], 534.0)
        self.assertEqual([(l["date"], l["units"], l["long_term_if_listed"]) for l in out["lots"]],
                         [("2025-06-01", 1.0, True), ("2026-06-01", 1.0, False)])

    def test_units_already_sold_come_off_the_earliest_lots_first(self):
        lots = [{"isin": ALPHA, "date": "2025-06-01", "units": 1.0},
                {"isin": ALPHA, "date": "2026-06-01", "units": 1.0}]
        out = exit_cost.estimate(holding(units=1.0), lots, {"listed": True}, CONFIG, PROFILE,
                                 "2026-10-02")
        self.assertEqual([l["date"] for l in out["lots"]], ["2026-06-01"])
        self.assertEqual(out["tax_if_listed"], 534.0)

    def test_effective_tax_rate_is_used_for_slab_taxed_gains(self):
        out = exit_cost.estimate(holding(), PURCHASES, None, CONFIG,
                                 dict(PROFILE, effective_tax_rate_pct=31.2), "2026-10-02")
        self.assertEqual(out["tax_if_unlisted"], 555.36)


if __name__ == "__main__":
    unittest.main()
