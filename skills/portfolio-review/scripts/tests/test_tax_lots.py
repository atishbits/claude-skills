import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tax_lots  # noqa: E402


class TestLotStatus(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 27)

    def test_short_term_lot(self):
        lot = {"date": "2026-06-01", "qty": 10, "cost": 100.0}
        status = tax_lots.lot_status(lot, price=110.0, today=self.today)
        self.assertFalse(status["is_lt"])
        self.assertEqual(status["held_days"], (self.today - date(2026, 6, 1)).days)
        self.assertAlmostEqual(status["gain"], 100.0)  # (110-100)*10

    def test_long_term_lot_exactly_at_threshold(self):
        buy = self.today - timedelta(days=tax_lots.LT_THRESHOLD_DAYS)
        lot = {"date": buy.isoformat(), "qty": 5, "cost": 50.0}
        status = tax_lots.lot_status(lot, price=60.0, today=self.today)
        self.assertTrue(status["is_lt"])
        self.assertEqual(status["days_to_lt"], 0)

    def test_one_day_short_of_long_term(self):
        buy = self.today - timedelta(days=tax_lots.LT_THRESHOLD_DAYS - 1)
        lot = {"date": buy.isoformat(), "qty": 5, "cost": 50.0}
        status = tax_lots.lot_status(lot, price=60.0, today=self.today)
        self.assertFalse(status["is_lt"])
        self.assertEqual(status["days_to_lt"], 1)

    def test_near_lt_flag_fires_within_window(self):
        buy = self.today - timedelta(days=tax_lots.LT_THRESHOLD_DAYS - 30)
        lot = {"date": buy.isoformat(), "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=60)
        self.assertTrue(status["near_lt"])

    def test_near_lt_flag_does_not_fire_outside_window(self):
        buy = self.today - timedelta(days=100)  # 265 days to LT, well outside a 60d window
        lot = {"date": buy.isoformat(), "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=60)
        self.assertFalse(status["near_lt"])

    def test_near_lt_never_fires_for_an_already_lt_lot(self):
        buy = self.today - timedelta(days=tax_lots.LT_THRESHOLD_DAYS + 10)
        lot = {"date": buy.isoformat(), "qty": 1, "cost": 10.0}
        status = tax_lots.lot_status(lot, price=20.0, today=self.today, near_lt_days=9999)
        self.assertTrue(status["is_lt"])
        self.assertFalse(status["near_lt"])

    def test_non_numeric_cost_is_a_corporate_action_not_an_error(self):
        lot = {"date": "2025-01-01", "qty": 5, "cost": "demerger"}
        status = tax_lots.lot_status(lot, price=100.0, today=self.today)
        self.assertIsNotNone(status)
        self.assertIsNone(status["gain"])

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
