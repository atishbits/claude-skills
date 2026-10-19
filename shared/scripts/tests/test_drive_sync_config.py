"""The config-driven parts: what a skill's drive-sync.json controls."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_sync as ds  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixture-config.json")

# A working folder that is the synced folder itself, with documents that only
# ever come down from the cloud.
DOCS = {
    "marker": "example-sync.json",
    "root_env": "EXAMPLE_ROOT",
    "data_dir": ".",
    "kinds": {
        "work": {"patterns": ["RESULT_*.md", "*.conflict-*"]},
        "document": {"patterns": ["*.pdf", "*.json"], "upload": False},
    },
}


class WithConfig(unittest.TestCase):
    cfg = DOCS

    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(self.write_config(self.cfg)))

    def tearDown(self):
        ds.configure(self._saved)

    def write_config(self, cfg):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = os.path.join(self.tmp.name, "drive-sync.json")
        with open(path, "w") as fh:
            json.dump(cfg, fh)
        return path


class TestLoadConfig(unittest.TestCase):
    def write(self, cfg):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "c.json")
        with open(path, "w") as fh:
            json.dump(cfg, fh)
        return path

    def test_marker_and_kinds_are_required(self):
        with self.assertRaises(ValueError):
            ds.load_config(self.write({"kinds": {}}))
        with self.assertRaises(ValueError):
            ds.load_config(self.write({"marker": "m.json"}))

    def test_scope_naming_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            ds.load_config(self.write({"marker": "m", "kinds": {"a": {"patterns": ["*"]}},
                                       "scopes": {"s": ["b:named"]}}))

    def test_defaults(self):
        cfg = ds.load_config(self.write({"marker": "m", "kinds": {}}))
        self.assertEqual((cfg["data_dir"], cfg["root_env"], cfg["scopes"]), (".", None, {}))


class TestKinds(WithConfig):
    def test_first_matching_kind_wins_and_hidden_files_never_sync(self):
        self.assertEqual(ds.scope_of("RESULT_salary.md"), "work")
        self.assertEqual(ds.scope_of("form16.pdf"), "document")
        self.assertEqual(ds.scope_of("statement.json"), "document")
        self.assertIsNone(ds.scope_of(".sync-base.json"))
        self.assertIsNone(ds.scope_of(".listing-1.json"))
        self.assertIsNone(ds.scope_of("sub/form16.pdf"))  # depth must match

    def test_the_manifest_is_never_a_synced_file(self):
        self.assertEqual(ds.scope_of("other-sync.json"), "document")
        self.assertIsNone(ds.scope_of("example-sync.json"))

    def test_download_only_kind_is_never_uploaded(self):
        base = {"root_id": "R0", "folders": {"": "R0"},
                "files": {"form16.pdf": {"sha": "s1", "id": "d", "modified": "t"}}}
        out = ds.plan({"new.pdf": "x", "form16.pdf": "s2", "RESULT_a.md": "y"},
                      {"form16.pdf": {"id": "d", "modified": "t"}}, base, {}, "all", [])
        self.assertEqual([u["path"] for u in out["upload"]], ["RESULT_a.md"])
        self.assertEqual(sorted(out["local_only"]), ["form16.pdf", "new.pdf"])

    def test_download_only_kind_still_downloads(self):
        out = ds.plan({}, {"ais.pdf": {"id": "p", "modified": "t"}},
                      {"root_id": "R0", "folders": {"": "R0"}, "files": {}}, {}, "all", [])
        self.assertEqual([d["path"] for d in out["download"]], ["ais.pdf"])


class TestDirection(WithConfig):
    def plan(self, direction):
        out = ds.plan({"RESULT_a.md": "x"}, {"ais.pdf": {"id": "p", "modified": "t"}},
                      {"root_id": "R0", "folders": {"": "R0"}, "files": {}}, {}, "all", [])
        return ds.by_direction(out, direction)

    def test_down_drops_uploads(self):
        out = self.plan("down")
        self.assertEqual((len(out["download"]), out["upload"]), (1, []))

    def test_up_drops_downloads(self):
        out = self.plan("up")
        self.assertEqual((out["download"], len(out["upload"])), ([], 1))

    def test_both_keeps_everything(self):
        out = self.plan("both")
        self.assertEqual((len(out["download"]), len(out["upload"])), (1, 1))


class TestRoot(WithConfig):
    def test_root_flag_and_data_dir_dot(self):
        work = os.path.join(self.tmp.name, "work")
        os.makedirs(work)
        with open(os.path.join(work, "RESULT_a.md"), "w") as fh:
            fh.write("x")
        ds.main(["--root", work, "init", "--root-id", "R0"])
        self.assertTrue(os.path.exists(os.path.join(work, ".sync-base.json")))
        out = ds.main(["--root", work, "plan", "--listing", self.empty_listing(), "--direction", "up"])
        self.assertEqual([u["path"] for u in out["upload"]], ["RESULT_a.md"])
        self.assertEqual(ds.main(["--root", work, "manifest"])["name"], "example-sync.json")

    def test_root_env_variable(self):
        work = os.path.join(self.tmp.name, "env-work")
        os.makedirs(work)
        os.environ["EXAMPLE_ROOT"] = work
        self.addCleanup(os.environ.pop, "EXAMPLE_ROOT")
        ds.main(["init", "--root-id", "R0"])
        self.assertTrue(os.path.exists(os.path.join(work, ".sync-base.json")))

    def test_unknown_scope_is_refused(self):
        with self.assertRaises(SystemExit):
            ds.main(["--root", self.tmp.name, "plan", "--scope", "ticker"])

    def empty_listing(self):
        path = os.path.join(self.tmp.name, "l.json")
        with open(path, "w") as fh:
            json.dump({"files": []}, fh)
        return path


class TestNamedScope(unittest.TestCase):
    """The fixture's ticker scope: shared files plus only the named notes."""

    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(FIXTURE))

    def tearDown(self):
        ds.configure(self._saved)

    def test_named_matches_case_insensitively_before_the_first_dot(self):
        self.assertTrue(ds.in_scope("skill-data/stocks/TESTCO.md", "ticker", ["testco"]))
        self.assertFalse(ds.in_scope("skill-data/stocks/EXAMPLEA.md", "ticker", ["testco"]))
        self.assertTrue(ds.in_scope("skill-data/calendar.md", "ticker", []))
        self.assertFalse(ds.in_scope("skill-data/scan-history/x.jsonl", "ticker", []))
        self.assertTrue(ds.in_scope("skill-data/scan-history/x.jsonl", "all", []))


if __name__ == "__main__":
    unittest.main()
