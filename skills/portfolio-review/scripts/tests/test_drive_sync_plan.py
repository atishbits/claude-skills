import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_sync as ds  # noqa: E402

FOLDERS = {"": "R0", "skill-data": "F1", "skill-data/stocks": "F2", "skill-data/ratings-ledger": "F3"}


def rem(i, m="2026-10-18T05:00:00Z"):
    return {"id": i, "modified": m}


class TestSyncedSet(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(ds.synced("broker_holdings_2026-10-01.csv"))
        self.assertTrue(ds.synced("skill-data/stocks/TESTCO.md"))
        self.assertTrue(ds.synced("skill-data/ratings-ledger/2026-10-18-abcdef.jsonl"))
        self.assertFalse(ds.synced("skill-data/snapshot-2026-10-18.json"))
        self.assertFalse(ds.synced("skill-data/.cache/x.json"))
        self.assertFalse(ds.synced("notes.md"))
        self.assertFalse(ds.synced(".sync-base.json"))
        self.assertTrue(ds.synced("skill-data/calendar.conflict-2026-10-18.md"))


class TestListings(unittest.TestCase):
    def test_paths_from_parent_ids_and_new_folders(self):
        pages = [{"files": [
            {"id": "F4", "title": "scan-history", "parentId": "F1",
             "mimeType": "application/vnd.google-apps.folder", "modifiedTime": "t"},
            {"id": "a", "title": "TESTCO.md", "parentId": "F2", "mimeType": "text/markdown",
             "modifiedTime": "2026-10-18T05:00:00Z"}]},
            {"files": [{"id": "a", "title": "TESTCO.md", "parentId": "F2", "mimeType": "text/markdown",
                        "modifiedTime": "2026-10-18T05:00:00Z"},
                       {"id": "b", "title": "x.jsonl", "parentId": "F4", "mimeType": "text/plain",
                        "modifiedTime": "t2"}]}]
        files, folders = ds.parse_listings(pages, dict(FOLDERS))
        self.assertEqual(folders["skill-data/scan-history"], "F4")
        self.assertEqual(files["skill-data/stocks/TESTCO.md"], rem("a"))
        self.assertEqual(files["skill-data/scan-history/x.jsonl"]["id"], "b")
        self.assertEqual(len(files), 2)

    def test_unknown_parent_ignored(self):
        files, _ = ds.parse_listings([{"files": [{"id": "z", "title": "y.md", "parentId": "ZZ",
                                                   "mimeType": "text/markdown", "modifiedTime": "t"}]}],
                                     dict(FOLDERS))
        self.assertEqual(files, {})


class TestPlan(unittest.TestCase):
    def p(self, local, remote, base=None, manifest=None, scope="all", tickers=(), mtimes=None):
        return ds.plan(local, remote, {"root_id": "R0", "folders": dict(FOLDERS), "files": base or {}},
                       manifest or {}, scope, list(tickers), local_mtimes=mtimes or {},
                       today="2026-10-18")

    N = "skill-data/stocks/TESTCO.md"

    def test_local_only_uploads_new(self):
        out = self.p({self.N: "s1"}, {})
        self.assertEqual(out["upload"], [{"path": self.N, "old_id": None, "parent": "F2",
                                          "mime": "text/markdown"}])

    def test_missing_folder_needs_mkdir_first(self):
        path = "skill-data/scan-history/2026-10-18-abcdef.jsonl"
        out = self.p({path: "s1"}, {})
        self.assertEqual(out["mkdir"], [{"path": "skill-data/scan-history", "parent": "F1"}])
        self.assertEqual(out["upload"], [])

    def test_remote_only_downloads_when_in_scope(self):
        self.assertEqual(self.p({}, {self.N: rem("a")})["download"][0]["id"], "a")

    def test_cold_ticker_scope_ignores_other_notes(self):
        other = "skill-data/stocks/EXAMPLEA.md"
        out = self.p({}, {self.N: rem("a"), other: rem("b"), "skill-data/digest.json": rem("d")},
                     scope="ticker", tickers=["TESTCO"])
        self.assertEqual(sorted(d["path"] for d in out["download"]), ["skill-data/digest.json", self.N])
        self.assertEqual(out["upload"], [])

    def test_identical_by_manifest_hash_is_adopted(self):
        out = self.p({self.N: "s1"}, {self.N: rem("a")}, manifest={self.N: {"sha": "s1", "id": "a",
                                                              "modified": "2026-10-18T05:00:00Z"}})
        self.assertEqual(out["adopt"], [{"path": self.N, "id": "a", "modified": "2026-10-18T05:00:00Z"}])

    def test_unchanged(self):
        base = {self.N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}
        out = self.p({self.N: "s1"}, {self.N: rem("a")}, base=base)
        self.assertEqual(out["unchanged"], [self.N])

    def test_local_edit_replaces_remote(self):
        base = {self.N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}
        out = self.p({self.N: "s2"}, {self.N: rem("a")}, base=base)
        self.assertEqual(out["upload"][0]["old_id"], "a")

    def test_hand_edit_in_cloud_downloads(self):
        base = {self.N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}
        out = self.p({self.N: "s1"}, {self.N: rem("a", "2026-10-18T09:00:00Z")}, base=base,
                     manifest={self.N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}})
        self.assertEqual([d["path"] for d in out["download"]], [self.N])
        self.assertEqual(out["upload"], [])

    def test_both_changed_is_conflict_newer_wins(self):
        base = {self.N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}
        out = self.p({self.N: "s2"}, {self.N: rem("b", "2026-10-18T09:00:00Z")}, base=base,
                     mtimes={self.N: "2026-10-18T07:00:00Z"})
        c = out["conflict"][0]
        self.assertEqual((c["keep"], c["id"]), ("remote", "b"))
        self.assertEqual(c["copy"], "skill-data/stocks/TESTCO.conflict-2026-10-18.md")
        out = self.p({self.N: "s2"}, {self.N: rem("b", "2026-10-18T06:00:00Z")}, base=base,
                     mtimes={self.N: "2026-10-18T07:00:00Z"})
        self.assertEqual(out["conflict"][0]["keep"], "local")


if __name__ == "__main__":
    unittest.main()
