import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import ingest  # noqa: E402
import rating_ledger  # noqa: E402
import run_record  # noqa: E402
from helpers import ALPHA, BETA, sample_report  # noqa: E402


def entry(issuer, isin, verdict, reason, when):
    return rating_ledger.make_entry("holding", issuer, verdict, reason, {"ytm": 12.0},
                                    ["https://example.com/rationale"], snapshot_hash="a" * 64,
                                    isin=isin, when=when)


ENTRIES = [
    entry("Alpha Finance", ALPHA, "HOLD", "Rating reaffirmed.", "2026-09-01T10:00:00+00:00"),
    entry("Beta Capital", BETA, "HOLD", "Nothing new.", "2026-10-02T09:00:00+00:00"),
    entry("Alpha Finance", ALPHA, "REVIEW", "Outlook cut to negative | watch.",
          "2026-10-02T10:00:00+00:00"),
]


class TestLatestVerdicts(unittest.TestCase):
    def test_last_entry_per_bond_wins(self):
        latest = run_record.latest_verdicts(ENTRIES)
        self.assertEqual([(e["issuer"], e["verdict"]) for e in latest],
                         [("Alpha Finance", "REVIEW"), ("Beta Capital", "HOLD")])


class TestSyncNotes(unittest.TestCase):
    def test_creates_a_note_with_the_verdict_history_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            run_record.sync_notes(d, ENTRIES)
            text = open(os.path.join(d, "alpha-finance.md"), encoding="utf-8").read()
            self.assertTrue(text.startswith("# Alpha Finance\n"))
            self.assertLess(text.index("REVIEW"), text.index("HOLD"))
            self.assertIn("Outlook cut to negative / watch.", text)  # a pipe cannot break the table
            self.assertTrue(os.path.exists(os.path.join(d, "beta-capital.md")))

    def test_replaces_only_its_own_block_and_keeps_what_was_written(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "alpha-finance.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# Alpha Finance\n\n## Credit read\nHand-written analysis stays.\n")
            run_record.sync_notes(d, ENTRIES[:1])
            run_record.sync_notes(d, ENTRIES)
            text = open(path, encoding="utf-8").read()
            self.assertIn("Hand-written analysis stays.", text)
            self.assertEqual(text.count(run_record.START), 1)
            self.assertEqual(text.count("Rating reaffirmed."), 1)
            self.assertIn("REVIEW", text)


class TestSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        data = common.skill_data_dir(self.root)
        common.write_json(os.path.join(self.root, "data", "profile.json"),
                          common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json")))
        common.write_json(os.path.join(data, "snapshot-2026-10-02.json"),
                          ingest.build_snapshot(sample_report(), common.load_config(),
                                                "2026-10-02", "abc"))
        for e in ENTRIES:
            rating_ledger.append(rating_ledger.ledger_path(self.root), e)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_every_output_a_review_and_the_notes(self):
        out = run_record.save(self.root, "2026-10-02")
        self.assertTrue(out.endswith(os.path.join("runs", "2026-10-02")))
        for name in ("portfolio.json", "cashflows.json", "repayment_check.json", "diff.json",
                     "screen.json", "verdicts.json", "REVIEW.md"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        self.assertEqual(common.load_json(os.path.join(out, "portfolio.json"))["totals"]
                         ["current_value"], 30000.0)
        self.assertIn("skipped", common.load_json(os.path.join(out, "screen.json")))
        self.assertIn("principal_ahead", common.load_json(os.path.join(out, "cashflows.json")))
        self.assertTrue(os.path.exists(os.path.join(self.root, "data", "skill-data", "bonds",
                                                    "alpha-finance.md")))

    def test_review_shows_breaches_verdicts_and_the_repayment_status(self):
        out = run_record.save(self.root, "2026-10-02")
        text = open(os.path.join(out, "REVIEW.md"), encoding="utf-8").read()
        self.assertIn("# Wint Wealth review, 2026-10-02", text)
        self.assertIn("Alpha Finance is 66.67% of the portfolio", text)
        self.assertIn("| Alpha Finance |", text)
        self.assertIn("REVIEW", text)
        self.assertIn("no baseline yet", text)

    def test_a_rerun_keeps_the_written_analysis(self):
        out = run_record.save(self.root, "2026-10-02")
        analysis = os.path.join(out, "analysis.md")
        with open(analysis, "w", encoding="utf-8") as fh:
            fh.write("my reading of this run\n")
        run_record.save(self.root, "2026-10-02")
        self.assertEqual(open(analysis, encoding="utf-8").read(), "my reading of this run\n")

    def test_holding_with_no_verdict_is_shown_as_such(self):
        os.remove(rating_ledger.ledger_path(self.root))
        out = run_record.save(self.root, "2026-10-02")
        text = open(os.path.join(out, "REVIEW.md"), encoding="utf-8").read()
        self.assertIn("none recorded", text)


if __name__ == "__main__":
    unittest.main()
