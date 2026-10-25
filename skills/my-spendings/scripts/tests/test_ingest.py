import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import ingest  # noqa: E402
import readers  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")
_TMP = tempfile.mkdtemp()


def bank_csv():
    """The example bank statement as a .csv (the repo keeps no CSV files)."""
    p = os.path.join(_TMP, "bank_statement.csv")
    if not os.path.exists(p):
        shutil.copy(os.path.join(FX, "bank-statement-example.txt"), p)
    return p
SKILL = os.path.join(os.path.dirname(__file__), "..", "..")
BANK = common.load_json(os.path.join(SKILL, "adapters", "example-bank-table.json"))
CARD = common.load_json(os.path.join(SKILL, "adapters", "example-card-pdf.json"))
ADDONS = {"9876": "Spouse"}


def bank_rows():
    return ingest.parse(readers.read_rows(bank_csv()), BANK)


def card_rows(name="card-statement-example.txt"):
    return ingest.parse(readers.read_rows(os.path.join(FX, name)), CARD, ADDONS)


class TestParse(unittest.TestCase):
    def test_parse_table_debit_credit(self):
        t = bank_rows()
        self.assertEqual(len(t), 4)
        self.assertEqual(t[0]["date"], "2026-04-01")
        self.assertEqual(t[0]["amount"], 100000.0)
        self.assertEqual(t[1]["amount"], -2000.0)
        self.assertEqual(t[1]["balance"], 108000.0)
        self.assertEqual(t[1]["account"], "savings-main")

    def test_parse_pdf_text_card(self):
        t = card_rows()
        self.assertEqual(len(t), 6)
        self.assertEqual(t[0]["amount"], -1500.0)
        pay = [x for x in t if "PAYMENT RECEIVED" in x["description"]][0]
        self.assertEqual(pay["amount"], 20000.0)
        self.assertIsNone(t[0]["balance"])

    def test_addon_holder_marked(self):
        t = card_rows()
        self.assertEqual([x["holder"] for x in t], ["", "", "", "", "Spouse", "Spouse"])

    def test_table_card_addon_sections(self):
        # Invented card CSV: a bare card-number row starts each holder's section.
        rows = [["Date", "Ref", "Details", "Amount", "Sign"],
                ["1111222233334444"],
                ["01/09/2026", "1", "GROCER", "500.00", ""],
                ["02/09/2026", "2", "PAYMENT RECEIVED", "500.00", "CR"],
                ["1111222233335555"],
                ["03/09/2026", "3", "PHARMACY", "250.00", ""]]
        ad = {"account": "card-1", "kind": "table", "header_contains": ["Details", "Sign"],
              "columns": {"date": "Date", "description": "Details", "amount": "Amount",
                          "drcr": "Sign", "reference": "Ref"},
              "holder_regex": "^\\d{12}(?P<last4>\\d{4})$", "date_format": "%d/%m/%Y"}
        t = ingest.parse(rows, ad, {"5555": "Spouse"})
        self.assertEqual([x["amount"] for x in t], [-500.0, 500.0, -250.0])
        self.assertEqual([x["holder"] for x in t], ["", "", "Spouse"])

    def test_balance_check_tolerates_intraday_order(self):
        t = bank_rows()
        t[1], t[2] = t[2], t[1]          # same-day rows in another order
        self.assertIsNone(ingest.check_balance(t))

    def test_balance_check_fails_on_missing_row(self):
        t = bank_rows()
        del t[2]
        self.assertIn("balance", ingest.check_balance(t))

    def test_duplicate_purchases_kept_distinct(self):
        t = card_rows()
        ids = [ingest.txn_id(x) for x in ingest.with_occurrence(t)]
        self.assertEqual(len(set(ids)), len(ids))

    def test_balance_check_newest_first(self):
        self.assertIsNone(ingest.check_balance(list(reversed(bank_rows()))))

    def test_balance_check_first_and_last_day_order(self):
        t = bank_rows()
        extra = dict(t[0], amount=-100.0, balance=t[0]["balance"] - 100, description="X")
        t.insert(1, extra)
        for r in t[2:]:
            r["balance"] -= 100
        t[0], t[1] = t[1], t[0]           # first-day rows swapped
        self.assertIsNone(ingest.check_balance(t))
        last = dict(t[-1], amount=-50.0, balance=t[-1]["balance"] - 50, description="Y")
        t.append(last)
        t[-1], t[-2] = t[-2], t[-1]       # last-day rows swapped
        self.assertIsNone(ingest.check_balance(t))


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.ledger = os.path.join(self.d, "ledger.csv")
        self.cov = os.path.join(self.d, "coverage.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_reingest_overlap_is_idempotent(self):
        r1 = ingest.merge(self.ledger, card_rows(), "card-statement-example.txt")
        self.assertEqual(r1, {"added": 6, "skipped": 0})
        r2 = ingest.merge(self.ledger, card_rows(), "card-statement-example.txt")
        self.assertEqual(r2, {"added": 0, "skipped": 6})
        r3 = ingest.merge(self.ledger, card_rows("card-statement-overlap-example.txt"), "overlap.txt")
        self.assertEqual(r3, {"added": 1, "skipped": 2})
        rows = ingest.load_ledger(self.ledger)
        self.assertEqual(len(rows), 7)
        self.assertEqual(list(rows[0].keys()), ingest.LEDGER_COLUMNS)

    def test_coverage_recorded(self):
        ingest.update_coverage(self.cov, "card-1", "2026-04-01", "2026-04-30")
        ingest.update_coverage(self.cov, "card-1", "2026-04-20", "2026-05-31")
        ingest.update_coverage(self.cov, "card-1", "2026-08-01", "2026-08-31")
        c = common.load_json(self.cov)
        self.assertEqual(c["card-1"], [["2026-04-01", "2026-05-31"], ["2026-08-01", "2026-08-31"]])

    def test_ledger_account_column_is_alias(self):
        ingest.merge(self.ledger, bank_rows(), "bank.csv")
        for r in ingest.load_ledger(self.ledger):
            self.assertEqual(r["account"], "savings-main")
            self.assertNotIn("1234", r["account"])
    def test_new_rows_inside_coverage_counted(self):
        ingest.merge(self.ledger, card_rows(), "card.txt")
        ingest.update_coverage(self.cov, "card-1", "2026-04-01", "2026-04-30")
        other = [dict(r, description=r["description"] + " CITY") for r in card_rows()[:2]]
        self.assertEqual(ingest.new_inside_coverage(self.ledger, self.cov, other), 2)
        self.assertEqual(ingest.new_inside_coverage(self.ledger, self.cov, card_rows()), 0)



class TestCli(unittest.TestCase):
    def test_cli_ingests_into_root(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data", "adapters"))
            shutil.copy(os.path.join(SKILL, "adapters", "example-bank-table.json"),
                        os.path.join(root, "data", "adapters", "bank.json"))
            out = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "ingest.py"),
                                  "--root", root, "--adapter", "bank",
                                  "--file", bank_csv()],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn('"added": 4', out.stdout)
            cov = common.load_json(os.path.join(root, "data", "skill-data", "coverage.json"))
            self.assertEqual(cov["savings-main"], [["2026-04-01", "2026-04-03"]])


if __name__ == "__main__":
    unittest.main()
