import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ingest_capture  # noqa: E402
import ingest_cas  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def text():
    with open(os.path.join(FIX, "cas-example.txt")) as f:
        return f.read()


class TestParse(unittest.TestCase):
    def setUp(self):
        self.holdings, self.tx, self.meta = ingest_cas.parse_cas_text(text())

    def test_meta_period(self):
        self.assertEqual(self.meta["period_from"], "2018-01-01")
        self.assertEqual(self.meta["period_to"], "2026-10-25")

    def test_holdings(self):
        self.assertEqual([h["isin"] for h in self.holdings],
                         ["INF000X01AA1", "INF000X01BB2", "INF000X01CC3"])
        h = self.holdings[0]
        self.assertEqual(h["units"], 1428.571)
        self.assertEqual(h["nav"], 120.0)
        self.assertEqual(h["invested"], 45000.0)
        self.assertEqual(h["current_value"], 171428.52)
        self.assertEqual(h["plan"], "direct")
        self.assertEqual(self.holdings[2]["option"], "idcw")
        self.assertNotIn("1111222233", json.dumps([self.holdings, self.tx]))

    def test_types(self):
        types = [(t["isin"][-3:], t["type"]) for t in self.tx]
        self.assertEqual(types, [("AA1", "buy"), ("AA1", "stamp"), ("AA1", "sip"),
                                 ("AA1", "sell"), ("BB2", "buy"), ("BB2", "switch_in"),
                                 ("CC3", "buy"), ("CC3", "dividend_payout")])
        sell = self.tx[3]
        self.assertEqual((sell["amount"], sell["units"]), (10000.0, 100.0))
        self.assertEqual(self.tx[7]["amount"], 250.0)

    def test_opening_balance_marks_incomplete(self):
        flags = [h["transactions_complete"] for h in self.holdings]
        self.assertEqual(flags, [True, True, False])


class TestIngest(unittest.TestCase):
    def test_reconciles_and_supersedes_portal_holding(self):
        with tempfile.TemporaryDirectory() as root:
            # a portal capture of the same folio + ISIN, then the CAS
            cap = {"source": "portalx", "transactions_complete": False,
                   "holdings": [{"scheme": "Example Large Cap Fund", "isin": "INF000X01AA1",
                                 "folio": "1111222233", "units": "1428.571", "invested": "45000",
                                 "current_value": "171428.52"}], "transactions": []}
            p = os.path.join(root, "cap.json")
            with open(p, "w") as f:
                json.dump(cap, f)
            ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-24",
                                 "--force"])
            tp = os.path.join(root, "cas.txt")
            with open(tp, "w") as f:
                f.write(text())
            out = ingest_cas.main(["--text", tp, "--root", root, "--date", "2026-10-25",
                                   "--force"])
            recon = {r["isin"]: r["units_ok"] for r in out["reconciliation"]}
            self.assertTrue(recon["INF000X01AA1"])
            self.assertTrue(recon["INF000X01BB2"])
            self.assertFalse(recon["INF000X01CC3"])  # opening balance 50 not in transactions
            with open(out["snapshot"]) as f:
                snap = json.load(f)
            aa1 = [h for h in snap["holdings"] if h["isin"] == "INF000X01AA1"]
            self.assertEqual([h["source"] for h in aa1], ["cas"])
            self.assertFalse(snap["sources"]["cas"]["transactions_complete"])

    def test_password_never_in_argv(self):
        with self.assertRaises(SystemExit):
            ingest_cas.main(["--pdf", "x.pdf", "--password", "secret"])


if __name__ == "__main__":
    unittest.main()
