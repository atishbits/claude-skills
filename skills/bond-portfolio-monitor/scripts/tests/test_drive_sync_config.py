"""bond-portfolio-monitor's drive-sync.json: the skill's state, what a session
with a browser pulled from the platform, and the saved runs all go both ways.
The sync logic itself is tested with the master copy in shared/scripts/tests."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402
import drive_sync as ds  # noqa: E402
import fy_interest  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "drive-sync.json")


class TestBondConfig(unittest.TestCase):
    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(CONFIG))

    def tearDown(self):
        ds.configure(self._saved)

    def test_kinds(self):
        cases = {
            "state": ["profile.json", "notes.md", "skill-data/bond-facts.json",
                      "skill-data/ratings-ledger.jsonl", "skill-data/PORTFOLIO.md",
                      "skill-data/POSITIONS.md", "skill-data/" + fy_interest.OUT_NAME,
                      "skill-data/bonds/issuer-a.md", "notes.conflict-2026-12-01.md",
                      "skill-data/bonds/issuer-a.conflict-2026-12-01.md"],
            "pulled": ["holdings-report-2026-12-01.xlsx", "bond-listings-2026-12-01T05-00-00-000Z.json",
                       "skill-data/snapshot-2026-12-01.json", "skill-data/listings-20261201T0500.json"],
            "run": ["skill-data/runs/2026-12-01/analysis.md", "skill-data/runs/2026-12-01/REVIEW.md"],
        }
        for kind, rels in cases.items():
            for rel in rels:
                with self.subTest(rel=rel):
                    self.assertEqual(ds.scope_of(rel), kind)
                    self.assertTrue(ds.uploads(rel))

    def test_not_synced(self):
        for rel in ("Platform_Master_Report_9876543210.xlsx", "statement.pdf",
                    "skill-data/bond-facts.json.bak-before-key-rename",
                    ".sync-base.json", "bond-portfolio-monitor-sync.json",
                    "skill-data/runs/2026-12-01/deep/x.json"):
            with self.subTest(rel=rel):
                self.assertFalse(ds.synced(rel))

    def test_a_report_uploads_as_a_spreadsheet(self):
        base = {"root_id": "R0", "folders": {"": "R0"}, "files": {}}
        out = ds.plan({"holdings-report-2026-12-01.xlsx": "x"}, {}, base, {}, "all", [])
        self.assertEqual(out["upload"][0]["mime"], ds.MIME[".xlsx"])

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "bond-portfolio-monitor-sync.json")
        self.assertEqual(ds.CFG["root_env"], common.ROOT_ENV)
        self.assertEqual(ds.CFG["data_dir"], "data")


if __name__ == "__main__":
    unittest.main()
