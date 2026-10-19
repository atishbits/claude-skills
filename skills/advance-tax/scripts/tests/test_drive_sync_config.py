"""advance-tax's drive-sync.json: the skill's state goes both ways, nothing
else in the working folder moves. The sync logic itself is tested with the
master copy in shared/scripts/tests."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import compute_advance_tax as cat  # noqa: E402
import drive_sync as ds  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "drive-sync.json")


class TestAdvanceTaxConfig(unittest.TestCase):
    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(CONFIG))

    def tearDown(self):
        ds.configure(self._saved)

    def test_state_goes_both_ways(self):
        for rel in (*cat.STATE_FILES, "ledger.conflict-2026-12-01.md",
                    "tax-profile.conflict-2026-12-01.json"):
            with self.subTest(rel=rel):
                self.assertEqual(ds.scope_of(rel), "state")
                self.assertTrue(ds.uploads(rel))

    def test_not_synced(self):
        for rel in ("advanceTax.xlsx", "backups/advanceTax.BACKUP-20260101.xlsx",
                    "backups/ledger.md", ".sync-base.json", ".listing-1.json",
                    ".manifest-in.json", "advance-tax-sync.json", "other.json"):
            with self.subTest(rel=rel):
                self.assertFalse(ds.synced(rel))

    def test_pull_then_push(self):
        base = {"root_id": "R0", "folders": {"": "R0"}, "files": {}}
        local = {"notes.md": "x"}
        remote = {"ledger.md": {"id": "l", "modified": "2026-12-01T00:00:00Z"}}
        pull = ds.by_direction(ds.plan(local, remote, base, {}, "all", []), "down")
        self.assertEqual([d["path"] for d in pull["download"]], ["ledger.md"])
        self.assertEqual(pull["upload"], [])
        push = ds.by_direction(ds.plan(local, remote, base, {}, "all", []), "up")
        self.assertEqual([u["path"] for u in push["upload"]], ["notes.md"])
        self.assertEqual(push["download"], [])

    def test_local_scan_skips_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("ledger.md", "advanceTax.xlsx", "backups/old.xlsx", ".sync-base.json"):
                os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(d, rel), "w") as f:
                    f.write("x")
            self.assertEqual(sorted(ds.local_files(d)), ["ledger.md"])

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "advance-tax-sync.json")
        self.assertEqual(ds.CFG["root_env"], cat.DIR_ENV)
        self.assertEqual(ds.CFG["data_dir"], ".")


if __name__ == "__main__":
    unittest.main()
