import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import transfers  # noqa: E402

ACCOUNTS = {"accounts": [
    {"alias": "savings-main", "type": "bank", "last4": "1234"},
    {"alias": "savings-2", "type": "bank", "last4": "5555"},
    {"alias": "card-1", "type": "card", "last4": "4321", "bill_payment_pattern": "CARDPAY"}]}


def t(date, account, amount, category, desc=""):
    return {"date": date, "account": account, "amount": str(amount), "category": category,
            "description": desc or category, "holder": ""}


def run(rows, coverage):
    out, warns = transfers.resolve(rows, ACCOUNTS, coverage)
    return [r["bucket"] for r in out], [r["category"] for r in out], warns


class TestResolve(unittest.TestCase):
    def test_covered_card_payment_excluded(self):
        rows = [t("2026-05-03", "savings-main", -20000, "card_payment", "UPI/CARDPAY/x"),
                t("2026-05-04", "card-1", 20000, "card_payment", "PAYMENT RECEIVED")]
        b, _, w = run(rows, {"card-1": [["2026-04-01", "2026-04-30"]]})
        self.assertEqual(b, ["excluded", "excluded"])
        self.assertEqual(w, [])

    def test_uncovered_card_payment_counts_once(self):
        rows = [t("2026-05-03", "savings-main", -20000, "card_payment", "UPI/CARDPAY/x")]
        b, c, _ = run(rows, {})
        self.assertEqual((b, c), (["spend"], ["card_spend_unexpanded"]))

    def test_unknown_card_payment_counts_once(self):
        rows = [t("2026-05-03", "savings-main", -7000, "card_payment", "UPI/OTHERCARD/x")]
        b, c, _ = run(rows, {"card-1": [["2026-04-01", "2026-04-30"]]})
        self.assertEqual((b, c), (["spend"], ["card_spend_unexpanded"]))

    def test_unmatched_amount_warns(self):
        rows = [t("2026-05-03", "savings-main", -20000, "card_payment", "UPI/CARDPAY/x"),
                t("2026-05-04", "card-1", 19000, "card_payment", "PAYMENT RECEIVED")]
        b, _, w = run(rows, {"card-1": [["2026-04-01", "2026-05-31"]]})
        self.assertEqual(b, ["excluded", "excluded"])
        self.assertEqual([x["kind"] for x in w], ["card_payment_unmatched"])
        self.assertEqual(w[0]["amount"], -20000.0)

    def test_shared_bill_app_matched_to_covered_card_by_amount(self):
        # One bill-pay app pays several cards: its pattern names a card with no
        # statement, but the payment arrived on card-2, whose statement is in.
        acc = {"accounts": ACCOUNTS["accounts"] + [
            {"alias": "cards-via-app", "type": "card", "last4": "", "bill_payment_pattern": "BILLAPP"},
            {"alias": "card-2", "type": "card", "last4": "8888", "bill_payment_pattern": ""}]}
        rows = [t("2026-05-03", "savings-main", -9000, "card_payment", "UPI/BILLAPP/x"),
                t("2026-05-03", "card-2", 9000, "card_payment", "PAYMENT RECEIVED"),
                t("2026-05-05", "savings-main", -4000, "card_payment", "UPI/BILLAPP/y")]
        out, w = transfers.resolve(rows, acc, {"card-2": [["2026-04-01", "2026-05-31"]]})
        self.assertEqual([r["bucket"] for r in out], ["excluded", "excluded", "spend"])
        self.assertEqual(out[2]["category"], "card_spend_unexpanded")
        self.assertEqual(w, [])

    def test_pattern_card_wrong_but_other_covered_card_matches(self):
        acc = {"accounts": ACCOUNTS["accounts"] + [
            {"alias": "card-2", "type": "card", "last4": "8888", "bill_payment_pattern": ""}]}
        rows = [t("2026-05-03", "savings-main", -5000, "card_payment", "UPI/CARDPAY/x"),
                t("2026-05-04", "card-2", 5000, "card_payment", "PAYMENT RECEIVED")]
        cov = {"card-1": [["2026-04-01", "2026-05-31"]], "card-2": [["2026-04-01", "2026-05-31"]]}
        out, w = transfers.resolve(rows, acc, cov)
        self.assertEqual([r["bucket"] for r in out], ["excluded", "excluded"])
        self.assertEqual(w, [])

    def test_own_transfer_pair_excluded(self):
        rows = [t("2026-05-03", "savings-main", -15000, "own_transfer"),
                t("2026-05-04", "savings-2", 15000, "own_transfer")]
        self.assertEqual(run(rows, {})[0], ["excluded", "excluded"])

    def test_own_transfer_to_untracked_is_moved_out(self):
        rows = [t("2026-05-03", "savings-main", -15000, "own_transfer"),
                t("2026-05-09", "savings-main", 3000, "own_transfer")]
        self.assertEqual(run(rows, {})[0], ["own_moved_out", "excluded"])

    def test_flow_buckets(self):
        rows = [t("2026-05-01", "savings-main", 100000, "income"),
                t("2026-05-01", "savings-main", 50, "interest"),
                t("2026-05-02", "savings-main", -350000, "investment:fd"),
                t("2026-05-02", "savings-main", -4000, "tax"),
                t("2026-05-02", "savings-main", -5000, "family_transfer"),
                t("2026-05-02", "card-1", -1500, "fuel"),
                t("2026-05-03", "card-1", 500, "refund")]
        self.assertEqual(run(rows, {})[0],
                         ["income", "income", "invest", "tax", "family", "spend", "spend"])

    def test_unlabelled_money_in_is_not_negative_spend(self):
        rows = [t("2026-05-01", "savings-main", 5000, "uncategorised"),
                t("2026-05-01", "savings-main", 300, "refund"),
                t("2026-05-02", "card-1", 500, "refund"),
                t("2026-05-02", "savings-main", 900, "dining")]
        self.assertEqual(run(rows, {})[0], ["other_in", "spend", "spend", "other_in"])

    def test_first_bill_before_card_coverage_counts_once(self):
        rows = [t("2026-04-03", "savings-main", -20000, "card_payment", "UPI/CARDPAY/x"),
                t("2026-04-04", "card-1", 20000, "card_payment", "PAYMENT RECEIVED")]
        b, c, _ = run(rows, {"card-1": [["2026-03-15", "2026-04-14"]]})
        self.assertEqual((b[0], c[0]), ("spend", "card_spend_unexpanded"))

    def test_unpatterned_bill_matched_by_card_credit(self):
        rows = [t("2026-05-03", "savings-main", -20000, "card_payment", "BILLPAY CC"),
                t("2026-05-05", "card-1", 20000, "card_payment", "PAYMENT RECEIVED")]
        b, _, w = run(rows, {"card-1": [["2026-04-01", "2026-05-31"]]})
        self.assertEqual(b, ["excluded", "excluded"])
        self.assertEqual(w, [])

    def test_card_credit_in_spend_category_reduces_spend(self):
        rows = [t("2026-05-02", "card-1", 500, "shopping", "WEBSHOP REFUND")]
        self.assertEqual(run(rows, {})[0], ["spend"])


if __name__ == "__main__":
    unittest.main()
