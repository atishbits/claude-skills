import contextlib
import io
import html
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calc  # noqa: E402
import check_layout  # noqa: E402
import common  # noqa: E402
import inspect_data  # noqa: E402


class TestCalc(unittest.TestCase):
    def test_change(self):
        r = calc.change(52000, 64000)
        self.assertEqual(r["pct"], 23.08)
        self.assertEqual(r["phrase"], "up 23%")
        self.assertEqual(calc.change(100, 95)["phrase"], "down 5%")
        self.assertEqual(calc.change(100, 100)["phrase"], "flat 0%")
        self.assertIsNone(calc.change(0, 5)["pct"])

    def test_share_words(self):
        self.assertEqual(calc.share(1, 3)["phrase"], "a third (33%)")
        self.assertEqual(calc.share(12500, 18000)["phrase"], "69%")
        self.assertEqual(calc.share(1, 2)["phrase"], "half (50%)")
        with self.assertRaises(ValueError):
            calc.share(1, 0)

    def test_ratio_cagr_annual_sum(self):
        self.assertEqual(calc.ratio(30, 10)["phrase"], "3x")
        self.assertEqual(calc.cagr(100, 121, 2)["cagr_pct"], 10.0)
        with self.assertRaises(ValueError):
            calc.cagr(0, 10, 1)
        self.assertEqual(calc.annual(6250)["annual"], 75000)
        self.assertEqual(calc.total([1, 2, 3])["sum"], 6)

    def test_cli_with_refs(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w") as f:
                json.dump({"a": {"old": 10, "new": 15}}, f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(calc.main(["--data", f"s={p}", "change", "s:a.old", "s:a.new"]), 0)
                self.assertEqual(calc.main(["ratio", "1"]), 1)
            self.assertIn("up 50%", out.getvalue())


class TestInspect(unittest.TestCase):
    def test_describe(self):
        lines = inspect_data.describe({"cat": {"A": 1, "B": 2}, "rows": [{"m": "Jan"}]}, "s:", 3, [])
        self.assertIn("s:cat  mapping[2]  <- items_from ready", lines)
        self.assertIn("s:rows  list[1]", lines)
        self.assertIn("s:rows.0.m  str  'Jan'", lines)


class TestLayout(unittest.TestCase):
    def test_parse_report(self):
        rep = {"width": 390, "height": 844,
               "slides": [{"slide": 1, "overflow_px": 0, "overflow_x_px": 0},
                          {"slide": 2, "overflow_px": 120, "overflow_x_px": 0},
                          {"slide": 3, "overflow_px": 3, "overflow_x_px": 0}]}
        dom = f'<head><meta name="layout-check" content="{html.escape(json.dumps(rep))}"></head>'
        got = check_layout.parse_report(dom)
        self.assertEqual(got["width"], 390)
        self.assertEqual([s["slide"] for s in check_layout.overflowing(got)], [2])
        self.assertIsNone(check_layout.parse_report("<html></html>"))

    def test_sizes(self):
        self.assertEqual(check_layout.parse_sizes("390x844, 1366x768"), [(390, 844), (1366, 768)])
        with self.assertRaises(ValueError):
            check_layout.parse_sizes("big")

    def test_template_has_layout_hook(self):
        with open(common.TEMPLATE, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("layoutcheck=1", t)
        self.assertIn('name = \'layout-check\'', t)


class TestCommon(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(common.slugify("  Where the money went!  "), "where-the-money-went")
        self.assertEqual(common.slugify("!!!"), "deck")

    def test_profile_overlay(self):
        with tempfile.TemporaryDirectory() as root:
            common.write_json(common.paths(root)["profile"], {"accent": "#000000", "_comment": "x"})
            prof = common.load_profile(root)
            self.assertEqual(prof["accent"], "#000000")
            self.assertNotIn("_comment", prof)
            self.assertEqual(prof["number_style"], "in")

    def test_resolve_root_refuses_bare_skill_folder(self):
        if os.path.isdir(os.path.join(common.SKILL_DIR, "data")):
            self.skipTest("this checkout has a data/ folder")
        with self.assertRaises(SystemExit):
            common.resolve_root(common.SKILL_DIR)


if __name__ == "__main__":
    unittest.main()
