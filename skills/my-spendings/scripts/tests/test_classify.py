import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import classify  # noqa: E402
import common  # noqa: E402

SKILL = os.path.join(os.path.dirname(__file__), "..", "..")
ACCOUNTS = common.load_json(os.path.join(SKILL, "accounts-template.json"))
DEFAULTS = classify.load_default_rules()


def tx(desc, amount, account="savings-main"):
    return {"description": desc, "amount": str(amount), "account": account, "date": "2026-04-01",
            "holder": ""}


def cat(desc, amount, account="savings-main", user=()):
    return classify.classify(tx(desc, amount, account), list(user), DEFAULTS, ACCOUNTS)


class TestClassify(unittest.TestCase):
    def test_user_rule_beats_default(self):
        user = [classify.Rule("FUELCO", "groceries", "any")]
        self.assertEqual(cat("UPI/FUELCO PUMP/x", -500, user=user), "groceries")

    def test_fuel_keyword(self):
        self.assertEqual(cat("POS CITY PETROL STATION", -1500), "fuel")
        self.assertEqual(cat("FUELCO FILLING STATION", -1500, "card-1"), "fuel")

    def test_salary_only_inbound(self):
        self.assertEqual(cat("CMS/ SALARY 2026APR EXAMPLE CORP", 100000), "income")
        self.assertNotEqual(cat("UPI/HELPER/anil salary", -2000), "income")

    def test_self_transfer_from_accounts_json(self):
        self.assertEqual(cat("MMT/IMPS/611612/JANE DOE/ABCD0123", -15000), "own_transfer")

    def test_family_transfer(self):
        self.assertEqual(cat("NEFT/JOHN DOE/Family", -5000), "family_transfer")

    def test_bill_payment_pattern_marks_card_payment(self):
        self.assertEqual(cat("UPI/CARDPAY/cardpay@acme/payment on", -20000), "card_payment")
        self.assertEqual(cat("PAYMENT RECEIVED THANK YOU", 20000, "card-1"), "card_payment")

    def test_card_refund_is_negative_spend(self):
        self.assertEqual(cat("SHOPMART REFUND", 500, "card-1"), "refund")

    def test_fees_and_tax(self):
        self.assertEqual(cat("ANNUAL FEE + GST", -590, "card-1"), "fees_charges")
        self.assertEqual(cat("UPI/DTAX/advance tax", -40000), "tax")
        self.assertEqual(cat("TRF TO FD no. 1234", -350000), "investment:fd")

    def test_fee_word_in_upi_note_is_not_bank_fee(self):
        self.assertNotEqual(cat("UPI/ACADEMY/academy@okx/Paying Fee/ACME BANK/1", -8000), "fees_charges")
        self.assertEqual(cat("LATE PAYMENT FEE", -500, "card-1"), "fees_charges")
        self.assertEqual(cat("PROCESSING FEE", -199, "card-1"), "fees_charges")

    def test_unknown_is_uncategorised(self):
        self.assertEqual(cat("UPI/ZQXWV/abc@okx", -999), "uncategorised")

    def test_classify_all_adds_category_and_payee(self):
        out = classify.classify_all([tx("UPI/FUELCO PUMP/x PETROL", -500)], [], DEFAULTS, ACCOUNTS)
        self.assertEqual((out[0]["category"], out[0]["payee"]), ("fuel", "FUELCO"))

    def test_uncategorised_top_payees_sorted_by_total(self):
        rows = classify.classify_all([tx("UPI/AAAA/x", -100), tx("UPI/BBBB/x", -900),
                                      tx("UPI/AAAA/y", -100)], [], DEFAULTS, ACCOUNTS)
        u = classify.uncategorised(rows)
        self.assertEqual([x["payee"] for x in u], ["BBBB", "AAAA"])
        self.assertEqual(u[1], {"payee": "AAAA", "count": 2, "total": -200.0})

    def test_default_rule_categories_are_known(self):
        for r in DEFAULTS:
            self.assertIn(r.category, classify.CATEGORIES, r.pattern)


class TestAddRule(unittest.TestCase):
    def run_cli(self, root, *args):
        return subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "classify.py"),
                               "--root", root, *args], capture_output=True, text=True)

    def test_add_rule_rejects_bad_regex_and_unknown_category(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            self.assertNotEqual(self.run_cli(root, "add-rule", "--pattern", "(", "--category", "fuel").returncode, 0)
            self.assertNotEqual(self.run_cli(root, "add-rule", "--pattern", "X", "--category", "nope").returncode, 0)
            ok = self.run_cli(root, "add-rule", "--pattern", "ZQXWV", "--category", "dining")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            rules = classify.load_rules(os.path.join(root, "data", "rules.csv"))
            self.assertEqual([(r.pattern, r.category, r.direction) for r in rules],
                             [("ZQXWV", "dining", "any")])


if __name__ == "__main__":
    unittest.main()
