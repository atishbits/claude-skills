import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import entry_plan  # noqa: E402

TODAY = date(2026, 10, 5)
WINDOW = (date(2026, 10, 15), date(2026, 11, 14))
# Invented numbers: price 100, well off a 60-day high of 120, under a 200 DMA of 110.
FALLING = {"dma200": 110.0, "dma200_reliable": True, "dma50": 108.0,
           "recent_high_60d": 120.0, "recent_low_60d": 95.0, "close_low_1y": 90.0}
STEADY = {"dma200": 90.0, "dma200_reliable": True, "recent_high_60d": 102.0,
          "recent_low_60d": 92.0, "close_low_1y": 80.0}


class TestTrend(unittest.TestCase):
    def test_below_dma_and_off_high_is_falling(self):
        tr = entry_plan.trend(100.0, FALLING)
        self.assertTrue(tr["falling"])
        self.assertAlmostEqual(tr["off_high_pct"], 16.67, places=2)

    def test_above_dma_is_not_falling(self):
        self.assertFalse(entry_plan.trend(100.0, STEADY)["falling"])

    def test_below_dma_but_near_high_is_not_falling(self):
        t = dict(FALLING, recent_high_60d=104.0)
        self.assertFalse(entry_plan.trend(100.0, t)["falling"])

    def test_uses_50dma_when_200_unreliable(self):
        t = dict(FALLING, dma200_reliable=False, dma200=50.0)
        tr = entry_plan.trend(100.0, t)
        self.assertEqual(tr["dma_label"], "50 DMA")
        self.assertTrue(tr["falling"])

    def test_missing_technicals_is_not_falling(self):
        self.assertFalse(entry_plan.trend(100.0, {})["falling"])
        self.assertFalse(entry_plan.trend(100.0, None)["falling"])


class TestLowerLevel(unittest.TestCase):
    def test_prefers_60_day_low_when_far_enough(self):
        self.assertEqual(entry_plan.lower_level(100.0, FALLING), ("60-day low", 95.0))

    def test_falls_through_to_52_week_low(self):
        t = dict(FALLING, recent_low_60d=98.5)
        self.assertEqual(entry_plan.lower_level(100.0, t), ("52-week low", 90.0))

    def test_none_when_price_sits_on_both(self):
        t = dict(FALLING, recent_low_60d=98.5, close_low_1y=98.5)
        self.assertIsNone(entry_plan.lower_level(100.0, t))


