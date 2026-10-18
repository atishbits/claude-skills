import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import freshness  # noqa: E402

NOTE = """# TESTCO — Test Company

**Research:**
- consensus: avg TP ₹1,000, 8 of 10 post-result — https://example.com/a — as of 2026-10-01
- guidance: FY27 revenue +15% — https://example.com/b — as of 2026-08-10, until 2026-11-14
- peers: EXAMPLEA P/E 30, EXAMPLEB P/E 25 — as of 2026-06-01
- recheck: ₹900 (200 DMA) — as of 2026-10-01

**Notes:** text
"""


class TestFreshness(unittest.TestCase):
    def test_parse_reads_all_items(self):
        r = freshness.parse_research(NOTE)
        self.assertEqual(set(r), set(freshness.ITEMS))
        self.assertEqual(r["guidance"]["until"], "2026-11-14")
        self.assertEqual(r["consensus"]["as_of"], "2026-10-01")
        self.assertIn("avg TP", r["consensus"]["value"])

    def test_assess_applies_windows(self):
        a = freshness.assess(freshness.parse_research(NOTE), date(2026, 10, 18))
        self.assertEqual(a["consensus"]["status"], "fresh")
        self.assertEqual(a["consensus"]["age_days"], 17)
        self.assertEqual(a["guidance"]["status"], "fresh")
        self.assertEqual(a["peers"]["status"], "due")       # 139 days
        self.assertEqual(a["recheck"]["status"], "info")

    def test_guidance_due_after_until(self):
        a = freshness.assess(freshness.parse_research(NOTE), date(2026, 11, 15))
        self.assertEqual(a["guidance"]["status"], "due")

    def test_consensus_due_at_31_days(self):
        a = freshness.assess(freshness.parse_research(NOTE), date(2026, 11, 1))
        self.assertEqual(a["consensus"]["status"], "due")

    def test_note_without_block_is_all_due(self):
        a = freshness.assess(freshness.parse_research("# X\n**Notes:** y\n"), date(2026, 10, 18))
        self.assertEqual({v["status"] for k, v in a.items() if k != "recheck"}, {"due"})
        self.assertEqual(a["recheck"]["status"], "due")

    def test_lines_outside_block_are_ignored(self):
        text = "- consensus: stray — as of 2026-10-17\n" + "# X\n"
        self.assertEqual(freshness.parse_research(text), {})


if __name__ == "__main__":
    unittest.main()
