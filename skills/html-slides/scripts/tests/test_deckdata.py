import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deckdata as dd  # noqa: E402

SRC = {"s": {
    "by_cat": {"Food": 300, "Rent": 1000, "Fuel": 200, "Misc": 50},
    "months": [{"m": "Jan", "v": 10}, {"m": "Feb", "v": 30}, {"m": "Mar", "v": 20}],
    "pairs": [["A", 1], ["B", 2]],
    "nested": {"x": {"amount": 5}, "y": {"amount": 7}},
    "totals": {"spend": 1550, "label": "text"},
}}


class TestFormat(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(dd.fmt_number(1234567), "12,34,567")
        self.assertEqual(dd.fmt_number(100000), "1,00,000")
        self.assertEqual(dd.fmt_number(999), "999")
        self.assertEqual(dd.fmt_number(1000), "1,000")

    def test_intl_and_plain(self):
        self.assertEqual(dd.fmt_number(1234567, "intl"), "1,234,567")
        self.assertEqual(dd.fmt_number(1234567, "plain"), "1234567")

    def test_lakh_and_compact(self):
        self.assertEqual(dd.fmt_number(250000, "lakh", prefix="₹"), "₹2.5L")
        self.assertEqual(dd.fmt_number(32000000, "lakh"), "3.2Cr")
        self.assertEqual(dd.fmt_number(52000, "lakh"), "52K")
        self.assertEqual(dd.fmt_number(1500000, "compact"), "1.5M")
        self.assertEqual(dd.fmt_number(2000000000, "compact"), "2B")
        self.assertEqual(dd.fmt_number(640, "lakh"), "640")
        self.assertEqual(dd.fmt_number(250000, "lakh", decimals=2), "2.50L")

    def test_decimals_and_rounding(self):
        self.assertEqual(dd.fmt_number(41.25), "41.3")       # half away from zero
        self.assertEqual(dd.fmt_number(2.5, decimals=0), "3")
        self.assertEqual(dd.fmt_number(1234.5), "1,235")     # large: whole number
        self.assertEqual(dd.fmt_number(0.125, decimals=2), "0.13")
        self.assertEqual(dd.fmt_number(7.0), "7")

    def test_negative_and_affixes(self):
        self.assertEqual(dd.fmt_number(-1200, prefix="₹"), "-₹1,200")
        self.assertEqual(dd.fmt_number(12, suffix="%"), "12%")
        self.assertEqual(dd.fmt_number(-0.01, decimals=0), "0")
        self.assertEqual(dd.fmt_number(None), "")


class TestShares(unittest.TestCase):
    def test_sum_to_100(self):
        for vals in ([1, 1, 1], [300, 1000, 200, 50], [7, 13, 29, 51], [1, 2]):
            with self.subTest(vals=vals):
                self.assertAlmostEqual(sum(dd.shares(vals)), 100)
                self.assertAlmostEqual(sum(dd.shares(vals, 1)), 100)

    def test_largest_remainder(self):
        self.assertEqual(dd.shares([1, 1, 1]), [34, 33, 33])
        self.assertEqual(dd.shares([50, 50]), [50, 50])

    def test_zero_and_negative(self):
        self.assertEqual(dd.shares([0, 0]), [0, 0])
        self.assertEqual(dd.shares([-5, 5]), [0, 100])

    def test_lengths(self):
        self.assertEqual(dd.lengths([50, 100, 25]), [50.0, 100.0, 25.0])
        self.assertEqual(dd.lengths([0, 0]), [0.0, 0.0])
        self.assertEqual(dd.lengths([]), [])


class TestRefs(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(dd.lookup(SRC, "s:totals.spend"), 1550)
        self.assertEqual(dd.lookup(SRC, "s:months.1.v"), 30)
        self.assertEqual(dd.lookup(SRC, "s:months.-1.m"), "Mar")

    def test_lookup_errors(self):
        for ref in ("nocolon", "x:totals", "s:totals.nope", "s:months.9", "s:months.a",
                    "s:totals.spend.x"):
            with self.subTest(ref=ref):
                with self.assertRaises(dd.RefError):
                    dd.lookup(SRC, ref)

    def test_items_from_mapping(self):
        items = dd.items_from(SRC, {"ref": "s:by_cat", "sort": "desc", "top": 2, "other": "Other"})
        self.assertEqual(items, [{"label": "Rent", "value": 1000}, {"label": "Food", "value": 300},
                                 {"label": "Other", "value": 250}])

    def test_items_from_top_without_other(self):
        self.assertEqual(len(dd.items_from(SRC, {"ref": "s:by_cat", "top": 2})), 2)

    def test_items_from_rows_and_pairs(self):
        self.assertEqual(dd.items_from(SRC, {"ref": "s:months", "label": "m", "value": "v"})[1],
                         {"label": "Feb", "value": 30})
        self.assertEqual(dd.items_from(SRC, "s:pairs"),
                         [{"label": "A", "value": 1}, {"label": "B", "value": 2}])
        self.assertEqual(dd.items_from(SRC, {"ref": "s:nested", "value": "amount"})[1],
                         {"label": "y", "value": 7})

    def test_items_from_filters(self):
        got = dd.items_from(SRC, {"ref": "s:by_cat", "exclude": ["Rent"], "sort": "asc"})
        self.assertEqual([i["label"] for i in got], ["Misc", "Fuel", "Food"])
        got = dd.items_from(SRC, {"ref": "s:by_cat", "only": ["Fuel", "Food"]})
        self.assertEqual([i["label"] for i in got], ["Food", "Fuel"])

    def test_items_from_rejects_text(self):
        with self.assertRaises(dd.RefError):
            dd.items_from(SRC, "s:totals")
        with self.assertRaises(dd.RefError):
            dd.items_from(SRC, {"ref": "s:months", "label": "m", "value": "missing"})

    def test_rows_from(self):
        header, rows = dd.rows_from(SRC, {"ref": "s:months", "sort_by": "v", "desc": True, "top": 2,
                                          "columns": [{"key": "m", "label": "Month"},
                                                      {"key": "v", "label": "Value", "num": True}]})
        self.assertEqual(header, [{"label": "Month", "num": False}, {"label": "Value", "num": True}])
        self.assertEqual(rows, [["Feb", 30], ["Mar", 20]])

    def test_resolve(self):
        deck = {"slides": [
            {"type": "bars", "items_from": {"ref": "s:by_cat", "top": 1}},
            {"type": "stats", "items": [{"label": "Spend", "value_from": "s:totals.spend"}]},
            {"type": "columns", "values_from": {"ref": "s:months", "label": "m", "value": "v"}},
            {"type": "stats", "items": [{"label": "Bad", "value_from": "s:totals.label"}]},
        ]}
        deck, errs = dd.resolve(deck, SRC)
        self.assertEqual(deck["slides"][0]["items"], [{"label": "Food", "value": 300}])
        self.assertEqual(deck["slides"][1]["items"][0]["value"], 1550)
        self.assertEqual(len(deck["slides"][2]["items"]), 3)
        self.assertEqual(len(errs), 1)
        self.assertIn("slide 4", errs[0])

    def test_csv_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.csv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("name,amount\nAlpha,\"1,200\"\nBeta,₹300\nGamma,n/a\n")
            rows = dd.load_source(p)
            self.assertEqual(rows[0], {"name": "Alpha", "amount": 1200.0})
            self.assertEqual(rows[1]["amount"], 300.0)
            self.assertEqual(rows[2]["amount"], "n/a")
            src = dd.parse_data_args(["t=x.csv"], base_dir=d)
            self.assertEqual(dd.lookup(src, "t:0.name"), "Alpha")

    def test_parse_data_args_needs_name(self):
        with self.assertRaises(dd.RefError):
            dd.parse_data_args(["just-a-path.json"])


if __name__ == "__main__":
    unittest.main()
