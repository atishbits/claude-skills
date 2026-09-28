import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tax_lots  # noqa: E402


class TestAddMonths(unittest.TestCase):
    def test_simple_case(self):
        self.assertEqual(tax_lots.add_months(date(2025, 6, 15), 12), date(2026, 6, 15))

    def test_clamps_short_month_no_leap_year(self):
        # 31 Jan + 1 month -> Feb has 28 days in a non-leap year.
        self.assertEqual(tax_lots.add_months(date(2025, 1, 31), 1), date(2025, 2, 28))

    def test_leap_day_to_non_leap_year_clamps(self):
        self.assertEqual(tax_lots.add_months(date(2024, 2, 29), 12), date(2025, 2, 28))

    def test_leap_day_to_leap_year(self):
        self.assertEqual(tax_lots.add_months(date(2024, 2, 29), 48), date(2028, 2, 29))

    def test_crosses_year_boundary(self):
        self.assertEqual(tax_lots.add_months(date(2025, 11, 28), 12), date(2026, 11, 28))


class TestIsLongTerm(unittest.TestCase):
    """The regression this session found by testing against a real Zerodha
    Console export: Console reports a lot bought 2025-11-28 as turning
    long-term on 2026-11-29, not on the 2026-11-28 anniversary itself -- a
    fixed `held_days >= 365` threshold got this wrong on the anniversary
    day. The rule is "more than 12 months", so the anniversary date itself
    must still be short-term."""

    def test_anniversary_date_is_still_short_term(self):
        self.assertFalse(tax_lots.is_long_term(date(2025, 11, 28), date(2026, 11, 28)))

    def test_day_after_anniversary_is_long_term(self):
        self.assertTrue(tax_lots.is_long_term(date(2025, 11, 28), date(2026, 11, 29)))

    def test_day_before_anniversary_is_short_term(self):
        self.assertFalse(tax_lots.is_long_term(date(2025, 11, 28), date(2026, 11, 27)))

    def test_matches_documented_example_from_a_real_console_export(self):
        # The user's own data file states: "held more than 12 months as of
        # 2026-09-27 (lot bought on or before 2025-09-26)".
        self.assertTrue(tax_lots.is_long_term(date(2025, 9, 26), date(2026, 9, 27)))
        self.assertFalse(tax_lots.is_long_term(date(2025, 9, 27), date(2026, 9, 27)))

    def test_a_fixed_365_day_threshold_would_get_this_wrong(self):
        # This is exactly the case a flat day-count threshold cannot satisfy
        # for both examples at once: 365 days after 2024-02-29 (a leap day)
        # is 2025-02-28, which IS the correct 12-calendar-month mark, but
        # 365 days after 2023-03-01 (a non-leap-day date whose window
        # crosses a leap day) is 2024-02-29 -- one day *before* the correct
        # 12-calendar-month mark of 2024-03-01. A single day-count constant
        # cannot get both of these right; calendar-month arithmetic does.
        self.assertFalse(tax_lots.is_long_term(date(2023, 3, 1), date(2024, 2, 29)))
        self.assertTrue(tax_lots.is_long_term(date(2023, 3, 1), date(2024, 3, 2)))


class TestLotStatus(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 27)

    def test_short_term_lot(self):
        lot = {"date": "2026-06-01", "qty": 10, "cost": 100.0}
        status = tax_lots.lot_status(lot, price=110.0, today=self.today)
        self.assertFalse(status["is_lt"])
        self.assertAlmostEqual(status["gain"], 100.0)  # (110-100)*10

    def test_long_term_lot(self):
        lot = {"date": "2025-06-01", "qty": 5, "cost": 50.0}
        status = tax_lots.lot_status(lot, price=60.0, today=self.today)
        self.assertTrue(status["is_lt"])

    def test_days_to_lt_counts_from_conversion_date(self):
        # Conversion date is 2026-09-27 exactly (self.today); one more day needed.
        lot = {"date": "2025-09-27", "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today)
        self.assertFalse(status["is_lt"])
        self.assertEqual(status["days_to_lt"], 1)

    def test_near_lt_flag_fires_within_window(self):
        # Bought 2025-09-30 -> the 12-month mark is 2026-09-30, still ST that
        # day too (is_long_term is strict), so the first LT date is
        # 2026-10-01 -- 4 days after today (2026-09-27).
        lot = {"date": "2025-09-30", "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=60)
        self.assertFalse(status["is_lt"])
        self.assertEqual(status["days_to_lt"], 4)
        self.assertTrue(status["near_lt"])

    def test_near_lt_flag_does_not_fire_outside_window(self):
        lot = {"date": "2026-06-20", "qty": 1, "cost": 10.0}  # far from 12mo
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=60)
        self.assertFalse(status["near_lt"])

    def test_near_lt_never_fires_for_an_already_lt_lot(self):
        lot = {"date": "2024-01-01", "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=9999)
        self.assertTrue(status["is_lt"])
        self.assertFalse(status["near_lt"])

    def test_non_numeric_cost_without_fallback_is_unknown(self):
        lot = {"date": "2025-01-01", "qty": 5, "cost": "demerger"}
        status = tax_lots.lot_status(lot, price=100.0, today=self.today)
        self.assertIsNotNone(status)
        self.assertIsNone(status["gain"])
        self.assertFalse(status["cost_is_estimate"])

    def test_non_numeric_cost_uses_fallback_and_is_labelled_estimated(self):
        # TMCV's real case: demerger lots with no cost silently dropped 25 of
        # 29 shares from every total before this fallback existed.
        lot = {"date": "2024-01-01", "qty": 5, "cost": "demerger"}
        status = tax_lots.lot_status(lot, price=100.0, today=self.today, fallback_cost=80.0)
        self.assertAlmostEqual(status["gain"], 100.0)  # (100-80)*5
        self.assertTrue(status["cost_is_estimate"])

    def test_zero_qty_yields_no_gain(self):
        lot = {"date": "2025-01-01", "qty": 0, "cost": 100.0}
        status = tax_lots.lot_status(lot, price=110.0, today=self.today)
        self.assertIsNone(status["gain"])

    def test_unparseable_date_returns_none(self):
        lot = {"date": "not-a-date", "qty": 1, "cost": 10.0}
        self.assertIsNone(tax_lots.lot_status(lot, price=20.0, today=self.today))

    def test_missing_date_returns_none(self):
        lot = {"qty": 1, "cost": 10.0}
        self.assertIsNone(tax_lots.lot_status(lot, price=20.0, today=self.today))

    def test_loss_is_negative_gain(self):
        lot = {"date": "2026-01-01", "qty": 10, "cost": 200.0}
        status = tax_lots.lot_status(lot, price=150.0, today=self.today)
        self.assertAlmostEqual(status["gain"], -500.0)


if __name__ == "__main__":
    unittest.main()
