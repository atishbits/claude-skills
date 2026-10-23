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
    """A broker's own lot-level export reports a lot bought 2025-06-02 as turning
    long-term on 2026-06-03, not on the 2026-06-02 anniversary itself -- a
    fixed `held_days >= 365` threshold got this wrong on the anniversary
    day. The rule is "more than 12 months", so the anniversary date itself
    must still be short-term."""

    def test_anniversary_date_is_still_short_term(self):
        self.assertFalse(tax_lots.is_long_term(date(2025, 6, 2), date(2026, 6, 2)))

    def test_day_after_anniversary_is_long_term(self):
        self.assertTrue(tax_lots.is_long_term(date(2025, 6, 2), date(2026, 6, 3)))

    def test_day_before_anniversary_is_short_term(self):
        self.assertFalse(tax_lots.is_long_term(date(2025, 6, 2), date(2026, 6, 1)))

    def test_matches_the_example_in_the_export_template(self):
        # The template states: "held more than 12 months as of 2026-01-15
        # (lot bought on or before 2025-01-14)".
        self.assertTrue(tax_lots.is_long_term(date(2025, 1, 14), date(2026, 1, 15)))
        self.assertFalse(tax_lots.is_long_term(date(2025, 1, 15), date(2026, 1, 15)))

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
        # Demerger lots with no cost were silently dropped from every total
        # before this fallback existed.
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


LOTS = [{"date": "2026-01-10", "qty": 10, "cost": 100.0, "broker": "brokera"},
        {"date": "2025-06-01", "qty": 5, "cost": 80.0, "broker": "brokera"},
        {"date": "2026-03-01", "qty": 8, "cost": 120.0, "broker": "brokerb"}]


class TestFifoAndSaleTax(unittest.TestCase):
    def test_fifo_oldest_first_within_account(self):
        m = tax_lots.fifo_match(LOTS, 8, "brokera")
        self.assertEqual([(x["date"], x["qty"]) for x in m], [("2025-06-01", 5), ("2026-01-10", 3)])

    def test_fifo_skips_already_sold(self):
        m = tax_lots.fifo_match(LOTS, 2, "brokera", already_sold=5)
        self.assertEqual([(x["date"], x["qty"]) for x in m], [("2026-01-10", 2)])

    def test_fifo_never_spills_into_other_account(self):
        with self.assertRaisesRegex(ValueError, "brokera.*15"):
            tax_lots.fifo_match(LOTS, 16, "brokera")

    def test_fifo_requires_account_when_split(self):
        with self.assertRaises(ValueError):
            tax_lots.fifo_match(LOTS, 1, None)

    def test_fifo_no_account_ok_when_single_broker(self):
        m = tax_lots.fifo_match(LOTS[:2], 5, None)
        self.assertEqual([(x["date"], x["qty"]) for x in m], [("2025-06-01", 5)])

    def test_demerger_cost_estimated_and_pre2018_untaxed(self):
        lots = [{"date": "2017-05-01", "qty": 2, "cost": 50.0, "broker": "a"},
                {"date": "2024-01-01", "qty": 3, "cost": "demerger", "broker": "a"}]
        m = tax_lots.fifo_match(lots, 5, "a", fallback_cost=60.0)
        self.assertFalse(m[0]["taxable"])
        self.assertTrue(m[1]["cost_is_estimate"])
        self.assertEqual(m[1]["cost"], 60.0)

    def test_unparseable_date_untaxed_but_consumes_quantity(self):
        lots = [{"date": "n/a", "qty": 2, "cost": 50.0, "broker": "a"},
                {"date": "2024-01-01", "qty": 3, "cost": 70.0, "broker": "a"}]
        m = tax_lots.fifo_match(lots, 3, "a")
        self.assertFalse(m[0]["taxable"])
        self.assertEqual([x["qty"] for x in m], [2, 1])
        t = tax_lots.sale_tax(m, 100.0, date(2026, 10, 23))
        self.assertEqual(t["untaxed_qty"], 2)

    def test_sale_tax_split(self):
        m = tax_lots.fifo_match(LOTS, 8, "brokera")       # 5 LT @80, 3 ST @100
        t = tax_lots.sale_tax(m, 150.0, date(2026, 10, 23))
        self.assertEqual((t["ltcg"], t["stcg"]), (350.0, 150.0))
        self.assertAlmostEqual(t["est_tax"], 0.125 * 350 + 0.20 * 150)

    def test_fy_tax_offsets_and_exemption(self):
        r = tax_lots.fy_tax(stcg=-10_000, ltcg=200_000)
        self.assertEqual((r["net_lt"], r["exempt_used"]), (190_000, 125_000))
        self.assertAlmostEqual(r["tax"], 0.125 * 65_000)


class TestBreakevenDrop(unittest.TestCase):
    LOT = [{"date": "2026-06-01", "qty": 1, "cost": 100.0, "cost_is_estimate": False, "taxable": True}]

    def test_breakeven_drop_without_headroom(self):
        # now: 150 - 0.20*50 = 140; later: p - 0.125*(p-100) = 140 -> p = 145.714...
        self.assertAlmostEqual(tax_lots.breakeven_drop_pct(self.LOT, 150.0, date(2026, 10, 23), 0), 2.86, places=2)

    def test_breakeven_drop_with_full_headroom(self):
        self.assertAlmostEqual(tax_lots.breakeven_drop_pct(self.LOT, 150.0, date(2026, 10, 23), 1e9), 6.67, places=2)

    def test_breakeven_none_when_all_long_term(self):
        m = [{"date": "2024-06-01", "qty": 1, "cost": 100.0, "cost_is_estimate": False, "taxable": True}]
        self.assertIsNone(tax_lots.breakeven_drop_pct(m, 150.0, date(2026, 10, 23), 0))

    def test_breakeven_none_when_untaxable(self):
        m = [dict(self.LOT[0], taxable=False)]
        self.assertIsNone(tax_lots.breakeven_drop_pct(m, 150.0, date(2026, 10, 23), 0))


if __name__ == "__main__":
    unittest.main()
