import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import glossary  # noqa: E402


class TestGlossaryTable(unittest.TestCase):
    def test_labels_are_unique(self):
        labels = [g[0] for g in glossary.GLOSSARY]
        self.assertEqual(len(labels), len(set(labels)))

    def test_every_entry_is_complete_and_compiles(self):
        for label, full, line, pattern in glossary.GLOSSARY:
            self.assertTrue(label and full and line, label)
            self.assertFalse(line.endswith("."), f"{label}: render() adds the full stop")
            re.compile(pattern)

    def test_case_insensitive_names_exist(self):
        labels = {g[0] for g in glossary.GLOSSARY}
        self.assertTrue(glossary.CASE_INSENSITIVE <= labels)


class TestTermsIn(unittest.TestCase):
    def test_finds_scorecard_terms(self):
        found = glossary.terms_in("P/E 34.2x (run-rate 25.0x), ROE 14.4%, ROCE 18.4%, avg TP ₹396")
        self.assertEqual(found, ["P/E", "Run-rate P/E", "TP", "ROE", "ROCE"])

    def test_dma_with_and_without_space(self):
        self.assertIn("DMA", glossary.terms_in("-8.6% vs 200DMA"))
        self.assertIn("DMA", glossary.terms_in("below its 50 DMA"))

    def test_ebitda_does_not_also_fire_ebit(self):
        found = glossary.terms_in("EBITDA margin 9-10%")
        self.assertIn("EBITDA", found)
        self.assertNotIn("EBIT", found)

    def test_acronyms_are_case_sensitive(self):
        self.assertEqual(glossary.terms_in("a pat on the back, tp roll, cr"), [])

    def test_ordinary_words_match_any_case(self):
        self.assertIn("Promoters", glossary.terms_in("Promoters 53.2%"))
        self.assertIn("Beta", glossary.terms_in("Beta 0.75"))

    def test_fy_and_quarter_labels(self):
        found = glossary.terms_in("Q2 FY27 result")
        self.assertIn("FY", found)
        self.assertIn("Q1-Q4", found)

    def test_percentage_points_needs_a_number(self):
        self.assertIn("pp", glossary.terms_in("FIIs 12.0% (-1.8pp)"))
        self.assertNotIn("pp", glossary.terms_in("see the app pp list"))

    def test_plain_prose_finds_nothing(self):
        self.assertEqual(glossary.terms_in("The price fell a little this week."), [])


class TestResolveTerms(unittest.TestCase):
    def test_free_typed_names(self):
        labels, unknown = glossary.resolve_terms(["rsi", " EBITDA margin ", "200 DMA", ""])
        self.assertEqual(labels, ["RSI", "EBITDA", "DMA"])
        self.assertEqual(unknown, [])

    def test_unknown_is_reported_not_dropped(self):
        labels, unknown = glossary.resolve_terms(["ROE", "zzgibberish"])
        self.assertEqual(labels, ["ROE"])
        self.assertEqual(unknown, ["zzgibberish"])


class TestRender(unittest.TestCase):
    def test_glossary_order_and_no_duplicates(self):
        out = glossary.render(["RSI", "P/E", "RSI"])
        lines = out.splitlines()
        self.assertEqual(lines[0], "**Terms used**")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith("- **P/E** (price-to-earnings ratio): "))
        self.assertTrue(lines[2].startswith("- **RSI** (relative strength index): "))
        self.assertTrue(lines[2].endswith("."))

    def test_empty_when_nothing_matches(self):
        self.assertEqual(glossary.render([]), "")


if __name__ == "__main__":
    unittest.main()
