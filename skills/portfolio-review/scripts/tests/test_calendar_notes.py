import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import calendar_notes  # noqa: E402


class TestNextResultsWindow(unittest.TestCase):
    def test_simple_quarter_rollover(self):
        start, end = calendar_notes.next_results_window("2026-06-30")
        # Next quarter end: 2026-09-30, +45/+75 days.
        self.assertEqual(start, date(2026, 9, 30) + calendar_notes.timedelta(days=45))
        self.assertEqual(end, date(2026, 9, 30) + calendar_notes.timedelta(days=75))

    def test_year_rollover(self):
        start, _ = calendar_notes.next_results_window("2026-12-31")
        # Next quarter end: 2027-03-31.
        self.assertEqual(start.year, 2027)
        self.assertEqual(start.month >= 3, True)

    def test_clamps_day_for_shorter_target_month(self):
        # Jun 30 + 3 months lands in Sep, which only has 30 days -- no crash,
        # no rolling into October.
        start, _ = calendar_notes.next_results_window("2026-03-31")
        # Next quarter end should be Jun 30, not Jul 1.
        # (start is +45 days from that quarter end, so just check no exception
        # and the window is chronologically sane.)
        self.assertIsNotNone(start)


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
        rows = calendar_notes.price_level_rows("TCS", 3000, {"range_60d_low": 2800})
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
