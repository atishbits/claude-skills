"""Cases from the whole-branch review: cold roots, duplicates, conflict
resolution, timestamps, default file locations."""
import base64
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_sync as ds  # noqa: E402

FOLDERS = {"": "R0", "skill-data": "F1", "skill-data/stocks": "F2"}
N = "skill-data/stocks/TESTCO.md"


def page(*files):
    return {"files": [dict(f) for f in files]}


def f(i, title, parent, m="2026-10-18T05:00:00Z", mime="text/markdown"):
    return {"id": i, "title": title, "parentId": parent, "modifiedTime": m, "mimeType": mime}


def b64(text):
    return base64.b64encode(text.encode()).decode()


class Root(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        return ds.main(list(argv), data_dir=self.data)

    def write(self, rel, text):
        path = os.path.join(self.data, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def save_page(self, n, pg):
        with open(os.path.join(self.data, f".listing-{n}.json"), "w") as fh:
            json.dump(pg, fh)


class TestColdRoot(Root):
    def test_manifest_put_seeds_folders_so_the_query_lists_them(self):
        manifest = {"schema": 1, "root_id": "R0", "folders": FOLDERS, "files": {}}
        tmp = os.path.join(self.tmp.name, "m.b64")
        with open(tmp, "w") as fh:
            fh.write(b64(json.dumps(manifest)))
        self.run_cli("put", ".manifest-in.json", tmp, "--id", "M1", "--modified", "t")
        q = self.run_cli("listing-query")["query"]
        for fid in FOLDERS.values():
            self.assertIn(f"'{fid}'", q)

    def test_plan_asks_for_a_relist_when_it_finds_an_unlisted_folder(self):
        self.run_cli("init", "--root-id", "R0")
        self.save_page(1, page(f("F1", "skill-data", "R0", mime=ds.FOLDER_MIME)))
        out = self.run_cli("plan", "--scope", "all")
        self.assertEqual(out["relist"], ["F1"])
        self.assertIn("'F1'", self.run_cli("listing-query")["query"])

    def test_listing_query_clears_old_pages(self):
        self.save_page(1, page())
        self.run_cli("init", "--root-id", "R0")
        self.run_cli("listing-query")
        self.assertFalse(os.path.exists(os.path.join(self.data, ".listing-1.json")))

    def test_plan_reads_default_manifest_and_pages_from_the_data_folder(self):
        self.write(N, "same")
        sha = ds.sha256(os.path.join(self.data, N))
        manifest = {"schema": 1, "root_id": "R0", "folders": FOLDERS,
                    "files": {N: {"sha": sha, "id": "a", "modified": "2026-10-18T05:00:00Z"}}}
        with open(os.path.join(self.data, ".manifest-in.json"), "w") as fh:
            json.dump(manifest, fh)
        self.save_page(1, page(f("a", "TESTCO.md", "F2")))
        out = self.run_cli("plan", "--scope", "all")
        self.assertEqual([a["path"] for a in out["adopt"]], [N])

    def test_manifest_command_names_the_old_manifest_to_bin(self):
        tmp = os.path.join(self.tmp.name, "m.b64")
        with open(tmp, "w") as fh:
            fh.write(b64(json.dumps({"schema": 1, "root_id": "R0", "folders": {"": "R0"}, "files": {}})))
        self.run_cli("put", ".manifest-in.json", tmp, "--id", "M1", "--modified", "t")
        self.assertEqual(self.run_cli("manifest")["old_id"], "M1")


class TestDuplicates(unittest.TestCase):
    def test_newest_of_two_ids_wins_and_the_other_is_reported(self):
        files, _ = ds.parse_listings([page(f("a", "TESTCO.md", "F2", "2026-10-18T05:00:00Z"),
                                           f("b", "TESTCO.md", "F2", "2026-10-18T09:00:00Z"))],
                                     dict(FOLDERS))
        self.assertEqual(files[N]["id"], "b")
        self.assertEqual([d["id"] for d in files[N]["dups"]], ["a"])

    def test_remote_edit_in_newer_duplicate_is_downloaded(self):
        files, _ = ds.parse_listings([page(f("b", "TESTCO.md", "F2", "2026-10-18T09:00:00Z"),
                                           f("a", "TESTCO.md", "F2", "2026-10-18T05:00:00Z"))],
                                     dict(FOLDERS))
        base = {"root_id": "R0", "folders": dict(FOLDERS),
                "files": {N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}}
        out = ds.plan({N: "s1"}, files, base, {}, "all", [], today="2026-10-18")
        self.assertEqual([d["id"] for d in out["download"]], ["b"])
        self.assertEqual(out["upload"], [])
        self.assertEqual(out["duplicate"][0]["id"], "a")
        self.assertTrue(out["duplicate"][0]["copy"].startswith("skill-data/stocks/TESTCO.conflict-"))


class TestTimestamps(unittest.TestCase):
    def test_fractional_and_offset_forms_compare_equal(self):
        self.assertEqual(ds.norm_ts("2026-10-18T05:00:00.000Z"), "2026-10-18T05:00:00Z")
        self.assertEqual(ds.norm_ts("2026-10-18T10:30:00+05:30"), "2026-10-18T05:00:00Z")

    def test_upload_time_in_another_format_is_unchanged_next_run(self):
        base = {"root_id": "R0", "folders": dict(FOLDERS),
                "files": {N: {"sha": "s1", "id": "a", "modified": ds.norm_ts("2026-10-18T05:00:00.000Z")}}}
        files, _ = ds.parse_listings([page(f("a", "TESTCO.md", "F2", "2026-10-18T05:00:00Z"))], dict(FOLDERS))
        out = ds.plan({N: "s1"}, files, base, {}, "all", [], today="2026-10-18")
        self.assertEqual(out["unchanged"], [N])


class TestConflicts(Root):
    def test_keep_local_converges_to_an_upload(self):
        self.write(N, "local edit")
        ds.save_base({"root_id": "R0", "folders": dict(FOLDERS),
                      "files": {N: {"sha": "old", "id": "a", "modified": "2026-10-18T05:00:00Z"}}},
                     os.path.join(self.data, ".sync-base.json"))
        tmp = os.path.join(self.tmp.name, "r.b64")
        with open(tmp, "w") as fh:
            fh.write(b64("remote edit"))
        copy = "skill-data/stocks/TESTCO.conflict-2026-10-18.md"
        self.run_cli("put", copy, tmp, "--id", "b", "--modified", "2026-10-18T09:00:00Z")
        self.run_cli("resolve-local", N, "--id", "b", "--modified", "2026-10-18T09:00:00Z")
        self.save_page(1, page(f("b", "TESTCO.md", "F2", "2026-10-18T09:00:00Z")))
        out = self.run_cli("plan", "--scope", "all")
        self.assertEqual(out["conflict"], [])
        uploads = {u["path"]: u["old_id"] for u in out["upload"]}
        self.assertEqual(uploads, {N: "b", copy: None})

    def test_conflict_copy_names_never_collide(self):
        base = {"root_id": "R0", "folders": dict(FOLDERS),
                "files": {N: {"sha": "s1", "id": "a", "modified": "2026-10-18T05:00:00Z"}}}
        taken = "skill-data/stocks/TESTCO.conflict-2026-10-18.md"
        out = ds.plan({N: "s2", taken: "x"}, {N: {"id": "b", "modified": "2026-10-18T09:00:00Z"}},
                      base, {}, "all", [], today="2026-10-18")
        self.assertEqual(out["conflict"][0]["copy"], "skill-data/stocks/TESTCO.conflict-2026-10-18-2.md")

    def test_conflict_copy_command_refuses_to_overwrite(self):
        self.write(N, "a")
        self.write("skill-data/stocks/TESTCO.conflict-2026-10-18.md", "b")
        with self.assertRaises(ValueError):
            self.run_cli("conflict-copy", N, "skill-data/stocks/TESTCO.conflict-2026-10-18.md")


class TestUploadedSize(Root):
    def test_size_mismatch_is_refused_and_not_recorded(self):
        self.write(N, "hello")
        self.run_cli("init", "--root-id", "R0")
        with self.assertRaises(ValueError):
            self.run_cli("uploaded", N, "--id", "x", "--modified", "t", "--size", "4")
        self.assertNotIn(N, ds.load_base(os.path.join(self.data, ".sync-base.json"))["files"])

    def test_matching_size_is_recorded(self):
        self.write(N, "hello")
        self.run_cli("uploaded", N, "--id", "x", "--modified", "t", "--size", "5")
        self.assertEqual(ds.load_base(os.path.join(self.data, ".sync-base.json"))["files"][N]["id"], "x")


class TestLedgerScope(unittest.TestCase):
    def test_ledger_files_are_pulled_only_for_full_passes(self):
        path = "skill-data/ratings-ledger/2026-10-01-abcdef.jsonl"
        remote = {path: {"id": "l", "modified": "t"}}
        base = {"root_id": "R0", "folders": {}, "files": {}}
        self.assertEqual(ds.plan({}, remote, base, {}, "ticker", ["TESTCO"])["download"], [])
        self.assertEqual(len(ds.plan({}, remote, base, {}, "sweep", [])["download"]), 1)


if __name__ == "__main__":
    unittest.main()
