import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scan_history  # noqa: E402


class TestNormaliseStage(unittest.TestCase):
    def test_accepts_plain_stages_case_insensitive(self):
        self.assertEqual(scan_history.normalise_stage("mechanical"), "MECHANICAL")
        self.assertEqual(scan_history.normalise_stage("Judgment"), "JUDGMENT")
        self.assertEqual(scan_history.normalise_stage("DEEP-DIVE"), "DEEP-DIVE")

    def test_accepts_whitespace_variations(self):
        self.assertEqual(scan_history.normalise_stage("  mechanical  "), "MECHANICAL")

    def test_rejects_anything_else(self):
        with self.assertRaises(ValueError) as ctx:
            scan_history.normalise_stage("UNKNOWN")
        self.assertIn("stage must be", str(ctx.exception))


class TestNormaliseOutcome(unittest.TestCase):
    def test_accepts_plain_outcomes_case_insensitive(self):
        self.assertEqual(scan_history.normalise_outcome("pass"), "PASS")
        self.assertEqual(scan_history.normalise_outcome("Fail"), "FAIL")
        self.assertEqual(scan_history.normalise_outcome("BORDERLINE"), "BORDERLINE")

    def test_accepts_whitespace_variations(self):
        self.assertEqual(scan_history.normalise_outcome("  pass  "), "PASS")

    def test_rejects_anything_else(self):
        with self.assertRaises(ValueError) as ctx:
            scan_history.normalise_outcome("MAYBE")
        self.assertIn("outcome must be", str(ctx.exception))


