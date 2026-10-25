import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_parse_amount_dr_cr(self):
        self.assertEqual(common.parse_amount("1,234.50 Dr"), -1234.5)
        self.assertEqual(common.parse_amount("₹ 500 Cr"), 500.0)
        self.assertEqual(common.parse_amount(""), 0.0)
        self.assertEqual(common.parse_amount("2,49,987.87"), 249987.87)
        self.assertEqual(common.parse_amount("-75.00"), -75.0)

    def test_parse_date_formats(self):
        for s in ["25/04/2026", "25-Apr-2026", "25 Apr 2026", "2026-04-25", "25-04-2026"]:
            self.assertEqual(common.parse_date(s), "2026-04-25", s)
        self.assertEqual(common.parse_date("04/25/2026", "%m/%d/%Y"), "2026-04-25")
        with self.assertRaises(ValueError):
            common.parse_date("soon")

    def test_payee_key(self):
        self.assertEqual(common.payee_key("UPI/FUELCO PUMP/fuelco@okx/Pay/ACME BANK/6123"), "FUELCO")
        self.assertEqual(common.payee_key("MMT/IMPS/611612/Jane Doe/ABCD0123"), "JANE")
        self.assertEqual(common.payee_key("123/456"), "UNKNOWN")

    def test_mask(self):
        self.assertEqual(common.mask("123456780352"), "XX0352")
        self.assertEqual(common.mask(""), "")


class TestRoot(unittest.TestCase):
    def test_resolve_root_env(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"SPENDINGS_ROOT": d}):
            self.assertEqual(common.resolve_root(None), os.path.abspath(d))

    def test_skill_dir_without_data_exits(self):
        if os.path.isdir(os.path.join(common.SKILL_DIR, "data")):
            self.skipTest("checkout has data/")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                common.resolve_root(common.SKILL_DIR)

    def test_paths_keys(self):
        p = common.paths("/r")
        for k in ["data", "raw", "adapters", "profile", "accounts", "rules", "notes", "holdings",
                  "offers", "cards", "vendor", "skill_data", "ledger", "coverage"]:
            self.assertIn(k, p)
        self.assertEqual(p["ledger"], "/r/data/skill-data/ledger.csv")


if __name__ == "__main__":
    unittest.main()
