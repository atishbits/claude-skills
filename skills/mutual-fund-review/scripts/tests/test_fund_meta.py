import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import fund_meta  # noqa: E402


class TestFundMeta(unittest.TestCase):
    def test_set_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            meta = fund_meta.load(root)
            fund_meta.set_fields(meta, "INF000X01AA1", category="large_cap",
                                 benchmark_key="large_cap", expense_ratio_pct=0.59,
                                 er_as_of="2026-10-25", er_basis="post_2026_04")
            fund_meta.save(root, meta)
            back = fund_meta.load(root)
            self.assertEqual(back["INF000X01AA1"]["expense_ratio_pct"], 0.59)
            self.assertEqual(back["INF000X01AA1"]["tax_class"], "equity")  # from benchmark map

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            fund_meta.set_fields({}, "INF000X01AA1", colour="red")

    def test_bad_benchmark_rejected(self):
        with self.assertRaises(ValueError):
            fund_meta.set_fields({}, "INF000X01AA1", benchmark_key="nifty_moon")

    def test_bad_er_basis_rejected(self):
        with self.assertRaises(ValueError):
            fund_meta.set_fields({}, "INF000X01AA1", er_basis="whenever")

    def test_idcw_note(self):
        b = fund_meta.benchmark_for({"benchmark_key": "large_cap", "option": "idcw"})
        self.assertEqual(b["proxy_amfi_code"], "120716")
        self.assertIn("growth proxy", b["note"])
        self.assertIsNone(fund_meta.benchmark_for({"option": "growth"}))

    def test_missing_lists_held_isins_without_meta(self):
        with tempfile.TemporaryDirectory() as root:
            sd = common.paths(root)["skill_data"]
            os.makedirs(sd)
            with open(os.path.join(sd, "snapshot-2026-10-25.json"), "w") as f:
                json.dump({"holdings": [{"isin": "INF000X01AA1", "scheme": "A"},
                                        {"isin": "INF000X01BB2", "scheme": "B"}]}, f)
            meta = {}
            fund_meta.set_fields(meta, "INF000X01AA1", benchmark_key="large_cap",
                                 category="large_cap", expense_ratio_pct=0.5,
                                 amfi_code="900001", exit_load_pct=0)
            fund_meta.save(root, meta)
            missing = fund_meta.missing(root)
            self.assertEqual([m["isin"] for m in missing], ["INF000X01BB2"])
            self.assertIn("expense_ratio_pct", missing[0]["fields"])

    def test_sold_fund_needs_no_fee_or_exit_load(self):
        with tempfile.TemporaryDirectory() as root:
            sd = common.paths(root)["skill_data"]
            os.makedirs(sd)
            with open(os.path.join(sd, "snapshot-2026-10-25.json"), "w") as f:
                json.dump({"holdings": [{"isin": "INF000X01AA1", "scheme": "Sold", "units": 0.0},
                                        {"isin": "INF000X01BB2", "scheme": "Held", "units": 0.0},
                                        {"isin": "INF000X01BB2", "scheme": "Held", "units": 5.0}]}, f)
            meta = {}
            for isin in ("INF000X01AA1", "INF000X01BB2"):
                fund_meta.set_fields(meta, isin, benchmark_key="large_cap",
                                     category="large_cap", amfi_code="900001")
            fund_meta.save(root, meta)
            missing = fund_meta.missing(root)
            self.assertEqual([m["isin"] for m in missing], ["INF000X01BB2"])

    def test_every_benchmark_has_tax_class(self):
        for key, b in common.load_benchmarks().items():
            if key.startswith("_"):
                continue
            self.assertIn(b["tax_class"], fund_meta.TAX_CLASSES, key)


if __name__ == "__main__":
    unittest.main()