class TestAppendAndLoadHistory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmpdir.name, "scan-history.jsonl")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_append_then_load_round_trips(self):
        scan_history.append_entry("TCS", "mechanical", "pass", "passed thresholds",
                                  asof="2026-09-27", ledger_path=self.ledger_path)
        entries = scan_history.load_history(ledger_path=self.ledger_path)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["ticker"], "TCS")
        self.assertEqual(e["stage"], "MECHANICAL")
        self.assertEqual(e["outcome"], "PASS")
        self.assertEqual(e["reason"], "passed thresholds")
        self.assertEqual(e["date"], "2026-09-27")
        self.assertNotIn("next_checkin", e)

    def test_append_with_next_checkin_round_trips(self):
        scan_history.append_entry("TCS", "mechanical", "borderline", "needs review",
                                  asof="2026-09-27", next_checkin="2026-10-15",
                                  ledger_path=self.ledger_path)
        entries = scan_history.load_history(ledger_path=self.ledger_path)
        e = entries[0]
        self.assertEqual(e["next_checkin"], "2026-10-15")

    def test_rejects_blank_reason(self):
        with self.assertRaises(ValueError) as ctx:
            scan_history.append_entry("TCS", "mechanical", "pass", "", ledger_path=self.ledger_path)
        self.assertIn("reason must be non-empty", str(ctx.exception))

    def test_rejects_whitespace_only_reason(self):
        with self.assertRaises(ValueError) as ctx:
            scan_history.append_entry("TCS", "mechanical", "pass", "   ", ledger_path=self.ledger_path)
        self.assertIn("reason must be non-empty", str(ctx.exception))

    def test_filters_by_ticker(self):
        scan_history.append_entry("TCS", "mechanical", "pass", "x", asof="2026-09-01",
                                  ledger_path=self.ledger_path)
        scan_history.append_entry("ITC", "judgment", "fail", "y", asof="2026-09-02",
                                  ledger_path=self.ledger_path)
        tcs_only = scan_history.load_history(ticker="tcs", ledger_path=self.ledger_path)
        self.assertEqual([e["ticker"] for e in tcs_only], ["TCS"])

    def test_sorted_by_ticker_then_date(self):
        scan_history.append_entry("TCS", "mechanical", "pass", "later", asof="2026-09-10",
                                  ledger_path=self.ledger_path)
        scan_history.append_entry("TCS", "judgment", "fail", "earlier", asof="2026-08-01",
                                  ledger_path=self.ledger_path)
        scan_history.append_entry("ABC", "deep-dive", "borderline", "first_ticker", asof="2026-09-05",
                                  ledger_path=self.ledger_path)
        entries = scan_history.load_history(ledger_path=self.ledger_path)
        tickers_dates = [(e["ticker"], e["date"]) for e in entries]
        self.assertEqual(tickers_dates, [("ABC", "2026-09-05"), ("TCS", "2026-08-01"), ("TCS", "2026-09-10")])

    def test_appends_are_newline_delimited_jsonl(self):
        scan_history.append_entry("TCS", "mechanical", "pass", "a", asof="2026-01-01",
                                  ledger_path=self.ledger_path)
        scan_history.append_entry("TCS", "judgment", "fail", "b", asof="2026-02-01",
                                  ledger_path=self.ledger_path)
        with open(self.ledger_path, encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        for line in lines:
            json.loads(line)  # each line stands alone as valid JSON


class TestOverdueCheckins(unittest.TestCase):
    def test_latest_entry_with_past_checkin_appears(self):
        """A ticker with two entries where only the latest has a past next_checkin appears."""
        entries = [
            {"ticker": "TCS", "date": "2026-08-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "first", "next_checkin": "2026-09-01"},
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "second with past checkin", "next_checkin": "2026-09-15"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["ticker"], "TCS")
        self.assertEqual(overdue[0]["date"], "2026-09-10")

    def test_latest_entry_with_future_checkin_does_not_appear(self):
        """A ticker whose latest entry's next_checkin is in the future does not appear."""
        entries = [
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "has future checkin", "next_checkin": "2026-10-15"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual(len(overdue), 0)

    def test_earlier_entry_superseded_by_latest_without_checkin(self):
        """A ticker whose EARLIER entry had a past next_checkin but whose LATEST entry
        has none does NOT appear (superseded)."""
        entries = [
            {"ticker": "TCS", "date": "2026-08-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "first with past checkin", "next_checkin": "2026-09-01"},
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "second without next_checkin"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual(len(overdue), 0)

    def test_multiple_tickers_sorted_by_checkin_date(self):
        """Multiple overdue tickers are sorted by next_checkin date ascending."""
        entries = [
            {"ticker": "ITC", "date": "2026-09-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "itc", "next_checkin": "2026-09-20"},
            {"ticker": "TCS", "date": "2026-09-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "tcs", "next_checkin": "2026-09-10"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-25")
        self.assertEqual(len(overdue), 2)
        self.assertEqual([e["ticker"] for e in overdue], ["TCS", "ITC"])
        self.assertEqual([e["next_checkin"] for e in overdue], ["2026-09-10", "2026-09-20"])

    def test_only_latest_entry_per_ticker_considered(self):
        """When a ticker has multiple entries, only the latest (by date) is checked for overdue."""
        entries = [
            {"ticker": "TCS", "date": "2026-08-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "old", "next_checkin": "2026-08-15"},
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "PASS",
             "reason": "new", "next_checkin": "2026-10-15"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        # Only the latest entry (2026-09-10) is checked; its next_checkin (2026-10-15) is in future
        self.assertEqual(len(overdue), 0)


class TestBuildReport(unittest.TestCase):
    def test_groups_by_ticker(self):
        entries = [
            {"ticker": "TCS", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "cheap"},
            {"ticker": "TCS", "date": "2026-06-01", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "review again"},
            {"ticker": "ITC", "date": "2026-02-01", "stage": "DEEP-DIVE", "outcome": "FAIL",
             "reason": "fell short"},
        ]
        lines = scan_history.build_report(entries, today="2026-09-01")
        text = "\n".join(lines)
        self.assertIn("TCS", text)
        self.assertIn("ITC", text)
        self.assertIn("cheap", text)
        self.assertIn("review again", text)
        self.assertIn("fell short", text)

    def test_includes_next_checkin_when_present(self):
        entries = [
            {"ticker": "TCS", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "x", "next_checkin": "2026-10-15"},
        ]
        lines = scan_history.build_report(entries)
        text = "\n".join(lines)
        self.assertIn("next: 2026-10-15", text)

    def test_omits_next_checkin_when_absent(self):
        entries = [
            {"ticker": "TCS", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "x"},
        ]
        lines = scan_history.build_report(entries)
        text = "\n".join(lines)
        self.assertNotIn("next:", text)

    def test_sorted_ticker_order(self):
        entries = [
            {"ticker": "ZZZ", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "z"},
            {"ticker": "AAA", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "a"},
            {"ticker": "MMM", "date": "2026-01-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "m"},
        ]
        lines = scan_history.build_report(entries)
        # Find the lines with ticker names
        ticker_lines = [l for l in lines if l and not l.startswith(" ")]
        self.assertEqual(ticker_lines, ["AAA", "MMM", "ZZZ"])


if __name__ == "__main__":
    unittest.main()
