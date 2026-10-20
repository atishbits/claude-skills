"""Where the skill keeps its data, and which input file is newest once a sync
has reset every modification time."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402


def touch(path, mtime):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    os.utime(path, (mtime, mtime))


class TestResolveRoot(unittest.TestCase):
    def test_flag_then_variable_then_working_directory(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with mock.patch.dict(os.environ, {common.ROOT_ENV: b}):
                self.assertEqual(common.resolve_root(a), os.path.abspath(a))
                self.assertEqual(common.resolve_root(), os.path.abspath(b))
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch("os.getcwd", return_value=a):
                self.assertEqual(common.resolve_root(), os.path.abspath(a))

    def test_the_skill_folder_without_data_is_refused(self):
        with tempfile.TemporaryDirectory() as skill:
            with mock.patch.object(common, "SKILL_DIR", skill), \
                    mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch("os.getcwd", return_value=skill):
                with self.assertRaises(SystemExit) as ctx:
                    common.resolve_root()
                self.assertIn(common.ROOT_ENV, str(ctx.exception))
                self.assertFalse(os.path.exists(os.path.join(skill, "data")))
                os.makedirs(os.path.join(skill, "data"))
                self.assertEqual(common.resolve_root(), os.path.abspath(skill))


class TestWhere(unittest.TestCase):
    def test_reports_the_newest_data(self):
        with tempfile.TemporaryDirectory() as root:
            sd = os.path.join(root, "data", "skill-data")
            for name in ("snapshot-2026-09-01.json", "snapshot-2026-10-04.json",
                         "listings-20261002T0629.json"):
                touch(os.path.join(sd, name), 1)
            out = common.where(root)
            self.assertEqual(out["newest_snapshot"], "snapshot-2026-10-04.json")
            self.assertEqual(out["newest_listings"], "listings-20261002T0629.json")
            self.assertFalse(out["profile"])
            self.assertEqual(out["from"], "--root")

    def test_no_folder_anywhere(self):
        with tempfile.TemporaryDirectory() as skill:
            with mock.patch.object(common, "SKILL_DIR", skill), \
                    mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(common.where(), {"root": None, "from": None, "exists": False})


class TestNewest(unittest.TestCase):
    def test_name_date(self):
        self.assertEqual(common.name_date("holdings-report-2026-10-04.xlsx"), "2026-10-04")
        self.assertEqual(common.name_date("listings-20261002T0629.json"), "2026-10-02")
        self.assertIsNone(common.name_date("report.xlsx"))
        self.assertIsNone(common.name_date("Report_98765432.xlsx"))

    def test_the_name_beats_a_fresh_download_time(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "holdings-report-2026-09-01.xlsx")
            new = os.path.join(d, "holdings-report-2026-10-04.xlsx")
            touch(new, 1_000_000)
            touch(old, 9_000_000)
            self.assertEqual(common.newest_by_name_date([old, new]), new)

    def test_same_day_captures_order_by_their_time(self):
        with tempfile.TemporaryDirectory() as d:
            early = os.path.join(d, "bond-listings-2026-10-02T05-53-38-583Z.json")
            late = os.path.join(d, "bond-listings-2026-10-02T06-29-36-971Z.json")
            touch(late, 1_000_000)
            touch(early, 9_000_000)
            self.assertEqual(common.newest_by_name_date([early, late]), late)

    def test_an_undated_name_falls_back_to_its_modification_date(self):
        with tempfile.TemporaryDirectory() as d:
            dated = os.path.join(d, "holdings-report-2001-01-01.xlsx")
            undated = os.path.join(d, "report.xlsx")
            touch(dated, 1)
            touch(undated, 2_000_000_000)
            self.assertEqual(common.newest_by_name_date([dated, undated]), undated)


if __name__ == "__main__":
    unittest.main()
