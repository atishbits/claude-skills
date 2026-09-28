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

    def test_later_entry_without_checkin_does_not_clear_earlier_reminder(self):
        """A ticker whose EARLIER entry had a past next_checkin and whose LATER entry
        has none still appears: an entry with no next_checkin never erases a reminder."""
        entries = [
            {"ticker": "TCS", "date": "2026-08-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "first with past checkin", "next_checkin": "2026-09-01"},
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "second without next_checkin"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["reason"], "first with past checkin")

    def test_same_day_funnel_deep_dive_reminder_fires(self):
        """The multibagger-scan funnel records mechanical -> judgment -> deep-dive for one
        ticker on the same day, and only deep-dive sets next_checkin. That reminder must
        surface even though the earlier same-date entries have none."""
        entries = [
            {"ticker": "ZENTRO", "date": "2026-06-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "quality pass; near local low"},
            {"ticker": "ZENTRO", "date": "2026-06-01", "stage": "JUDGMENT", "outcome": "PASS",
             "reason": "long runway"},
            {"ticker": "ZENTRO", "date": "2026-06-01", "stage": "DEEP-DIVE", "outcome": "PASS",
             "reason": "rated HOLD, see rating_ledger", "next_checkin": "2026-09-01"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual([e["ticker"] for e in overdue], ["ZENTRO"])
        self.assertEqual(overdue[0]["stage"], "DEEP-DIVE")

    def test_same_day_funnel_via_ledger_file(self):
        """Same bug scenario end to end through append_entry/load_history, so the
        file-order tie-break is exercised on real ledger output."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scan-history.jsonl")
            scan_history.append_entry("ZENTRO", "mechanical", "pass", "quality pass; near local low",
                                      asof="2026-06-01", ledger_path=path)
            scan_history.append_entry("ZENTRO", "judgment", "pass", "long runway",
                                      asof="2026-06-01", ledger_path=path)
            scan_history.append_entry("ZENTRO", "deep-dive", "pass", "rated BUY, see rating_ledger",
                                      asof="2026-06-01", next_checkin="2026-09-01", ledger_path=path)
            overdue = scan_history.overdue_checkins(scan_history.load_history(ledger_path=path),
                                                    today="2026-09-20")
        self.assertEqual([e["stage"] for e in overdue], ["DEEP-DIVE"])

    def test_same_date_reminders_tie_broken_by_file_order(self):
        """Two same-date entries both carrying next_checkin: the one later in the list wins."""
        entries = [
            {"ticker": "QORVIK", "date": "2026-06-01", "stage": "JUDGMENT", "outcome": "BORDERLINE",
             "reason": "first", "next_checkin": "2026-07-01"},
            {"ticker": "QORVIK", "date": "2026-06-01", "stage": "DEEP-DIVE", "outcome": "PASS",
             "reason": "second", "next_checkin": "2026-12-01"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        self.assertEqual(overdue, [])

    def test_ticker_with_no_reminders_contributes_nothing(self):
        entries = [
            {"ticker": "QORVIK", "date": "2026-06-01", "stage": "MECHANICAL", "outcome": "FAIL",
             "reason": "roce short 20.0%"},
        ]
        self.assertEqual(scan_history.overdue_checkins(entries, today="2026-09-20"), [])

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

    def test_later_reminder_supersedes_earlier_reminder(self):
        """When several entries carry a next_checkin, only the latest such entry (by date)
        is checked -- a later, future reminder replaces an earlier, past one."""
        entries = [
            {"ticker": "TCS", "date": "2026-08-01", "stage": "MECHANICAL", "outcome": "PASS",
             "reason": "old", "next_checkin": "2026-08-15"},
            {"ticker": "TCS", "date": "2026-09-10", "stage": "JUDGMENT", "outcome": "PASS",
             "reason": "new", "next_checkin": "2026-10-15"},
        ]
        overdue = scan_history.overdue_checkins(entries, today="2026-09-20")
        # Only the latest reminder (2026-09-10's) is checked; its next_checkin (2026-10-15) is in future
        self.assertEqual(len(overdue), 0)


class TestRecordShortlist(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmpdir.name, "scan-history.jsonl")
        self.shortlist_path = os.path.join(self.tmpdir.name, "multibagger-shortlist-2026-06-01.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def write_shortlist(self, stocks):
        with open(self.shortlist_path, "w", encoding="utf-8") as fh:
            json.dump({"generated_at": "2026-06-01T10:00:00", "source_file": "screen-2026-06-01.json",
                       "thresholds": {}, "screened": len(stocks), "stocks": stocks}, fh)

    def test_records_every_stock_with_verdict_and_reason(self):
        self.write_shortlist([
            {"ticker": "ZENTRO", "quality_verdict": "pass", "near_local_low": True,
             "reason": "quality pass; near local low"},
            {"ticker": "QORVIK", "quality_verdict": "borderline", "near_local_low": False,
             "reason": "roce short 8.9%; not near a local low"},
            {"ticker": "MALBEX", "quality_verdict": "fail", "near_local_low": False,
             "reason": "pe_growth over by 12.0%; cash_conversion short 5.0%; not near a local low"},
        ])
        returned = scan_history.record_shortlist(self.shortlist_path, asof="2026-06-01",
                                                 ledger_path=self.ledger_path)
        self.assertEqual(len(returned), 3)
        with open(self.ledger_path, encoding="utf-8") as fh:
            written = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(
            [(e["ticker"], e["stage"], e["outcome"], e["reason"], e["date"]) for e in written],
            [("ZENTRO", "MECHANICAL", "PASS", "quality pass; near local low", "2026-06-01"),
             ("QORVIK", "MECHANICAL", "BORDERLINE", "roce short 8.9%; not near a local low", "2026-06-01"),
             ("MALBEX", "MECHANICAL", "FAIL",
              "pe_growth over by 12.0%; cash_conversion short 5.0%; not near a local low", "2026-06-01")])
        for e in written:
            self.assertNotIn("next_checkin", e)

    def test_stage_override(self):
        self.write_shortlist([{"ticker": "ZENTRO", "quality_verdict": "pass", "reason": "quality pass"}])
        entries = scan_history.record_shortlist(self.shortlist_path, stage="judgment",
                                                ledger_path=self.ledger_path)
        self.assertEqual(entries[0]["stage"], "JUDGMENT")

    def test_missing_reason_raises_and_writes_nothing(self):
        self.write_shortlist([
            {"ticker": "ZENTRO", "quality_verdict": "pass", "reason": "quality pass"},
            {"ticker": "QORVIK", "quality_verdict": "fail"},
        ])
        with self.assertRaises(ValueError):
            scan_history.record_shortlist(self.shortlist_path, ledger_path=self.ledger_path)
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_bad_verdict_raises_and_writes_nothing(self):
        self.write_shortlist([
            {"ticker": "ZENTRO", "quality_verdict": "pass", "reason": "quality pass"},
            {"ticker": "QORVIK", "quality_verdict": "maybe", "reason": "x"},
        ])
        with self.assertRaises(ValueError):
            scan_history.record_shortlist(self.shortlist_path, ledger_path=self.ledger_path)
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_missing_ticker_or_verdict_raises_value_error(self):
        for stock in ({"quality_verdict": "pass", "reason": "x"},
                      {"ticker": 7, "quality_verdict": "pass", "reason": "x"},
                      {"ticker": "ZENTRO", "reason": "x"}):
            self.write_shortlist([stock])
            with self.assertRaises(ValueError):
                scan_history.record_shortlist(self.shortlist_path, ledger_path=self.ledger_path)
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_not_a_shortlist_file_raises(self):
        with open(self.shortlist_path, "w", encoding="utf-8") as fh:
            json.dump({"something": "else"}, fh)
        with self.assertRaises(ValueError):
            scan_history.record_shortlist(self.shortlist_path, ledger_path=self.ledger_path)

    def test_cli_record_shortlist_is_one_invocation(self):
        """End to end through main(): one CLI call records every stock."""
        self.write_shortlist([
            {"ticker": "ZENTRO", "quality_verdict": "pass", "reason": "quality pass; near local low"},
            {"ticker": "QORVIK", "quality_verdict": "fail", "reason": "roce short 20.0%; not near a local low"},
        ])
        import io
        from contextlib import redirect_stdout
        saved_argv, saved_path = sys.argv, scan_history.LEDGER_PATH
        sys.argv = ["scan_history.py", "record-shortlist", self.shortlist_path, "--date", "2026-06-01"]
        scan_history.LEDGER_PATH = self.ledger_path
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                scan_history.main()
        finally:
            sys.argv, scan_history.LEDGER_PATH = saved_argv, saved_path
        self.assertIn("Recorded 2 MECHANICAL entries", out.getvalue())
        entries = scan_history.load_history(ledger_path=self.ledger_path)
        self.assertEqual({(e["ticker"], e["outcome"]) for e in entries},
                         {("ZENTRO", "PASS"), ("QORVIK", "FAIL")})


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


class TestCmdReport(unittest.TestCase):
    """CLI-level tests for cmd_report function."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmpdir.name, "scan-history.jsonl")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_overdue_section_prints_even_when_filtered_entries_empty(self):
        """Finding 1: Overdue re-checks section must always print, even when
        filtered entries are empty (e.g., --borderline with no BORDERLINE entries,
        or a ticker with no entries). This ensures a due reminder for a ticker
        the user didn't ask about still surfaces."""
        # Create two entries: one PASS with past next_checkin, one BORDERLINE with future
        scan_history.append_entry("TCS", "MECHANICAL", "PASS", "cheap",
                                 asof="2026-09-01", next_checkin="2026-09-10",
                                 ledger_path=self.ledger_path)
        scan_history.append_entry("ITC", "MECHANICAL", "BORDERLINE", "review",
                                 asof="2026-09-05", next_checkin="2026-10-15",
                                 ledger_path=self.ledger_path)

        # Mock args for report with --borderline (filters out TCS)
        class Args:
            tickers = []
            borderline = True

        # Monkey-patch load_history to use our test ledger
        original_load = scan_history.load_history
        scan_history.load_history = lambda ticker=None, ledger_path=None: original_load(ledger_path=self.ledger_path)

        try:
            # Capture output
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                scan_history.cmd_report(Args())
            output = f.getvalue()

            # Verify ITC BORDERLINE entry is shown (filtered result)
            self.assertIn("ITC", output)
            self.assertIn("BORDERLINE", output)

            # Verify TCS is NOT in the filtered entries section (because it's PASS, not BORDERLINE)
            # but we should still see the overdue section
            self.assertIn("Overdue re-checks:", output)
            self.assertIn("TCS", output)  # TCS should appear in overdue section
            self.assertIn("cheap", output)  # TCS's reason should appear
        finally:
            scan_history.load_history = original_load

    def test_overdue_section_prints_none_when_no_ticker_filters_and_empty(self):
        """When the ledger is completely empty, "No scan history entries yet."
        prints, but we still get "Overdue re-checks: none." """
        class Args:
            tickers = []
            borderline = False

        # Monkey-patch load_history to use empty ledger
        original_load = scan_history.load_history
        scan_history.load_history = lambda ticker=None, ledger_path=None: []

        try:
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                scan_history.cmd_report(Args())
            output = f.getvalue()

            self.assertIn("No scan history entries yet.", output)
            self.assertIn("Overdue re-checks:", output)
            self.assertIn("none.", output)
        finally:
            scan_history.load_history = original_load

    def test_report_calls_build_report_not_inline_formatting(self):
        """Verify cmd_report uses build_report for formatting (not reimplemented)."""
        scan_history.append_entry("TCS", "MECHANICAL", "PASS", "cheap",
                                 asof="2026-09-01", ledger_path=self.ledger_path)

        class Args:
            tickers = []
            borderline = False

        # Monkey-patch load_history and build_report to verify build_report is called
        original_load = scan_history.load_history
        original_build = scan_history.build_report

        build_report_called = []

        def mock_build_report(entries, today=None):
            build_report_called.append(True)
            return original_build(entries, today)

        scan_history.load_history = lambda ticker=None, ledger_path=None: original_load(ledger_path=self.ledger_path)
        scan_history.build_report = mock_build_report

        try:
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                scan_history.cmd_report(Args())

            # Verify build_report was called
            self.assertTrue(build_report_called, "build_report should be called by cmd_report")
        finally:
            scan_history.load_history = original_load
            scan_history.build_report = original_build


if __name__ == "__main__":
    unittest.main()
