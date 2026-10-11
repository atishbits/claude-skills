import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import window  # noqa: E402
from common import parse_ts, read_last_run  # noqa: E402

NOW = parse_ts("2026-10-10T06:00:00Z")
WEEK_AGO = NOW - timedelta(days=7)


class TestComputeWindow(unittest.TestCase):
    def test_no_last_run_gives_seven_days(self):
        start, end, basis = window.compute_window(NOW)
        self.assertEqual((start, end), (WEEK_AGO, NOW))
        self.assertTrue(basis.startswith("last 7 days"))

    def test_recent_last_run_is_the_start(self):
        last = parse_ts("2026-10-07T06:00:00Z")
        start, _, basis = window.compute_window(NOW, last_run=last)
        self.assertEqual(start, last)
        self.assertEqual(basis, "since last run")

    def test_old_last_run_is_capped_at_seven_days(self):
        start, _, basis = window.compute_window(NOW, last_run=parse_ts("2026-09-01T00:00:00Z"))
        self.assertEqual(start, WEEK_AGO)
        self.assertIn("last run was earlier", basis)

    def test_future_last_run_is_ignored(self):
        start, _, basis = window.compute_window(NOW, last_run=NOW + timedelta(hours=1))
        self.assertEqual(start, WEEK_AGO)
        self.assertIn("future", basis)

    def test_requested_days_override_the_last_run(self):
        last = parse_ts("2026-10-09T06:00:00Z")
        start, _, basis = window.compute_window(NOW, last_run=last, days=3)
        self.assertEqual(start, NOW - timedelta(days=3))
        self.assertIn("requested", basis)

    def test_requested_days_above_the_cap_are_clamped(self):
        start, _, basis = window.compute_window(NOW, days=30)
        self.assertEqual(start, WEEK_AGO)
        self.assertIn("limit", basis)

    def test_requested_days_below_one_are_clamped(self):
        start, _, _ = window.compute_window(NOW, days=0)
        self.assertEqual(start, NOW - timedelta(days=1))

    def test_label(self):
        self.assertEqual(window.label(parse_ts("2026-10-03T06:00:00Z"), NOW), "3 Oct to 10 Oct")


class TestReadLastRun(unittest.TestCase):
    def _state(self, text):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "state.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_missing_file(self):
        self.assertIsNone(read_last_run("/nonexistent/state.json"))

    def test_corrupt_file(self):
        self.assertIsNone(read_last_run(self._state("{not json")))

    def test_empty_file(self):
        self.assertIsNone(read_last_run(self._state("")))

    def test_wrong_shape(self):
        self.assertIsNone(read_last_run(self._state('{"last_run": 12}')))

    def test_valid(self):
        path = self._state('{"last_run": "2026-10-07T06:00:00Z"}')
        self.assertEqual(read_last_run(path), parse_ts("2026-10-07T06:00:00Z"))


class TestMain(unittest.TestCase):
    def _run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            window.main(list(argv))
        return json.loads(out.getvalue())

    def test_short_window_reports_hours(self):
        got = self._run("--now", "2026-10-10T06:00:00Z", "--last-run", "2026-10-10T05:30:00Z",
                        "--state", "/nonexistent/state.json")
        self.assertEqual(got["hours"], 0.5)
        self.assertEqual(got["start"], "2026-10-10T05:30:00Z")
        self.assertEqual(got["basis"], "since last run")

    def test_corrupt_state_falls_back_to_seven_days(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "state.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("garbage")
        got = self._run("--now", "2026-10-10T06:00:00Z", "--state", path)
        self.assertEqual(got["start"], "2026-10-03T06:00:00Z")
        self.assertEqual(got["label"], "3 Oct to 10 Oct")
        self.assertEqual(got["hours"], 168.0)


if __name__ == "__main__":
    unittest.main()
