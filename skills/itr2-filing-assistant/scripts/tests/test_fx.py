"""Unit tests for fx.py. Run from scripts/:

    python3 -m unittest discover -s tests -p 'test_*.py'
"""
import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fx  # noqa: E402


class RateDateTest(unittest.TestCase):
    def test_rule115_is_last_day_of_previous_month(self):
        self.assertEqual(fx.rate_date("rule115", dt.date(2025, 11, 14)),
                         dt.date(2025, 10, 31))

    def test_rule128_crosses_year_end(self):
        self.assertEqual(fx.rate_date("rule128", dt.date(2026, 1, 5)),
                         dt.date(2025, 12, 31))

    def test_rule115_on_first_of_month(self):
        self.assertEqual(fx.rate_date("rule115", dt.date(2024, 3, 1)),
                         dt.date(2024, 2, 29))

    def test_fa_closing_is_31_december(self):
        self.assertEqual(fx.rate_date("fa-closing", dt.date(2025, 6, 30)),
                         dt.date(2025, 12, 31))

    def test_fa_peak_and_initial_use_event_date(self):
        d = dt.date(2025, 8, 12)
        self.assertEqual(fx.rate_date("fa-peak", d), d)
        self.assertEqual(fx.rate_date("fa-initial", d), d)


class MainTest(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fx.main(list(argv))
        return code, out.getvalue()

    def test_no_rate_refuses_to_guess(self):
        code, out = self.run_main("--amount", "1000", "--date", "2025-11-14",
                                  "--basis", "rule115")
        self.assertEqual(code, 1)
        self.assertIn("2025-10-31", out)

    def test_converts_with_supplied_rate(self):
        code, out = self.run_main("--amount", "1000", "--date", "2025-11-14",
                                  "--basis", "rule115", "--rate", "80")
        self.assertEqual(code, 0)
        self.assertIn("Rs 80,000.00", out)

    def test_reads_rate_for_required_date_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rates.json")
            with open(path, "w") as fh:
                json.dump({"USD": {"2025-10-31": 80.0,
                                   "2025-11-14": 99.0}}, fh)
            self.assertEqual(
                fx.load_rate(path, "usd", dt.date(2025, 10, 31)), 80.0)
            self.assertIsNone(
                fx.load_rate(path, "EUR", dt.date(2025, 10, 31)))
            code, out = self.run_main("--amount", "1000", "--date",
                                      "2025-11-14", "--basis", "rule115",
                                      "--rates", path)
        self.assertEqual(code, 0)
        self.assertIn("Rs 80,000.00", out)

    def test_bad_date(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self.run_main("--amount", "1", "--date", "14/11/2025",
                                    "--basis", "rule115")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
