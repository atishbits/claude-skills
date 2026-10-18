import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import logdir  # noqa: E402


class TestLogdir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.logs = os.path.join(self.root, "data", "skill-data", "ratings-ledger")

    def tearDown(self):
        self.tmp.cleanup()

    def test_writer_id_is_stable_per_root(self):
        a = logdir.writer_id(self.root)
        self.assertEqual(a, logdir.writer_id(self.root))
        self.assertRegex(a, r"^[0-9a-f]{6}$")

    def test_two_roots_same_day_write_two_files(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        p1 = logdir.append(self.logs, {"ticker": "TESTCO"}, self.root, "2026-10-18")
        p2 = logdir.append(self.logs, {"ticker": "TESTCO"}, other.name, "2026-10-18")
        self.assertNotEqual(os.path.basename(p1), os.path.basename(p2))
        self.assertEqual(len(logdir.read(self.logs)), 2)

    def test_same_root_same_day_appends_to_one_file(self):
        logdir.append(self.logs, {"n": 1}, self.root, "2026-10-18")
        logdir.append(self.logs, {"n": 2}, self.root, "2026-10-18")
        self.assertEqual(len(os.listdir(self.logs)), 1)
        self.assertEqual([r["n"] for r in logdir.read(self.logs)], [1, 2])

    def test_read_includes_legacy_file_and_skips_blank_lines(self):
        legacy = os.path.join(self.root, "old.jsonl")
        with open(legacy, "w") as fh:
            fh.write(json.dumps({"n": 0}) + "\n\n")
        logdir.append(self.logs, {"n": 1}, self.root, "2026-10-18")
        self.assertEqual(sorted(r["n"] for r in logdir.read(self.logs, legacy)), [0, 1])

    def test_read_missing_folder_is_empty(self):
        self.assertEqual(logdir.read(os.path.join(self.root, "nope")), [])

    def test_migrate_moves_legacy_into_folder_once(self):
        legacy = os.path.join(self.root, "old.jsonl")
        with open(legacy, "w") as fh:
            fh.write(json.dumps({"n": 0}) + "\n")
        dest = logdir.migrate(legacy, self.logs, self.root)
        self.assertFalse(os.path.exists(legacy))
        self.assertTrue(os.path.basename(dest).startswith("legacy-"))
        self.assertIsNone(logdir.migrate(legacy, self.logs, self.root))
        self.assertEqual(len(logdir.read(self.logs, legacy)), 1)


if __name__ == "__main__":
    unittest.main()
