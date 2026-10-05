import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import calendar_notes  # noqa: E402


class TestNextResultsWindow(unittest.TestCase):
    def test_simple_quarter_rollover(self):
        qe, start, end = calendar_notes.next_results_window("2026-06-30")
        # Next quarter end: 2026-09-30; results are due within 45 days of it.
        self.assertEqual(qe, date(2026, 9, 30))
        self.assertEqual(start, date(2026, 10, 15))
        self.assertEqual(end, date(2026, 11, 14))

    def test_year_end_quarter_gets_the_longer_deadline(self):
        qe, start, end = calendar_notes.next_results_window("2026-12-31", "Mar")
        self.assertEqual(qe, date(2027, 3, 31))
        self.assertEqual(start, date(2027, 4, 15))
        self.assertEqual(end, date(2027, 5, 30))

    def test_december_year_end_company(self):
        # Sep quarter reported; the Dec quarter closes this company's year.
        qe, _, end = calendar_notes.next_results_window("2026-09-30", "Dec")
        self.assertEqual(qe, date(2026, 12, 31))
        self.assertEqual((end - qe).days, 60)
        # ...and its March quarter is an ordinary one.
        qe, _, end = calendar_notes.next_results_window("2026-12-31", "Dec")
        self.assertEqual((end - qe).days, 45)

    def test_missing_fiscal_year_end_defaults_to_march(self):
        qe, _, end = calendar_notes.next_results_window("2026-12-31", None)
        self.assertEqual((end - qe).days, 60)

    def test_next_quarter_ends_on_its_month_end(self):
        # Mar 31 -> Jun 30 (shorter month), Sep 30 -> Dec 31 (longer month).
        self.assertEqual(calendar_notes.next_results_window("2026-03-31")[0], date(2026, 6, 30))
        self.assertEqual(calendar_notes.next_results_window("2026-09-30")[0], date(2026, 12, 31))


class TestNearLevel(unittest.TestCase):
    def test_within_threshold_is_near(self):
        self.assertTrue(calendar_notes.near_level(100, 102))

    def test_outside_threshold_is_not_near(self):
        self.assertFalse(calendar_notes.near_level(100, 120))

    def test_none_price_is_not_near(self):
        self.assertFalse(calendar_notes.near_level(None, 100))

    def test_none_level_is_not_near(self):
        self.assertFalse(calendar_notes.near_level(100, None))

    def test_zero_level_is_not_near(self):
        self.assertFalse(calendar_notes.near_level(100, 0))


class TestPriceLevelRows(unittest.TestCase):
    def test_uses_200dma_when_reliable(self):
        rows = calendar_notes.price_level_rows("TCS", 3000, {"dma200_reliable": True, "dma200": 2950})
        labels = [r["detail"] for r in rows]
        self.assertTrue(any("200 DMA" in d for d in labels))

    def test_falls_back_to_50dma_when_200_unreliable(self):
        rows = calendar_notes.price_level_rows(
            "NEWCO", 100, {"dma200_reliable": False, "dma200": 90, "dma50": 95})
        labels = [r["detail"] for r in rows]
        self.assertTrue(any("50 DMA" in d for d in labels))
        self.assertFalse(any("200 DMA" in d for d in labels))

    def test_flags_due_now_when_price_is_close(self):
        rows = calendar_notes.price_level_rows("TCS", 2960, {"dma200_reliable": True, "dma200": 2950})
        due = [r for r in rows if r["due_now"]]
        self.assertEqual(len(due), 1)
        self.assertIn("DUE NOW", due[0]["detail"])

    def test_includes_60_day_low(self):
        # The key fetch_fundamentals.py actually writes into `technicals`.
        rows = calendar_notes.price_level_rows("TCS", 3000, {"recent_low_60d": 2800})
        self.assertTrue(any("60-day low" in r["detail"] for r in rows))


class TestBuildRows(unittest.TestCase):
    def test_filters_to_requested_tickers(self):
        stocks = [
            {"ticker": "TCS", "price": 3000, "latest_quarter_end": "2026-06-30", "technicals": {}},
            {"ticker": "ITC", "price": 400, "latest_quarter_end": "2026-06-30", "technicals": {}},
        ]
        rows = calendar_notes.build_rows(stocks, tickers=["tcs"])
        self.assertTrue(all(r["ticker"] == "TCS" for r in rows))

    def test_no_ticker_filter_covers_everything(self):
        stocks = [
            {"ticker": "TCS", "price": 3000, "latest_quarter_end": "2026-06-30", "technicals": {}},
            {"ticker": "ITC", "price": 400, "latest_quarter_end": "2026-06-30", "technicals": {}},
        ]
        rows = calendar_notes.build_rows(stocks)
        tickers = {r["ticker"] for r in rows}
        self.assertEqual(tickers, {"TCS", "ITC"})

    def test_skips_results_row_when_no_quarter_end(self):
        stocks = [{"ticker": "NEWCO", "price": 100, "technicals": {}}]
        rows = calendar_notes.build_rows(stocks)
        self.assertFalse(any(r["kind"] == "results-estimate" for r in rows))


class TestWriteCalendarMd(unittest.TestCase):
    def test_writes_a_markdown_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "calendar.md")
            rows = [{"ticker": "TCS", "kind": "price-level", "detail": "200 DMA at 2950.00"}]
            out = calendar_notes.write_calendar_md(rows, path=path)
            self.assertEqual(out, path)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("| TCS | price-level | 200 DMA at 2950.00 |", content)
            self.assertIn("# Calendar candidates", content)


if __name__ == "__main__":
    unittest.main()
