import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import fy_interest  # noqa: E402
import ingest  # noqa: E402
from helpers import sample_report  # noqa: E402


def snapshot():
    return ingest.build_snapshot(sample_report(), common.load_config(), "2026-10-02", "abc")


class TestFyInterest(unittest.TestCase):
    def test_year_defaults_to_the_one_the_snapshot_falls_in(self):
        out = fy_interest.fy_interest(snapshot())
        self.assertEqual((out["financial_year"], out["from"], out["to"]),
                         ("2026-27", "2026-04-01", "2027-03-31"))

    def test_received_and_scheduled_interest_are_gross_and_within_the_year(self):
        out = fy_interest.fy_interest(snapshot())
        self.assertEqual(out["received"], {"interest_gross": 200.0, "tds": 20.0})
        self.assertEqual(out["scheduled"], {"interest_gross": 650.0, "tds": 40.0})
        self.assertEqual(out["total"], {"interest_gross": 850.0, "tds": 60.0})

    def test_an_earlier_year_counts_only_its_own_payments(self):
        out = fy_interest.fy_interest(snapshot(), "2025-04-01")
        self.assertEqual(out["financial_year"], "2025-26")
        self.assertEqual(out["total"], {"interest_gross": 200.0, "tds": 20.0})

    def test_issuers_paying_without_tds_are_named(self):
        self.assertEqual(fy_interest.fy_interest(snapshot())["issuers_without_tds"],
                         ["Beta Capital"])


class TestFyInterestFile(unittest.TestCase):
    def test_main_writes_the_synced_file_and_out(self):
        with tempfile.TemporaryDirectory() as root:
            sd = common.skill_data_dir(root)
            common.write_json(os.path.join(sd, "snapshot-2026-10-02.json"), snapshot())
            extra = os.path.join(root, "elsewhere.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fy_interest.main(["--root", root, "--out", extra]), 0)
            synced = common.load_json(os.path.join(sd, fy_interest.OUT_NAME))
            self.assertEqual(synced, common.load_json(extra))
            self.assertEqual(synced["as_of"], "2026-10-02")


if __name__ == "__main__":
    unittest.main()
