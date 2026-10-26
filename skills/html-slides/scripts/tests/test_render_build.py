import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build_deck  # noqa: E402
import common  # noqa: E402
import decks  # noqa: E402
import render  # noqa: E402

with open(common.TEMPLATE, encoding="utf-8") as _f:
    TEMPLATE = _f.read()
PROFILE = dict(common.DEFAULT_PROFILE)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

ALL_TYPES = {
    "title": "Example deck",
    "slides": [
        {"type": "title", "title": "Example deck", "kicker": "Brief", "subtitle": "Sub"},
        {"type": "section", "title": "Part one"},
        {"type": "statement", "title": "Costs fell ==a third=="},
        {"type": "bullets", "title": "Points", "items": ["One **bold**", "Two"]},
        {"type": "stats", "title": "Totals", "money": True, "source": "report",
         "items": [{"label": "Spent", "value": 123456, "delta": "+5%", "tone": "bad"},
                   {"label": "Rate", "value": 41.3, "format": {"suffix": "%", "prefix": ""}}]},
        {"type": "bars", "title": "By kind", "source": "report", "highlight": ["B"],
         "items": [{"label": "A", "value": 50}, {"label": "B", "value": 100}]},
        {"type": "columns", "title": "Over time", "source": "report",
         "items": [{"label": "Jan", "value": 10}, {"label": "Feb", "value": 40}]},
        {"type": "share", "title": "Split", "source": "report",
         "items": [{"label": "X", "value": 1}, {"label": "Y", "value": 1}, {"label": "Other", "value": 1}]},
        {"type": "blocks", "title": "Blocks", "items": [{"title": "A", "text": "a", "icon": "*"}]},
        {"type": "flow", "title": "Flow", "steps": [{"title": "In"}, {"title": "Out"}]},
        {"type": "layers", "title": "Stack", "layers": [{"title": "Top", "items": ["a", "b"]}]},
        {"type": "compare", "title": "Pick", "pick": 1,
         "sides": [{"title": "A", "points": ["p"]}, {"title": "B", "tag": "Pick", "points": ["q"]}]},
        {"type": "timeline", "title": "When", "events": [{"when": "Jan", "title": "Start"}]},
        {"type": "table", "title": "Table", "source": "report", "columns": ["Name", "Amount"],
         "rows": [["A", 1500], ["B", 250000]]},
        {"type": "quote", "quote": "Short quote", "by": "Someone"},
        {"type": "svg", "title": "Diagram", "svg": "<svg viewBox='0 0 10 10'><rect width='4' height='4'/></svg>"},
        {"type": "sources", "title": "Sources", "items": [{"title": "Site", "url": "https://example.com"}]},
    ],
}


class TestRender(unittest.TestCase):
    def setUp(self):
        self.html = render.render_deck(json.loads(json.dumps(ALL_TYPES)), TEMPLATE, PROFILE)

    def test_every_slide_rendered_and_placeholders_filled(self):
        self.assertEqual(self.html.count('<section class="slide t-'), len(ALL_TYPES["slides"]))
        self.assertNotIn("{{", self.html)
        self.assertIn("#2f6fde1f", self.html)  # accent soft token built from the accent

    def test_type_classes_do_not_collide_with_components(self):
        # A slide's class must never equal a component class such as .bars or .timeline.
        for t in ("bars", "timeline", "layers", "compare", "stats", "blocks", "flow"):
            self.assertNotIn(f'class="slide {t}"', self.html)

    def test_numbers_formatted_by_script(self):
        self.assertIn("₹1,23,456", self.html)
        self.assertIn("41.3%", self.html)
        self.assertIn("2,50,000", self.html)
        self.assertIn('style="width:50.0%"', self.html)
        self.assertIn('style="height:25.0%"', self.html)
        self.assertEqual(len(re.findall(r"<b>3[34]%</b>", self.html)), 3)

    def test_inline_marks(self):
        self.assertIn("<strong>bold</strong>", self.html)
        self.assertIn('<span class="em">a third</span>', self.html)

    def test_highlight_and_pick(self):
        self.assertIn('class="bar-row hl"', self.html)
        self.assertIn('class="side pick"', self.html)

    def test_links_are_safe(self):
        self.assertIn('rel="noopener noreferrer"', self.html)

    def test_escaping(self):
        d = {"title": "<b>x</b>", "slides": [{"type": "statement", "title": "<script>alert(1)</script>"}]}
        out = render.render_deck(d, TEMPLATE, PROFILE)
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("<title>&lt;b&gt;x&lt;/b&gt;</title>", out)


