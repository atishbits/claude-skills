import base64
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_sync as ds  # noqa: E402


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data)
        self.base_path = os.path.join(self.data, ".sync-base.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_writes_and_records(self):
        base = {"root_id": "R0", "folders": {"": "R0"}, "files": {}}
        b64 = base64.b64encode("hello\n".encode()).decode()
        sha = ds.put(self.data, base, "skill-data/stocks/TESTCO.md", b64, "a", "t1")
        with open(os.path.join(self.data, "skill-data", "stocks", "TESTCO.md")) as fh:
            self.assertEqual(fh.read(), "hello\n")
        self.assertEqual(base["files"]["skill-data/stocks/TESTCO.md"], {"sha": sha, "id": "a", "modified": "t1"})

    def test_put_rejects_paths_outside_synced_set(self):
        base = {"root_id": "R0", "folders": {}, "files": {}}
        with self.assertRaises(ValueError):
            ds.put(self.data, base, "../evil.md", "aGk=", "a", "t")
        with self.assertRaises(ValueError):
            ds.put(self.data, base, "skill-data/snapshot-2026-10-18.json", "aGk=", "a", "t")

    def test_put_manifest_is_not_recorded_as_a_synced_file(self):
        base = {"root_id": "R0", "folders": {}, "files": {}}
        ds.put(self.data, base, ".manifest-in.json", base64.b64encode(b"{}").decode(), "m", "t")
        self.assertTrue(os.path.exists(os.path.join(self.data, ".manifest-in.json")))
        self.assertEqual(base["files"], {})

    def test_put_tolerates_whitespace_in_base64(self):
        base = {"root_id": "R0", "folders": {}, "files": {}}
        ds.put(self.data, base, "skill-data/calendar.md", "aGVs\nbG8=\n", "a", "t")
        with open(os.path.join(self.data, "skill-data", "calendar.md")) as fh:
            self.assertEqual(fh.read(), "hello")

    def test_record_upload_and_manifest(self):
        os.makedirs(os.path.join(self.data, "skill-data"))
        with open(os.path.join(self.data, "skill-data", "calendar.md"), "w") as fh:
            fh.write("x")
        base = {"root_id": "R0", "folders": {"": "R0", "skill-data": "F1"}, "files": {}}
        ds.record_upload(self.data, base, "skill-data/calendar.md", "new", "t9")
        m = ds.build_manifest(base)
        self.assertEqual(m["schema"], 1)
        self.assertEqual(m["root_id"], "R0")
        self.assertEqual(m["folders"]["skill-data"], "F1")
        self.assertEqual(m["files"]["skill-data/calendar.md"]["id"], "new")
        self.assertEqual(m["files"]["skill-data/calendar.md"]["modified"], "t9")

    def test_listing_query_covers_every_folder(self):
        q = ds.listing_query({"": "R0", "skill-data": "F1"})
        self.assertEqual(q, "parentId = 'R0' or parentId = 'F1'")

    def test_end_to_end_plan_command(self):
        os.makedirs(os.path.join(self.data, "skill-data"))
        with open(os.path.join(self.data, "skill-data", "calendar.md"), "w") as fh:
            fh.write("x")
        ds.save_base({"root_id": "R0", "folders": {"": "R0", "skill-data": "F1"}, "files": {}},
                     self.base_path)
        listing = os.path.join(self.tmp.name, "l.json")
        with open(listing, "w") as fh:
            json.dump({"files": []}, fh)
        out = ds.main(["plan", "--listing", listing, "--scope", "all"], data_dir=self.data)
        self.assertEqual(out["upload"][0]["path"], "skill-data/calendar.md")


if __name__ == "__main__":
    unittest.main()
