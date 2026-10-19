"""itr2-filing-assistant's drive-sync.json: the skill's own files go up,
the user's documents only come down. The sync logic itself is tested with the
master copy in shared/scripts/tests."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive_sync as ds  # noqa: E402

CONFIG = os.path.join(os.path.dirname(HERE), "drive-sync.json")


class TestItr2Config(unittest.TestCase):
    def setUp(self):
        self._saved = ds.CFG
        ds.configure(ds.load_config(CONFIG))

    def tearDown(self):
        ds.configure(self._saved)

    def test_conclusions_and_worksheet_go_up(self):
        for rel in ("00_Document_Review_and_Data_Inventory.md",
                    "ITR2_Schedule_CG_conclusions.md",
                    "ITR2_Final_Worksheet_and_Prefiling_Checklist.md",
                    "ITR2_Schedule_CG_conclusions.conflict-2026-07-01.md",
                    "sbi-tt-rates.json", "sbi-tt-rates.conflict-2026-07-01.json"):
            with self.subTest(rel=rel):
                self.assertEqual(ds.scope_of(rel), "work")
                self.assertTrue(ds.uploads(rel))

    def test_documents_only_come_down(self):
        for rel in ("form16.pdf", "ais.json", "broker/capital-gains.xlsx", "26as.conflict-2026-07-01.pdf"):
            with self.subTest(rel=rel):
                self.assertEqual(ds.scope_of(rel), "document")
                self.assertFalse(ds.uploads(rel))

    def test_not_synced(self):
        for rel in (".sync-base.json", ".listing-1.json", ".manifest-in.json", "notes.md",
                    "itr2-filing-assistant-sync.json",
                    "a/b/deep.pdf", "form16.docx"):
            with self.subTest(rel=rel):
                self.assertFalse(ds.synced(rel))

    def test_pull_and_push(self):
        base = {"root_id": "R0", "folders": {"": "R0"}, "files": {}}
        local = {"ITR2_Schedule_Salary_conclusions.md": "x", "form16.pdf": "y"}
        remote = {"ais.pdf": {"id": "p", "modified": "2026-07-01T00:00:00Z"}}
        pull = ds.by_direction(ds.plan(local, remote, base, {}, "all", []), "down")
        self.assertEqual([d["path"] for d in pull["download"]], ["ais.pdf"])
        self.assertEqual(pull["upload"], [])
        push = ds.by_direction(ds.plan(local, remote, base, {}, "all", []), "up")
        self.assertEqual([u["path"] for u in push["upload"]], ["ITR2_Schedule_Salary_conclusions.md"])
        self.assertEqual(push["download"], [])
        self.assertEqual(push["local_only"], ["form16.pdf"])

    def test_marker_and_root(self):
        self.assertEqual(ds.CFG["marker"], "itr2-filing-assistant-sync.json")
        self.assertEqual(ds.CFG["data_dir"], ".")


if __name__ == "__main__":
    unittest.main()
