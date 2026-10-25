import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ingest_capture  # noqa: E402
import ingest_cas  # noqa: E402
import ledger  # noqa: E402

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
            out = ingest_cas.main(["--text", tp, "--root", root, "--date", "2026-10-25"])
            recon = {r["isin"]: r["units_ok"] for r in out["reconciliation"]}
            self.assertTrue(all(recon.values()))  # opening balance counted, no --force needed
            with open(out["snapshot"]) as f:
                snap = json.load(f)
            aa1 = [h for h in snap["holdings"] if h["isin"] == "INF000X01AA1"]
            self.assertEqual([h["source"] for h in aa1], ["cas"])
            self.assertFalse(snap["sources"]["cas"]["transactions_complete"])

    def test_portal_refresh_after_cas_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as root:
            cap = {"source": "portalx", "transactions_complete": False,
                   "holdings": [{"scheme": "Example Large Cap Fund", "isin": "INF000X01AA1",
                                 "folio": "1111222233/0", "units": "1428.571", "invested": "45000",
                                 "current_value": "171428.52"}], "transactions": []}
            p = os.path.join(root, "cap.json")
            with open(p, "w") as f:
                json.dump(cap, f)
            ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-24", "--force"])
            tp = os.path.join(root, "cas.txt")
            with open(tp, "w") as f:
                f.write(text())
            ingest_cas.main(["--text", tp, "--root", root, "--date", "2026-10-25"])
            out = ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-26",
                                       "--force"])
            with open(out["snapshot"]) as f:
                snap = json.load(f)
            aa1 = [h["source"] for h in snap["holdings"] if h["isin"] == "INF000X01AA1"]
            self.assertEqual(aa1, ["cas"])

    def test_systematic_withdrawal_is_a_sale(self):
        self.assertEqual(ingest_cas.tx_type("Systematic Withdrawal - Instalment 3"), "sell")
        self.assertEqual(ingest_cas.tx_type("SWP Redemption"), "sell")

    def test_redemption_mentioning_stt_is_a_sale(self):
        self.assertEqual(ingest_cas.tx_type("Redemption less TDS, STT"), "sell")
        self.assertEqual(ingest_cas.tx_type("*** STT Paid ***"), "stt")

    def test_rejected_instalment_cancels_its_purchase(self):
        txt = """Folio No: 7777888899 / 0                    KYC: OK
EX04-Example Mid Cap Fund - Direct Plan Growth (Non-Demat) - ISIN: INF000X01DD4(Advisor: DIRECT) Registrar : EXAMPLE
Opening Unit Balance: 0.000
04-May-2018   Sys. Investment SIP First Installment (1/3)          30,000.00        600.000       50.0000         600.000
04-Jun-2018   Sys. Investment ISIP (2/3)                            30,000.00        500.000       60.0000       1,100.000
04-Jun-2018   Systematic Investment Rejection (2/3)               (30,000.00)      (500.000)      60.0000         600.000
04-Jul-2018   Sys. Investment ISIP (3/3)                            30,000.00        400.000       75.0000       1,000.000
20-Oct-2023   Redemption less TDS, STT                            (10,000.00)      (100.000)     100.0000         900.000
20-Oct-2023   *** STT Paid ***                                          0.10
Closing Unit Balance: 900.000      NAV on 23-Oct-2026: INR 120.0000      Total Cost Value: 50,000.00      Market Value on 23-Oct-2026: INR 108,000.00
"""
        holdings, tx, _ = ingest_cas.parse_cas_text(txt)
        self.assertEqual([(t["date"], t["type"]) for t in tx],
                         [("2018-05-04", "sip"), ("2018-07-04", "sip"),
                          ("2023-10-20", "sell"), ("2023-10-20", "stt")])
        self.assertTrue(all(r["units_ok"] for r in ledger.reconcile(tx, holdings)))

    def test_rejection_without_its_purchase_is_an_error(self):
        txt = """Folio No: 7777888899 / 0                    KYC: OK
EX04-Example Mid Cap Fund - Direct Plan Growth (Non-Demat) - ISIN: INF000X01DD4(Advisor: DIRECT) Registrar : EXAMPLE
Opening Unit Balance: 0.000
04-Jun-2018   Systematic Investment Rejection (2/3)               (30,000.00)      (500.000)      60.0000           0.000
Closing Unit Balance: 0.000      NAV on 23-Oct-2026: INR 120.0000      Total Cost Value: 0.00      Market Value on 23-Oct-2026: INR 0.00
"""
        with self.assertRaises(ValueError):
            ingest_cas.parse_cas_text(txt)

    def test_password_never_in_argv(self):
        with self.assertRaises(SystemExit):
            ingest_cas.main(["--pdf", "x.pdf", "--password", "secret"])


if __name__ == "__main__":
    unittest.main()