class TestPlan(unittest.TestCase):
    def test_falling_stock_gets_three_tranches_that_sum_to_budget(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY)
        self.assertTrue(p["staged"])
        self.assertEqual(len(p["tranches"]), 3)
        self.assertEqual(p["tranches"][0]["shares"], 100)
        self.assertAlmostEqual(sum(t["amount"] for t in p["tranches"]), 30000.0)

    def test_second_tranche_names_the_level_and_a_fallback_before_results(self):
        t2 = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY)["tranches"][1]
        self.assertIn("₹95.00 (60-day low)", t2["when"])
        # 14 days out would be 19 Oct, past the window's start: capped to the day before it.
        self.assertIn("2026-10-14", t2["when"])
        self.assertEqual(t2["shares"], 105)

    def test_fallback_is_14_days_when_results_are_far(self):
        far = (date(2027, 1, 15), date(2027, 2, 14))
        t2 = entry_plan.plan(100.0, 30000.0, FALLING, far, TODAY)["tranches"][1]
        self.assertIn("2026-10-19", t2["when"])

    def test_no_real_level_makes_second_tranche_date_only(self):
        t = dict(FALLING, recent_low_60d=98.5, close_low_1y=98.5)
        t2 = entry_plan.plan(100.0, 30000.0, t, WINDOW, TODAY)["tranches"][1]
        self.assertTrue(t2["when"].startswith("on 2026-10-14"))
        self.assertEqual(t2["at_price"], 100.0)

    def test_last_tranche_waits_for_the_result_and_can_be_cancelled(self):
        t3 = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY)["tranches"][2]
        self.assertIn("after the next result", t3["when"])
        self.assertIn("cancel", t3["when"])
        self.assertIn("2026-10-15 to 2026-11-14", t3["when"])
        self.assertIsNone(t3["shares"])

    def test_unknown_results_date_says_so(self):
        t3 = entry_plan.plan(100.0, 30000.0, FALLING, None, TODAY)["tranches"][2]
        self.assertIn("date unknown", t3["when"])

    def test_steady_stock_is_a_single_purchase(self):
        p = entry_plan.plan(100.0, 30000.0, STEADY, WINDOW, TODAY)
        self.assertFalse(p["staged"])
        self.assertEqual(len(p["tranches"]), 1)
        self.assertEqual(p["tranches"][0]["shares"], 300)

    def test_budget_for_two_shares_skips_the_level_tranche(self):
        p = entry_plan.plan(100.0, 250.0, FALLING, WINDOW, TODAY)
        self.assertTrue(p["staged"])
        self.assertEqual(len(p["tranches"]), 2)
        self.assertEqual(p["tranches"][0]["shares"], 1)
        self.assertIn("after the next result", p["tranches"][1]["when"])
        self.assertAlmostEqual(sum(t["amount"] for t in p["tranches"]), 250.0)

    def test_budget_for_one_share_is_not_staged(self):
        p = entry_plan.plan(100.0, 150.0, FALLING, WINDOW, TODAY)
        self.assertFalse(p["staged"])
        self.assertEqual(p["tranches"][0]["shares"], 1)

    def test_budget_below_one_share_buys_nothing(self):
        p = entry_plan.plan(100.0, 50.0, FALLING, WINDOW, TODAY)
        self.assertEqual(p["tranches"], [])
        self.assertIn("below one share", p["note"])


class TestSpentAgainstTheBudget(unittest.TestCase):
    def test_spend_fills_tranches_in_order(self):
        # Budget 30,000 in three slices of 10,000; 12,000 already in.
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY, spent=12000.0)
        t1, t2, t3 = p["tranches"]
        self.assertTrue(t1["done"])
        self.assertEqual(t1["amount"], 0)
        self.assertAlmostEqual(t2["amount"], 8000.0)
        self.assertAlmostEqual(t3["amount"], 10000.0)
        self.assertAlmostEqual(p["remaining"], 18000.0)
        self.assertAlmostEqual(sum(t["amount"] for t in p["tranches"]), 18000.0)

    def test_partial_first_tranche_buys_the_rest_now(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY, spent=4000.0)
        self.assertFalse(p["tranches"][0]["done"])
        self.assertEqual(p["tranches"][0]["shares"], 60)

    def test_only_the_result_tranche_left(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY, spent=20000.0)
        self.assertEqual([t["done"] for t in p["tranches"]], [True, True, False])
        self.assertAlmostEqual(p["tranches"][2]["amount"], 10000.0)

    def test_budget_used_up(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY, spent=29950.0)
        self.assertEqual(p["tranches"], [])
        self.assertIn("Budget used", p["note"])

    def test_steady_stock_places_what_is_left_at_once(self):
        p = entry_plan.plan(100.0, 30000.0, STEADY, WINDOW, TODAY, spent=12000.0)
        self.assertEqual(p["tranches"][0]["shares"], 180)

    def test_fallback_counts_from_the_day_the_budget_was_set(self):
        far = (date(2027, 1, 15), date(2027, 2, 14))
        p = entry_plan.plan(100.0, 30000.0, FALLING, far, TODAY, anchor=date(2026, 9, 1))
        self.assertIn("2026-09-15", p["tranches"][1]["when"])
        self.assertIn("due now", p["tranches"][1]["when"])

    def test_render_shows_what_is_in_and_what_is_done(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY, spent=12000.0)
        out = entry_plan.render("NEWCO", 100.0, 30000.0, p)
        self.assertIn("Already in: ₹12,000; left to place: ₹18,000", out)
        self.assertIn("1. Now: done, covered by what is already in", out)


