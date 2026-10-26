import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lint  # noqa: E402


def luhn_complete(body):
    """body + the check digit that makes it pass Luhn. Built at runtime so no
    valid card number is ever written in this file."""
    for d in "0123456789":
        if lint.luhn_ok(body + d):
            return body + d
    raise AssertionError


def deck(*slides, **kw):
    d = {"title": "Example deck", "slides": [{"type": "title", "title": "Example deck"}] + list(slides)}
    d.update(kw)
    return d


class TestSlides(unittest.TestCase):
    def errs(self, s):
        return lint.check_slide(2, s)[0]

    def test_unknown_type_and_missing_fields(self):
        self.assertIn("unknown type", self.errs({"type": "pie", "title": "x"})[0])
        self.assertIn("needs 'items'", self.errs({"type": "bullets", "title": "x"})[0])
        self.assertIn("needs 'quote'", self.errs({"type": "quote"})[0])

    def test_title_word_cap(self):
        long = " ".join(["word"] * 15)
        self.assertTrue(any("the title" in e for e in self.errs({"type": "statement", "title": long})))
        self.assertEqual(self.errs({"type": "statement", "title": "Short **bold** title"}), [])

    def test_bullets(self):
        s = {"type": "bullets", "title": "x", "items": ["a"] * 7}
        self.assertTrue(any("7 bullets" in e for e in self.errs(s)))
        s = {"type": "bullets", "title": "x", "items": [" ".join(["w"] * 17)]}
        self.assertTrue(any("bullet" in e for e in self.errs(s)))

    def test_data_slides_need_source(self):
        s = {"type": "bars", "title": "x", "items": [{"label": "A", "value": 1}]}
        self.assertTrue(any("source" in e for e in self.errs(s)))
        s["source"] = "report"
        self.assertEqual(self.errs(s), [])

    def test_bars_need_numbers_and_no_negatives(self):
        s = {"type": "bars", "title": "x", "source": "r", "items": [{"label": "A", "value": "12"}]}
        self.assertTrue(any("numeric value" in e for e in self.errs(s)))
        s["items"] = [{"label": "A", "value": -3}]
        self.assertTrue(any("negative" in e for e in self.errs(s)))

    def test_stats(self):
        s = {"type": "stats", "title": "x", "source": "r",
             "items": [{"label": "A", "value": 1, "tone": "great"}]}
        self.assertTrue(any("tone" in e for e in self.errs(s)))
        s["items"] = [{"label": "A", "value": "₹1.2L"}]
        self.assertEqual(self.errs(s), [])
        s["items"] = [{"label": "A", "value": 1}] * 5
        self.assertTrue(any("5 stats" in e for e in self.errs(s)))

    def test_table_shape(self):
        s = {"type": "table", "title": "x", "source": "r", "columns": ["a", "b"], "rows": [[1]]}
        self.assertTrue(any("2 cells" in e for e in self.errs(s)))

    def test_compare_needs_two(self):
        s = {"type": "compare", "title": "x", "sides": [{"title": "A"}]}
        self.assertTrue(any("at least 2" in e for e in self.errs(s)))

    def test_svg_no_script(self):
        ok = {"type": "svg", "title": "x", "svg": "<svg viewBox='0 0 10 10'><rect width='5' height='5'/></svg>"}
        self.assertEqual(self.errs(ok), [])
        for bad in ("<svg><script>alert(1)</script></svg>", "<svg onload='x()'></svg>",
                    "<svg><a href='javascript:x'>a</a></svg>", "<div>no</div>"):
            with self.subTest(bad=bad):
                self.assertTrue(self.errs({"type": "svg", "title": "x", "svg": bad}))

    def test_sources_urls(self):
        s = {"type": "sources", "title": "S", "items": [{"title": "A", "url": "ftp://x"}]}
        self.assertTrue(any("http" in e for e in self.errs(s)))

    def test_slide_word_total(self):
        blocks = [{"title": "Block", "text": " ".join(["w"] * 25)} for _ in range(5)]
        e, w = lint.check_slide(2, {"type": "blocks", "title": "x", "items": blocks})
        self.assertTrue(any("words on one slide" in x for x in e))

    def test_notes_and_source_not_counted(self):
        s = {"type": "statement", "title": "Hi", "notes": " ".join(["n"] * 150),
             "source": " ".join(["s"] * 50)}
        self.assertEqual(lint.slide_words(s), 1)


class TestIdentifiers(unittest.TestCase):
    def test_card_number_full(self):
        card = luhn_complete("4" + "0" * 14)
        e, _ = lint.identifier_problems(f"Paid with {card}")
        self.assertTrue(any("card number" in x for x in e))
        spaced = " ".join(card[i:i + 4] for i in range(0, 16, 4))
        self.assertTrue(lint.identifier_problems(spaced)[0])

    def test_non_luhn_digits_pass(self):
        card = luhn_complete("4" + "0" * 14)
        wrong = card[:-1] + str((int(card[-1]) + 1) % 10)
        e, w = lint.identifier_problems(wrong)
        self.assertEqual(e, [])
        self.assertTrue(w)  # still a long digit run: flagged as a possible account number

    def test_masked(self):
        for text in ("XXXX XXXX XXXX 1234", "card XX9876", "**** **** **** 4321", "4000" + "X" * 8 + "1111"):
            with self.subTest(text=text):
                self.assertTrue(lint.identifier_problems(text)[0])

    def test_bold_year_is_fine(self):
        self.assertEqual(lint.identifier_problems("**2026** was a big year"), ([], []))

    def test_pan_and_aadhaar(self):
        pan = "ABCDE" + "1234" + "F"
        self.assertTrue(lint.identifier_problems(f"PAN {pan}")[0])
        aad = "2345" + " " + "6789" + " " + "0123"
        self.assertTrue(lint.identifier_problems(aad)[0])

    def test_amounts_and_dates_are_fine(self):
        for text in ("₹12,34,567", "2026-10-25", "1,00,000 a year", "41.3%", "Q3 FY26"):
            with self.subTest(text=text):
                self.assertEqual(lint.identifier_problems(text), ([], []))

    def test_url_ids_not_warned(self):
        self.assertEqual(lint.identifier_problems("https://example.com/item/1234567890123"), ([], []))


class TestDeck(unittest.TestCase):
    def test_ok(self):
        e, w = lint.check_deck(deck({"type": "statement", "title": "One idea"}))
        self.assertEqual((e, w), ([], []))

    def test_empty_and_untitled(self):
        self.assertTrue(lint.check_deck({"slides": []})[0])
        self.assertTrue(lint.check_deck({"slides": [{"type": "title", "title": "x"}]})[0])

    def test_accent(self):
        self.assertTrue(lint.check_deck(deck(accent="blue"))[0])
        self.assertEqual(lint.check_deck(deck(accent="#11aa33"))[0], [])

    def test_warnings(self):
        d = {"title": "T", "slides": [{"type": "statement", "title": "Same"},
                                      {"type": "statement", "title": "Same"}]}
        e, w = lint.check_deck(d, max_slides=1)
        self.assertEqual(e, [])
        self.assertTrue(any("not a title slide" in x for x in w))
        self.assertTrue(any("share the title" in x for x in w))
        self.assertTrue(any("2 slides" in x for x in w))

    def test_identifier_anywhere_blocks(self):
        d = deck({"type": "statement", "title": "Card", "notes": "from card XX4321"})
        e, _ = lint.check_deck(d)
        self.assertTrue(any("identifier" in x for x in e))


if __name__ == "__main__":
    unittest.main()
