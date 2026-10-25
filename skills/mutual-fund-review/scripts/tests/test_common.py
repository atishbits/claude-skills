import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_parse_date_formats(self):
        for s in ["18th Sep 2026", "18-Sep-2026", "18/09/2026", "18-09-2026",
                  "2026-09-18", "20260918", "1st Sep 2026".replace("1st", "18th")]:
            self.assertEqual(common.parse_date(s), "2026-09-18", s)
        self.assertEqual(common.parse_date("2nd Dec 2025"), "2025-12-02")
        self.assertEqual(common.parse_date("23rd Oct 2026"), "2026-10-23")
        self.assertIsNone(common.parse_date(" - "))
        self.assertIsNone(common.parse_date(""))
        with self.assertRaises(ValueError):
            common.parse_date("soon")

    def test_parse_num(self):
        self.assertEqual(common.parse_num("₹2,49,987.87"), 249987.87)
        self.assertEqual(common.parse_num("-7.13%"), -7.13)
        self.assertEqual(common.parse_num("(1,000.50)"), -1000.5)
        self.assertEqual(common.parse_num("INR 94.0665"), 94.0665)
        self.assertIsNone(common.parse_num(""))
        self.assertIsNone(common.parse_num("-"))

    def test_folio_ref_hides_folio(self):
        r = common.folio_ref("123456789012")
        self.assertTrue(r.startswith("9012-"))
        self.assertEqual(len(r), 13)
        self.assertNotIn("12345678", r)
        self.assertEqual(r, common.folio_ref(" 123456789012 "))
        self.assertIsNone(common.folio_ref(None))
        self.assertIsNone(common.folio_ref(""))


class TestFolioSuffix(unittest.TestCase):
    def test_check_digit_suffix_ignored(self):
        self.assertEqual(common.folio_ref("1111222233 / 0"), common.folio_ref("1111222233"))
        self.assertEqual(common.folio_ref("1111222233/12"), common.folio_ref("1111222233"))


class TestRootAndProfile(unittest.TestCase):
    def test_profile_defaults_overlaid(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(tmp, "data", "profile.json"), "w") as f:
                json.dump({"fd_rate_pct": 7.0}, f)
            p = common.load_profile(tmp)
            self.assertEqual(p["fd_rate_pct"], 7.0)
            self.assertEqual(p["keep_min_window_win_pct"], 65)
            self.assertEqual(p["stale_after_days"], 30)

    def test_profile_missing_file_gives_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(common.load_profile(tmp)["fd_rate_pct"], 6.5)

    def test_resolve_root_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"MF_ROOT": tmp}):
                self.assertEqual(common.resolve_root(None), os.path.abspath(tmp))
            self.assertEqual(common.resolve_root(tmp), os.path.abspath(tmp))

    def test_paths(self):
        p = common.paths("/x")
        self.assertEqual(p["transactions"], "/x/data/skill-data/transactions.csv")
        self.assertEqual(p["fund_meta"], "/x/data/skill-data/fund-meta.json")
        self.assertEqual(p["nav_cache"], "/x/data/skill-data/nav")
        self.assertEqual(p["adapters"], "/x/data/adapters")

    def test_tax_rules(self):
        r = common.load_tax_rules()
        self.assertEqual(r["equity"]["ltcg_pct"], 12.5)
        self.assertEqual(r["equity"]["stcg_pct"], 20)
        self.assertEqual(r["ltcg_exemption_inr"], 125000)
        self.assertEqual(r["hybrid_gold_intl"]["lt_months"], 24)
        self.assertEqual(r["grandfather_date"], "2018-01-31")


if __name__ == "__main__":
    unittest.main()
