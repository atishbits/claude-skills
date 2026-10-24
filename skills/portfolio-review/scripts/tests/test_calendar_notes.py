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
        rows = calendar_notes.price_level_rows("TESTCO", 3000, {"dma200_reliable": True, "dma200": 2950})
        labels = [r["detail"] for r in rows]
        self.assertTrue(any("200 DMA" in d for d in labels))

    def test_falls_back_to_50dma_when_200_unreliable(self):
        rows = calendar_notes.price_level_rows(
            "NEWCO", 100, {"dma200_reliable": False, "dma200": 90, "dma50": 95})
        labels = [r["detail"] for r in rows]
        self.assertTrue(any("50 DMA" in d for d in labels))
        self.assertFalse(any("200 DMA" in d for d in labels))

    def test_flags_due_now_when_price_is_close(self):
        rows = calendar_notes.price_level_rows("TESTCO", 2960, {"dma200_reliable": True, "dma200": 2950})
        due = [r for r in rows if r["due_now"]]
        self.assertEqual(len(due), 1)
        self.assertIn("DUE NOW", due[0]["detail"])

    def test_includes_60_day_low(self):
        # The key fetch_fundamentals.py actually writes into `technicals`.
        rows = calendar_notes.price_level_rows("TESTCO", 3000, {"recent_low_60d": 2800})
        self.assertTrue(any("60-day low" in r["detail"] for r in rows))


class TestBuildRows(unittest.TestCase):
    def test_filters_to_requested_tickers(self):
        stocks = [
            {"ticker": "TESTCO", "price": 3000, "latest_quarter_end": "2026-06-30", "technicals": {}},
            {"ticker": "ITEMCO", "price": 400, "latest_quarter_end": "2026-06-30", "technicals": {}},
        ]
        rows = calendar_notes.build_rows(stocks, tickers=["testco"])
        self.assertTrue(all(r["ticker"] == "TESTCO" for r in rows))

    def test_no_ticker_filter_covers_everything(self):
        stocks = [
            {"ticker": "TESTCO", "price": 3000, "latest_quarter_end": "2026-06-30", "technicals": {}},
            {"ticker": "ITEMCO", "price": 400, "latest_quarter_end": "2026-06-30", "technicals": {}},
        ]
        rows = calendar_notes.build_rows(stocks)
        tickers = {r["ticker"] for r in rows}
        self.assertEqual(tickers, {"TESTCO", "ITEMCO"})

    def test_skips_results_row_when_no_quarter_end(self):
        stocks = [{"ticker": "NEWCO", "price": 100, "technicals": {}}]
        rows = calendar_notes.build_rows(stocks)
        self.assertFalse(any(r["kind"] == "results-estimate" for r in rows))


class TestWriteCalendarMd(unittest.TestCase):
    def test_writes_a_markdown_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "calendar.md")
            rows = [{"ticker": "TESTCO", "kind": "price-level", "detail": "200 DMA at 2950.00"}]
            out = calendar_notes.write_calendar_md(rows, path=path)
            self.assertEqual(out, path)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("| TESTCO | price-level | 200 DMA at 2950.00 |", content)
            self.assertIn("# Calendar candidates", content)



class TestPostResultRecheck(unittest.TestCase):
    def test_friday_after_close_result_rechecks_tuesday(self):
        # Out Fri after the close: priced Mon, re-checked Tue morning, not Sat.
        first, recheck = calendar_notes.post_result_recheck(date(2026, 10, 23), "after-close")
        self.assertEqual(first, date(2026, 10, 26))
        self.assertEqual(recheck, date(2026, 10, 27))

    def test_unknown_timing_is_treated_as_after_close(self):
        self.assertEqual(calendar_notes.post_result_recheck(date(2026, 10, 21)),
                         calendar_notes.post_result_recheck(date(2026, 10, 21), "after-close"))

    def test_result_during_session_is_priced_same_day(self):
        first, recheck = calendar_notes.post_result_recheck(date(2026, 10, 21), "during")
        self.assertEqual(first, date(2026, 10, 21))
        self.assertEqual(recheck, date(2026, 10, 22))

    def test_weekend_result_is_priced_monday_whatever_the_timing(self):
        first, _ = calendar_notes.post_result_recheck(date(2026, 10, 24), "pre-open")
        self.assertEqual(first, date(2026, 10, 26))

    def test_holidays_are_skipped(self):
        hol = {date(2026, 10, 26)}
        first, recheck = calendar_notes.post_result_recheck(date(2026, 10, 23), "after-close", hol)
        self.assertEqual(first, date(2026, 10, 27))
        self.assertEqual(recheck, date(2026, 10, 28))

    def test_rejects_unknown_timing_label(self):
        with self.assertRaises(ValueError):
            calendar_notes.post_result_recheck(date(2026, 10, 23), "evening")

if __name__ == "__main__":
    unittest.main()


class TestCalendarMerge(unittest.TestCase):
    def test_named_tickers_replace_only_their_own_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calendar.md")
            calendar_notes.write_calendar_md(
                [{"ticker": "EXAMPLEA", "kind": "price-level", "detail": "200 DMA 500"},
                 {"ticker": "TESTCO", "kind": "price-level", "detail": "old"}], path)
            rows = calendar_notes.merge_rows(
                calendar_notes.read_calendar_rows(path),
                [{"ticker": "TESTCO", "kind": "price-level", "detail": "new"}], ["TESTCO"])
            self.assertEqual([(r["ticker"], r["detail"]) for r in rows],
                             [("EXAMPLEA", "200 DMA 500"), ("TESTCO", "new")])

    def test_missing_file_reads_as_no_rows(self):
        self.assertEqual(calendar_notes.read_calendar_rows("/nonexistent/calendar.md"), [])
