"""portfolio-review's own drive-sync.json: what it syncs and when. The sync
logic itself is tested with the master copy in shared/scripts/tests."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive_sync as ds  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "drive-sync.json")


class TestPortfolioConfig(unittest.TestCase):
    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(CONFIG))

    def tearDown(self):
        ds.configure(self._saved)

    def test_synced_set(self):
        self.assertTrue(ds.synced("broker_holdings_2026-10-01.csv"))
        self.assertTrue(ds.synced("skill-data/stocks/TESTCO.md"))
        self.assertTrue(ds.synced("examplebroker-portfolio-2026-09-27.md"))  # same rule as fetch_fundamentals
        self.assertTrue(ds.synced("skill-data/ratings-ledger/2026-10-18-abcdef.jsonl"))
        self.assertTrue(ds.synced("skill-data/calendar.conflict-2026-10-18.md"))
        self.assertFalse(ds.synced("skill-data/snapshot-2026-10-18.json"))
        self.assertFalse(ds.synced("skill-data/.cache/x.json"))
        self.assertFalse(ds.synced("notes.md"))
        self.assertFalse(ds.synced(".sync-base.json"))
        self.assertFalse(ds.synced("old-data/broker_holdings_2026-09-30.csv"))  # local archive

    def test_everything_synced_can_be_uploaded(self):
        for kind in ds.CFG["kinds"].values():
            self.assertTrue(kind.get("upload", True))

    def test_scopes(self):
        note, other = "skill-data/stocks/TESTCO.md", "skill-data/stocks/EXAMPLEA.md"
        ledger = "skill-data/ratings-ledger/2026-10-01-abcdef.jsonl"
        scan = "skill-data/scan-history/2026-10-01-abcdef.jsonl"
        self.assertTrue(ds.in_scope("skill-data/digest.json", "ticker", ["TESTCO"]))
        self.assertTrue(ds.in_scope(note, "ticker", ["TESTCO"]))
        self.assertFalse(ds.in_scope(other, "ticker", ["TESTCO"]))
        self.assertFalse(ds.in_scope(ledger, "ticker", ["TESTCO"]))
        self.assertTrue(ds.in_scope(ledger, "sweep", []))
        self.assertTrue(ds.in_scope(other, "sweep", []))
        self.assertFalse(ds.in_scope(scan, "sweep", []))
        self.assertTrue(ds.in_scope(scan, "scan", []))
        self.assertFalse(ds.in_scope(note, "scan", []))

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "portfolio-review-sync.json")
        self.assertEqual((ds.CFG["root_env"], ds.CFG["data_dir"]), ("PORTFOLIO_ROOT", "data"))


if __name__ == "__main__":
    unittest.main()
