import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import rating_ledger  # noqa: E402


class TestNormaliseRating(unittest.TestCase):
    def test_accepts_plain_ratings_case_insensitive(self):
        self.assertEqual(rating_ledger.normalise_rating("buy"), "BUY")
        self.assertEqual(rating_ledger.normalise_rating("Hold"), "HOLD")
        self.assertEqual(rating_ledger.normalise_rating("SELL"), "SELL")

    def test_trim_aliases_map_to_sell(self):
        self.assertEqual(rating_ledger.normalise_rating("SELL/trim"), "SELL")
        self.assertEqual(rating_ledger.normalise_rating("trim"), "SELL")
        self.assertEqual(rating_ledger.normalise_rating("Sell / Trim"), "SELL")

    def test_rejects_anything_else(self):
        with self.assertRaises(ValueError):
            rating_ledger.normalise_rating("MAYBE")


class TestAppendAndLoadLedger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmpdir.name, "ratings-ledger.jsonl")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_append_then_load_round_trips(self):
        rating_ledger.append_entry("tcs", "buy", "3150.5", "clears the Nifty hurdle, thinly",
                                    asof="2026-09-27", ledger_path=self.ledger_path)
        entries = rating_ledger.load_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["ticker"], "TCS")
        self.assertEqual(e["rating"], "BUY")
        self.assertEqual(e["price"], 3150.5)
        self.assertEqual(e["date"], "2026-09-27")

    def test_filters_by_ticker(self):
        rating_ledger.append_entry("TCS", "HOLD", 3000, "x", asof="2026-09-01",
                                    ledger_path=self.ledger_path)
        rating_ledger.append_entry("ITC", "BUY", 400, "y", asof="2026-09-02",
                                    ledger_path=self.ledger_path)
        tcs_only = rating_ledger.load_ledger(ticker="tcs", ledger_path=self.ledger_path)
        self.assertEqual([e["ticker"] for e in tcs_only], ["TCS"])

    def test_sorted_by_ticker_then_date(self):
        rating_ledger.append_entry("TCS", "HOLD", 3000, "later", asof="2026-09-10",
                                    ledger_path=self.ledger_path)
        rating_ledger.append_entry("TCS", "BUY", 2900, "earlier", asof="2026-08-01",
                                    ledger_path=self.ledger_path)
        entries = rating_ledger.load_ledger(ledger_path=self.ledger_path)
        self.assertEqual([e["date"] for e in entries], ["2026-08-01", "2026-09-10"])

    def test_rejects_non_positive_price(self):
        with self.assertRaises(ValueError):
            rating_ledger.append_entry("TCS", "BUY", 0, "x", ledger_path=self.ledger_path)

    def test_appends_are_newline_delimited_jsonl(self):
        rating_ledger.append_entry("TCS", "BUY", 100, "a", asof="2026-01-01",
                                    ledger_path=self.ledger_path)
        rating_ledger.append_entry("TCS", "HOLD", 110, "b", asof="2026-02-01",
                                    ledger_path=self.ledger_path)
        with open(self.ledger_path, encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        for line in lines:
            json.loads(line)  # each line stands alone as valid JSON


class TestDaysBetweenAndReturn(unittest.TestCase):
    def test_days_between(self):
        self.assertEqual(rating_ledger.days_between("2026-01-01", "2026-01-31"), 30)

    def test_realised_return_positive(self):
        self.assertAlmostEqual(rating_ledger.realised_return_pct(100, 110), 10.0)

    def test_realised_return_negative(self):
        self.assertAlmostEqual(rating_ledger.realised_return_pct(100, 90), -10.0)

    def test_realised_return_none_when_current_missing(self):
        self.assertIsNone(rating_ledger.realised_return_pct(100, None))

    def test_realised_return_none_when_entry_price_missing(self):
        self.assertIsNone(rating_ledger.realised_return_pct(None, 100))


class TestBuildReport(unittest.TestCase):
    def test_groups_by_ticker_and_includes_thesis(self):
        entries = [
            {"ticker": "TCS", "date": "2026-01-01", "rating": "BUY", "price": 3000.0,
             "thesis": "cheap vs consensus"},
            {"ticker": "TCS", "date": "2026-06-01", "rating": "HOLD", "price": 3200.0,
             "thesis": "priced in now"},
        ]
        lines = rating_ledger.build_report(entries, {"TCS": 3300.0}, today="2026-09-01")
        text = "\n".join(lines)
        self.assertIn("TCS", text)
        self.assertIn("cheap vs consensus", text)
        self.assertIn("priced in now", text)
        self.assertIn("+10.0%", text)  # 3000 -> 3300

    def test_missing_current_price_reports_na(self):
        entries = [{"ticker": "XYZ", "date": "2026-01-01", "rating": "BUY", "price": 100.0,
                    "thesis": "t"}]
        lines = rating_ledger.build_report(entries, {}, today="2026-02-01")
        text = "\n".join(lines)
        self.assertIn("no current price on file", text)
        self.assertIn("n/a", text)


if __name__ == "__main__":
    unittest.main()
