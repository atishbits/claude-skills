"""my-spendings' drive-sync.json. The sync logic itself is tested with the
master copy in shared/scripts/tests."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402
import drive_sync as ds  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "drive-sync.json")


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(CONFIG))

    def tearDown(self):
        ds.configure(self._saved)

    def test_kinds_both_ways(self):
        cases = {
            "state": ["profile.json", "notes.md", "accounts.json", "rules.csv", "holdings.csv",
                      "adapters/bank-a.json", "offers/fuel-card.json", "cards/current.json",
                      "notes.conflict-2026-12-01.md"],
            "run": ["skill-data/analysis-2026-10-25.json", "skill-data/REPORT-2026-10-25.md"],
        }
        for kind, rels in cases.items():
            for rel in rels:
                with self.subTest(rel=rel):
                    self.assertEqual(ds.scope_of(rel), kind)
                    self.assertTrue(ds.uploads(rel))

    def test_statements_download_only(self):
        for rel in ("raw/bank-2026-10.pdf", "raw/bank-2026-10.xls", "raw/card.csv"):
            with self.subTest(rel=rel):
                self.assertEqual(ds.scope_of(rel), "statement")
                self.assertFalse(ds.uploads(rel))

    def test_not_synced(self):
        for rel in ("skill-data/ledger.csv", "skill-data/coverage.json", ".sync-base.json",
                    "my-spendings-sync.json", "vendor/xlrd/__init__.py"):
            with self.subTest(rel=rel):
                self.assertFalse(ds.synced(rel))

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "my-spendings-sync.json")
        self.assertEqual(ds.CFG["root_env"], common.ROOT_ENV)
        self.assertEqual(ds.CFG["data_dir"], "data")


if __name__ == "__main__":
    unittest.main()
