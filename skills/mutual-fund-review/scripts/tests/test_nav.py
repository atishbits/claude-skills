import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import nav  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def read(name):
    with open(os.path.join(FIX, name)) as f:
        return f.read()


class TestAmfi(unittest.TestCase):
    def test_parse_by_header_names(self):
        parsed = nav.parse_amfi_navall(read("NAVAll-example.txt"))
        self.assertEqual(parsed["900001"]["nav"], 120.0)
        self.assertEqual(parsed["900001"]["date"], "2026-10-23")
        self.assertEqual(parsed["900002"]["isins"], ["INF000X01AB9", "INF000X01AC7"])
        self.assertIsNone(parsed["900003"]["nav"])

    def test_old_column_order_also_parses(self):
        text = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;"
                "Net Asset Value;Date\n\nExample AMC\n"
                "900001;INF000X01AA1;-;Example Large Cap Fund;120.0000;23-Oct-2026\n")
        parsed = nav.parse_amfi_navall(text)
        self.assertEqual(parsed["900001"]["scheme"], "Example Large Cap Fund")
        self.assertEqual(nav.isin_index(parsed)["INF000X01AA1"], "900001")


class TestHistory(unittest.TestCase):
    def test_nav_on_falls_back_never_forward(self):
        s = nav.parse_history(json.loads(read("mfapi-example.json")))
        self.assertEqual(nav.nav_on(s, "2026-10-23"), 120.0)
        self.assertEqual(nav.nav_on(s, "2026-10-18"), 118.0)   # Sunday -> Friday 16th
        self.assertIsNone(nav.nav_on(s, "2026-10-01"))        # before series
        self.assertIsNone(nav.nav_on(s, "2026-11-01"))        # 9 days after last point
        self.assertEqual(nav.nav_on(s, "2026-10-15"), 117.0)

    def test_cache_used_when_fresh(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return read("mfapi-example.json")

        with tempfile.TemporaryDirectory() as root:
            s1 = nav.history("900001", root, fetch=fetch)
            s2 = nav.history("900001", root, fetch=fetch)
            self.assertEqual(s1, s2)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].endswith("/mf/900001"))
            cache = os.path.join(root, "data", "skill-data", "nav", "900001.json")
            old = time.time() - 3 * 86400
            os.utime(cache, (old, old))
            nav.history("900001", root, fetch=fetch)
            self.assertEqual(len(calls), 2)

    def test_fetch_failure_falls_back_to_stale_cache(self):
        with tempfile.TemporaryDirectory() as root:
            nav.history("900001", root, fetch=lambda u: read("mfapi-example.json"))
            cache = os.path.join(root, "data", "skill-data", "nav", "900001.json")
            old = time.time() - 3 * 86400
            os.utime(cache, (old, old))

            def broken(url):
                raise OSError("offline")
            self.assertEqual(nav.history("900001", root, fetch=broken)["2026-10-23"], 120.0)


if __name__ == "__main__":
    unittest.main()