class TestSavedBudgets(unittest.TestCase):
    def test_round_trip_and_spend_since(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "entry-budgets.json")
            self.assertEqual(entry_plan.load_budgets(path), {})
            entry_plan.save_budget("newco", 30000.0, 5000.0, 0.0, TODAY, path)
            rec = entry_plan.load_budgets(path)["NEWCO"]
            self.assertEqual(rec, {"budget": 30000.0, "set_on": "2026-10-05", "baseline_invested": 5000.0})
            # Nothing bought since; then 7,000 more goes in.
            self.assertEqual(entry_plan.spent_against(rec, 5000.0), 0.0)
            self.assertEqual(entry_plan.spent_against(rec, 12000.0), 7000.0)

    def test_spent_so_far_lowers_the_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "entry-budgets.json")
            rec = entry_plan.save_budget("NEWCO", 50000.0, 20000.0, 20000.0, TODAY, path)
            self.assertEqual(rec["baseline_invested"], 0.0)
            self.assertEqual(entry_plan.spent_against(rec, 20000.0), 20000.0)

    def test_saving_one_keeps_the_others(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "entry-budgets.json")
            entry_plan.save_budget("AAA", 1000.0, 0.0, 0.0, TODAY, path)
            entry_plan.save_budget("BBB", 2000.0, 0.0, 0.0, TODAY, path)
            self.assertEqual(sorted(entry_plan.load_budgets(path)), ["AAA", "BBB"])


class TestSizing(unittest.TestCase):
    SNAP = {"stocks": [{"ticker": "AAA", "qty": 10, "price": 100.0},
                       {"ticker": "BBB", "qty": 5, "price": None, "current_value": 1000.0}]}

    def test_book_value_falls_back_to_holdings_value(self):
        self.assertEqual(entry_plan.book_value(self.SNAP), 2000.0)

    def test_budget_is_the_gap_to_the_target_weight(self):
        self.assertEqual(entry_plan.budget_for_target(60, 2000.0, 1000.0), 200.0)

    def test_budget_never_negative(self):
        self.assertEqual(entry_plan.budget_for_target(10, 2000.0, 1000.0), 0.0)

    def test_find_stock_prefers_the_holding(self):
        screen = {"stocks": [{"ticker": "AAA", "price": 99.0}, {"ticker": "NEWCO", "price": 50.0}]}
        s, held = entry_plan.find_stock("aaa", self.SNAP, screen)
        self.assertTrue(held)
        self.assertEqual(s["price"], 100.0)
        s, held = entry_plan.find_stock("NEWCO", self.SNAP, screen)
        self.assertFalse(held)
        self.assertEqual(entry_plan.find_stock("ZZZ", self.SNAP, screen), (None, False))


class TestResultsWindow(unittest.TestCase):
    def test_upcoming_window(self):
        s = {"latest_quarter_end": "2026-06-30", "fiscal_year_end": "Mar"}
        self.assertEqual(entry_plan.results_window(s, TODAY), WINDOW)

    def test_passed_window_is_unknown(self):
        s = {"latest_quarter_end": "2025-06-30", "fiscal_year_end": "Mar"}
        self.assertIsNone(entry_plan.results_window(s, TODAY))

    def test_missing_quarter_is_unknown(self):
        self.assertIsNone(entry_plan.results_window({}, TODAY))


class TestRender(unittest.TestCase):
    def test_staged_plan_reads_as_numbered_tranches(self):
        p = entry_plan.plan(100.0, 30000.0, FALLING, WINDOW, TODAY)
        out = entry_plan.render("NEWCO", 100.0, 30000.0, p)
        self.assertIn("-> falling", out)
        self.assertIn("  1. Now: 100 shares, ₹10,000", out)
        self.assertIn("  2. At or below ₹95.00", out)
        self.assertIn("  3. After the next result", out)
        self.assertIn("unspent tranches are cancelled", out)

    def test_single_purchase_has_no_cancel_line(self):
        p = entry_plan.plan(100.0, 30000.0, STEADY, WINDOW, TODAY)
        out = entry_plan.render("NEWCO", 100.0, 30000.0, p)
        self.assertIn("-> not falling", out)
        self.assertNotIn("cancelled", out)


if __name__ == "__main__":
    unittest.main()