class TestBuild(unittest.TestCase):
    def test_build_writes_files_and_index(self):
        with tempfile.TemporaryDirectory() as root:
            p = common.paths(root)
            src = os.path.join(root, "deck.deck.json")
            d = dict(ALL_TYPES, date="2026-01-02")
            s = build_deck.build(d, {}, PROFILE, TEMPLATE, out_dir=p["decks"], index_path=p["index"],
                                 source_path=src)
            self.assertTrue(s["ok"], s["errors"])
            self.assertEqual(s["id"], "2026-01-02-example-deck")
            self.assertTrue(os.path.exists(s["html"]))
            self.assertEqual(load(s["json"])["title"], "Example deck")
            idx = load(p["index"])
            self.assertEqual(idx["decks"][0]["html"], "decks/2026-01-02-example-deck.html")
            self.assertEqual(idx["decks"][0]["source"], "../../deck.deck.json")

            # A published link survives a rebuild.
            decks.link(p["index"], "2026-01-02-example", "https://claude.ai/artifact/abc")
            build_deck.build(d, {}, PROFILE, TEMPLATE, out_dir=p["decks"], index_path=p["index"])
            idx = load(p["index"])
            self.assertEqual(len(idx["decks"]), 1)
            self.assertEqual(idx["decks"][0]["url"], "https://claude.ai/artifact/abc")

    def test_errors_write_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            out = os.path.join(root, "out")
            d = {"title": "T", "slides": [{"type": "bars", "title": "x", "items": [{"label": "A", "value": 1}]}]}
            s = build_deck.build(d, {}, PROFILE, TEMPLATE, out_dir=out)
            self.assertFalse(s["ok"])
            self.assertFalse(os.path.exists(out))

    def test_check_only(self):
        with tempfile.TemporaryDirectory() as root:
            out = os.path.join(root, "out")
            s = build_deck.build(ALL_TYPES, {}, PROFILE, TEMPLATE, check_only=True, out_dir=out)
            self.assertTrue(s["ok"])
            self.assertFalse(os.path.exists(out))

    def test_data_refs_and_cli(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "d.json"), "w") as f:
                json.dump({"cat": {"A": 10, "B": 30}}, f)
            deck = {"title": "Refs", "id": "refs", "data": {"src": "d.json"},
                    "slides": [{"type": "bars", "title": "Cats", "source": "file",
                                "items_from": {"ref": "src:cat", "sort": "desc"}}]}
            dp = os.path.join(root, "refs.deck.json")
            with open(dp, "w") as f:
                json.dump(deck, f)
            os.makedirs(os.path.join(root, "data"))
            with contextlib.redirect_stdout(io.StringIO()):
                rc = build_deck.main([dp, "--root", root])
            self.assertEqual(rc, 0)
            resolved = load(os.path.join(root, "data", "skill-data", "decks", "refs.json"))
            self.assertEqual(resolved["slides"][0]["items"][0], {"label": "B", "value": 30})
            self.assertNotIn("items_from", resolved["slides"][0])

    def test_deck_id(self):
        self.assertEqual(build_deck.deck_id({"title": "Hello, World!", "date": "2026-01-01"}),
                         "2026-01-01-hello-world")
        self.assertEqual(build_deck.deck_id({"id": "My Deck"}), "my-deck")


class TestIndex(unittest.TestCase):
    def test_link_rules(self):
        with tempfile.TemporaryDirectory() as root:
            ip = os.path.join(root, "decks.json")
            common.write_json(ip, {"decks": [{"id": "2026-01-01-a"}, {"id": "2026-01-01-b"}]})
            with self.assertRaises(ValueError):
                decks.link(ip, "2026-01-01-a", "http://insecure")
            with self.assertRaises(KeyError):
                decks.link(ip, "2026-01-01", "https://x")  # ambiguous prefix
            self.assertEqual(decks.link(ip, "2026-01-01-b", "https://x")["url"], "https://x")


if __name__ == "__main__":
    unittest.main()
