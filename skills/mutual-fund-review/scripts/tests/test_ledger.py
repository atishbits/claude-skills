import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ledger  # noqa: E402


def tx(date="2026-02-16", type_="buy", amount=49997.50, units=3382.003, isin="INF000X01AA1",
       source="p", folio_ref="0001-abcdef12", row_id=None, scheme="Example Bank Index Fund"):
    return {"date": date, "source": source, "owner": "self", "folio_ref": folio_ref,
            "isin": isin, "amfi_code": "", "scheme": scheme, "plan": "direct",
            "option": "growth", "type": type_, "amount": amount, "units": units, "nav": "",
            "row_id": row_id or ledger.make_row_id(source, f"{date}|{amount}|{units}|{type_}", 0)}


class TestMerge(unittest.TestCase):
    def test_identical_same_day_rows_both_kept(self):
        raw = "2026-02-16|49997.50|3382.003"
        a = tx(row_id=ledger.make_row_id("p", raw, 0))
        b = tx(row_id=ledger.make_row_id("p", raw, 1))
        merged, stats = ledger.merge([], [a, b])
        self.assertEqual(len(merged), 2)
        self.assertEqual(stats, {"added": 2, "skipped": 0})
        merged2, stats2 = ledger.merge(merged, [a, b])
        self.assertEqual(len(merged2), 2)
        self.assertEqual(stats2, {"added": 0, "skipped": 2})

    def test_merge_sorted_by_date(self):
        merged, _ = ledger.merge([tx(date="2026-03-01")], [tx(date="2025-01-01")])
        self.assertEqual([r["date"] for r in merged], ["2025-01-01", "2026-03-01"])

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            ledger.merge([], [tx(type_="gift")])

    def test_roundtrip_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.csv")
            ledger.write_transactions(p, [tx()])
            back = ledger.read_transactions(p)
            self.assertEqual(back[0]["units"], 3382.003)
            self.assertEqual(back[0]["amount"], 49997.5)
            self.assertEqual(ledger.read_transactions(os.path.join(tmp, "none.csv")), [])


class TestUnitsAndReconcile(unittest.TestCase):
    def test_sell_reduces_units(self):
        rows = [tx(units=10, amount=1000), tx(date="2026-03-01", type_="sell", units=4, amount=500)]
        self.assertAlmostEqual(
            ledger.units_by_holding(rows)[("p", "0001-abcdef12", "INF000X01AA1")], 6.0)

    def test_reconcile_units_tolerance_and_stamp_gap(self):
        rows = [tx(units=896.736, amount=9999.50), tx(date="2026-09-15", units=136.382, amount=1499.93)]
        holdings = [{"source": "p", "folio_ref": "0001-abcdef12", "isin": "INF000X01AA1",
                     "scheme": "x", "units": 1033.118, "invested": 11499.80}]
        r = ledger.reconcile(rows, holdings)[0]
        self.assertTrue(r["units_ok"])
        self.assertAlmostEqual(r["amount_gap_inr"], 0.37, places=2)

    def test_reconcile_flags_missing_units(self):
        rows = [tx(units=90, amount=900)]
        holdings = [{"source": "p", "folio_ref": "0001-abcdef12", "isin": "INF000X01AA1",
                     "scheme": "x", "units": 100, "invested": 1000}]
        self.assertFalse(ledger.reconcile(rows, holdings)[0]["units_ok"])

    def test_reconcile_holding_without_folio_matches_any_folio(self):
        rows = [tx(units=5, amount=50)]
        holdings = [{"source": "p", "folio_ref": None, "isin": "INF000X01AA1",
                     "scheme": "x", "units": 5, "invested": 50}]
        self.assertTrue(ledger.reconcile(rows, holdings)[0]["units_ok"])

    def test_snapshot_refuses_unreconciled_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            recon = [{"units_ok": False, "isin": "X"}]
            with self.assertRaises(ValueError):
                ledger.write_snapshot(tmp, "2026-10-25", [], recon, {})
            path = ledger.write_snapshot(tmp, "2026-10-25", [], recon, {"p": {}}, force=True)
            with open(path) as f:
                snap = json.load(f)
            self.assertEqual(snap["date"], "2026-10-25")
            self.assertTrue(path.endswith("snapshot-2026-10-25.json"))


class TestExclude(unittest.TestCase):
    def test_ingest_drops_excluded_isins(self):
        import common
        with tempfile.TemporaryDirectory() as tmp:
            common.write_json(common.paths(tmp)["profile"], {"exclude_isins": ["INF000X01ZZ9"]})
            keep = tx(isin="INF000X01AA1", source="cas")
            drop = tx(isin="INF000X01ZZ9", source="cas", amount=100.0, units=10.0)
            holdings = [{"source": "cas", "folio_ref": "0001-abcdef12", "isin": i, "units": u}
                        for i, u in (("INF000X01AA1", 3382.003), ("INF000X01ZZ9", 10.0))]
            out = ledger.ingest(tmp, "cas", holdings, [keep, drop], "2026-10-25", True)
            self.assertEqual(out["excluded"], 2)
            rows = ledger.read_transactions(common.paths(tmp)["transactions"])
            self.assertEqual({r["isin"] for r in rows}, {"INF000X01AA1"})
            with open(out["snapshot"]) as f:
                snap = json.load(f)
            self.assertEqual([h["isin"] for h in snap["holdings"]], ["INF000X01AA1"])
            self.assertEqual(len(snap["reconciliation"]), 1)


if __name__ == "__main__":
    unittest.main()
