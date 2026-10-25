"""mutual-fund-review's drive-sync.json. The sync logic itself is tested with
the master copy in shared/scripts/tests."""
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
            "state": ["profile.json", "notes.md", "fds.csv", "adapters/portal-a.json",
                      "skill-data/fund-meta.json", "skill-data/PORTFOLIO.md",
                      "notes.conflict-2026-12-01.md"],
            "pulled": ["raw/portal-a-capture-2026-10-25T10-00-00-000Z.json", "raw/cas-2026-10.txt",
                       "raw/manual-2026-10-25.csv", "skill-data/transactions.csv",
                       "skill-data/snapshot-2026-10-25.json"],
            "run": ["skill-data/analysis-2026-10-23.json"],
        }
        for kind, rels in cases.items():
            for rel in rels:
                with self.subTest(rel=rel):
                    self.assertEqual(ds.scope_of(rel), kind)
                    self.assertTrue(ds.uploads(rel))

    def test_statement_pdf_download_only(self):
        self.assertEqual(ds.scope_of("raw/cas-2026-10.pdf"), "statement")
        self.assertFalse(ds.uploads("raw/cas-2026-10.pdf"))

    def test_not_synced(self):
        for rel in ("skill-data/nav/120716.json", ".sync-base.json", "mutual-fund-review-sync.json",
                    "statement.pdf", "skill-data/transactions.csv.tmp"):
            with self.subTest(rel=rel):
                self.assertFalse(ds.synced(rel))

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "mutual-fund-review-sync.json")
        self.assertEqual(ds.CFG["root_env"], common.ROOT_ENV)
        self.assertEqual(ds.CFG["data_dir"], "data")


if __name__ == "__main__":
    unittest.main()
