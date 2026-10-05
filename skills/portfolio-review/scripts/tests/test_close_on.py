import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import close_on  # noqa: E402


class TestDailyChartFiles(unittest.TestCase):
    def test_skips_the_weekly_long_history_chart(self):
        with tempfile.TemporaryDirectory() as d:
            names = ["NEWCO-chart-2026-10-04.json", "NEWCO-chart-2026-10-05.json",
                     "NEWCO-chart-long-2026-10-05.json", "OTHER-chart-2026-10-05.json"]
            for n in names:
                open(os.path.join(d, n), "w").close()
            files = [os.path.basename(f) for f in close_on.daily_chart_files("NEWCO", d)]
            self.assertEqual(files, ["NEWCO-chart-2026-10-04.json", "NEWCO-chart-2026-10-05.json"])

    def test_empty_when_nothing_cached(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(close_on.daily_chart_files("NEWCO", d), [])


if __name__ == "__main__":
    unittest.main()
