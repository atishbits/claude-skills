import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import digest  # noqa: E402

NOTE = """# TESTCO — Test Company

**Last analysis:** 1 Oct 2026 (prev 1 Sep 2026)
**Rating:** BUY, UPGRADED from HOLD
**Signal row:** Row 1 → *cheap quality* (confidence: high)

**Research:**
- consensus: avg TP ₹1,000 — https://example.com — as of 2026-10-01
"""


class TestDigest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.tmp.name, "skill-data")
        os.makedirs(os.path.join(self.sd, "stocks"))
        os.makedirs(os.path.join(self.sd, "ratings-ledger"))
        with open(os.path.join(self.sd, "stocks", "TESTCO.md"), "w") as fh:
            fh.write(NOTE)
        with open(os.path.join(self.sd, "stocks", "TESTCO.conflict-2026-10-18.md"), "w") as fh:
            fh.write(NOTE)
        with open(os.path.join(self.sd, "entry-budgets.json"), "w") as fh:
            json.dump({"TESTCO": {"budget": 50000, "set_on": "2026-10-01", "baseline_invested": 0}}, fh)
        with open(os.path.join(self.sd, "calendar.md"), "w") as fh:
            fh.write("| Ticker | Type | Detail |\n|---|---|---|\n"
                     "| TESTCO | Next results window | 2026-11-01 to 2026-11-29 |\n"
                     "| EXAMPLEA | Price re-look | 200 DMA ₹500 |\n")
        with open(os.path.join(self.sd, "ratings-ledger", "2026-10-01-abcdef.jsonl"), "w") as fh:
            fh.write(json.dumps({"ticker": "TESTCO", "date": "2026-10-01", "rating": "BUY",
                                 "price": 1000.0, "thesis": "x"}) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_note_fields(self):
        d = digest.build(self.sd, date(2026, 10, 18))
        t = d["tickers"]["TESTCO"]
        self.assertEqual(t["rating"], "BUY")
        self.assertEqual(t["last_analysis"], "2026-10-01")
        self.assertEqual(t["days_since_analysis"], 17)
        self.assertEqual(t["signal_row"], 1)
        self.assertEqual(t["research"]["consensus"]["status"], "fresh")
        self.assertEqual(t["research"]["peers"]["status"], "due")

    def test_conflict_copy_is_not_a_ticker(self):
        d = digest.build(self.sd, date(2026, 10, 18))
        self.assertEqual(list(d["tickers"]), ["TESTCO"])
        self.assertEqual(d["conflicts"], ["stocks/TESTCO.conflict-2026-10-18.md"])

    def test_budget_calendar_ledger_joined(self):
        t = digest.build(self.sd, date(2026, 10, 18))["tickers"]["TESTCO"]
        self.assertEqual(t["budget"]["budget"], 50000)
        self.assertEqual(t["calendar"], ["Next results window | 2026-11-01 to 2026-11-29"])
        self.assertEqual(t["ledger"], [{"date": "2026-10-01", "rating": "BUY", "price": 1000.0}])

    def test_unmigrated_single_file_ledger_is_read(self):
        os.remove(os.path.join(self.sd, "ratings-ledger", "2026-10-01-abcdef.jsonl"))
        os.rmdir(os.path.join(self.sd, "ratings-ledger"))
        with open(os.path.join(self.sd, "ratings-ledger.jsonl"), "w") as fh:
            fh.write(json.dumps({"ticker": "TESTCO", "date": "2026-09-01", "rating": "HOLD",
                                 "price": 900.0, "thesis": "x"}) + "\n")
        t = digest.build(self.sd, date(2026, 10, 18))["tickers"]["TESTCO"]
        self.assertEqual(t["ledger"], [{"date": "2026-09-01", "rating": "HOLD", "price": 900.0}])

    def test_unparseable_note_still_listed(self):
        with open(os.path.join(self.sd, "stocks", "EXAMPLEB.md"), "w") as fh:
            fh.write("# EXAMPLEB\n")
        t = digest.build(self.sd, date(2026, 10, 18))["tickers"]["EXAMPLEB"]
        self.assertIsNone(t["rating"])
        self.assertIsNone(t["days_since_analysis"])

    def test_merge_keeps_tickers_whose_notes_were_not_pulled(self):
        previous = {"generated_on": "2026-10-10", "conflicts": [], "tickers": {
            "EXAMPLEA": {"rating": "HOLD", "ledger": []},
            "TESTCO": {"rating": "HOLD", "ledger": [{"date": "2026-09-01", "rating": "HOLD", "price": 900.0}]}}}
        d = digest.build(self.sd, date(2026, 10, 18), previous=previous)
        self.assertEqual(d["tickers"]["EXAMPLEA"], {"rating": "HOLD", "ledger": []})
        self.assertEqual(d["tickers"]["TESTCO"]["rating"], "BUY")
        self.assertEqual([e["date"] for e in d["tickers"]["TESTCO"]["ledger"]], ["2026-09-01", "2026-10-01"])

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(digest.build(empty, date(2026, 10, 18))["tickers"], {})


if __name__ == "__main__":
    unittest.main()
