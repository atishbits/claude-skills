import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ingest_capture  # noqa: E402
import ledger  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
MANUAL = os.path.join(os.path.dirname(__file__), "..", "..", "manual-import-template.csv")


def load(name):
    with open(os.path.join(FIX, name)) as f:
        return json.load(f)


class TestParseCapture(unittest.TestCase):
    def test_normalises_and_hides_folio(self):
        holdings, tx = ingest_capture.parse_capture(load("capture-example.json"))
        self.assertEqual(len(holdings), 2)
        self.assertEqual(len(tx), 3)
        self.assertEqual(holdings[0]["units"], 2000.0)
        self.assertEqual(holdings[0]["invested"], 20000.10)
        self.assertEqual(tx[0]["date"], "2026-02-16")
        self.assertEqual(tx[0]["type"], "buy")
        self.assertEqual(tx[2]["type"], "sip")
        blob = json.dumps([holdings, tx])
        self.assertNotIn("1234567890", blob)
        self.assertTrue(all(r["folio_ref"].startswith("7890-") for r in tx))
        self.assertNotEqual(tx[0]["row_id"], tx[1]["row_id"])

    def test_missing_isin_is_refused(self):
        doc = load("capture-example.json")
        del doc["holdings"][0]["isin"]
        with self.assertRaises(ValueError):
            ingest_capture.parse_capture(doc)


class TestIngest(unittest.TestCase):
    def test_ingest_twice_adds_nothing_and_keeps_other_sources(self):
        with tempfile.TemporaryDirectory() as root:
            out = ingest_capture.main(["--capture", os.path.join(FIX, "capture-example.json"),
                                       "--root", root, "--date", "2026-10-25"])
            self.assertEqual(out["added"], 3)
            self.assertTrue(all(r["units_ok"] for r in out["reconciliation"]))
            out2 = ingest_capture.main(["--capture", os.path.join(FIX, "capture-example.json"),
                                        "--root", root, "--date", "2026-10-25"])
            self.assertEqual(out2["added"], 0)
            out3 = ingest_capture.main(["--csv", MANUAL,
                                        "--source", "manualsrc", "--root", root,
                                        "--date", "2026-10-26"])
            self.assertEqual(out3["added"], 2)
            with open(out3["snapshot"]) as f:
                snap = json.load(f)
            self.assertEqual({h["source"] for h in snap["holdings"]},
                             {"exampleportal", "manualsrc"})
            self.assertTrue(snap["sources"]["exampleportal"]["transactions_complete"])
            self.assertEqual(snap["sources"]["manualsrc"]["holdings_as_of"], "2026-10-26")
            for name in os.listdir(os.path.join(root, "data", "skill-data")):
                with open(os.path.join(root, "data", "skill-data", name)) as f:
                    self.assertNotIn("1234567890", f.read())

    def test_incomplete_flag_propagates(self):
        with tempfile.TemporaryDirectory() as root:
            doc = load("capture-example.json")
            doc["transactions_complete"] = False
            p = os.path.join(root, "cap.json")
            with open(p, "w") as f:
                json.dump(doc, f)
            out = ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-25"])
            with open(out["snapshot"]) as f:
                self.assertFalse(json.load(f)["sources"]["exampleportal"]["transactions_complete"])

    def test_unreconciled_refused_without_force(self):
        with tempfile.TemporaryDirectory() as root:
            doc = load("capture-example.json")
            doc["holdings"][1]["units"] = "150.000"
            p = os.path.join(root, "cap.json")
            with open(p, "w") as f:
                json.dump(doc, f)
            with self.assertRaises(ValueError):
                ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-25"])
            self.assertEqual(ledger.read_transactions(
                os.path.join(root, "data", "skill-data", "transactions.csv")), [])
            out = ingest_capture.main(["--capture", p, "--root", root, "--date", "2026-10-25",
                                       "--force"])
            self.assertFalse(all(r["units_ok"] for r in out["reconciliation"]))

    def test_manual_csv_shape(self):
        holdings, tx = ingest_capture.parse_manual_csv(
            MANUAL, "manualsrc")
        self.assertEqual(holdings[0]["current_value"], 7500.0)
        self.assertEqual([t["type"] for t in tx], ["buy", "sip"])
        self.assertEqual(tx[0]["source"], "manualsrc")


if __name__ == "__main__":
    unittest.main()
