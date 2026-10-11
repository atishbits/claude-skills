import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import package  # noqa: E402


def make_skill():
    root = os.path.join(tempfile.mkdtemp(), "news-briefing")
    files = ["SKILL.md", "scripts/window.py", "scripts/tests/test_window.py",
             "scripts/__pycache__/window.cpython-312.pyc", "data/profile.json", "data/api.json",
             "data/notes.md"]
    for rel in files:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
    return root


class TestBuildZip(unittest.TestCase):
    def test_bundle_has_the_skill_and_nothing_personal(self):
        out = os.path.join(tempfile.mkdtemp(), "bundle.zip")
        names = package.build_zip(make_skill(), out)
        self.assertEqual(names, ["news-briefing/SKILL.md", "news-briefing/scripts/window.py"])
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.namelist(), names)

    def test_a_symlinked_install_is_bundled_under_the_real_name(self):
        root = make_skill()
        link = os.path.join(tempfile.mkdtemp(), "alias")
        os.symlink(root, link)
        names = package.build_zip(link, os.path.join(tempfile.mkdtemp(), "bundle.zip"))
        self.assertIn("news-briefing/SKILL.md", names)

    def test_refuses_a_folder_that_is_not_a_skill(self):
        with self.assertRaises(ValueError):
            package.build_zip(tempfile.mkdtemp(), os.path.join(tempfile.mkdtemp(), "bundle.zip"))


if __name__ == "__main__":
    unittest.main()
