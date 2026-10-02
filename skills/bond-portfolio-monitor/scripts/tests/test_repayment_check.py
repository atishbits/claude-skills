import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import repayment_check  # noqa: E402

ALPHA = "INE000A07011"


def baseline():
    return {"as_of": "2026-10-02", "expected_cashflows": [
        {"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-10-15", "principal": None,
         "interest_gross": 200.0},
        {"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-11-15", "principal": None,
         "interest_gross": 200.0}]}


def current(received, as_of="2026-11-01"):
    return {"as_of": as_of, "received_cashflows": received}


def paid(date, gross, principal=0.0):
    return {"issuer": "Alpha Finance", "isin": ALPHA, "date": date, "principal": principal,
            "interest_gross": gross}


class TestCheck(unittest.TestCase):
    def test_on_time_payment_raises_no_flag(self):
        result = repayment_check.check(baseline(), current([paid("2026-10-15", 200.0)]))
        self.assertEqual(result["flags"], [])
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["baseline"], "2026-10-02")

    def test_payment_a_few_days_late_still_matches(self):
        result = repayment_check.check(baseline(), current([paid("2026-10-18", 200.0)]))
        self.assertEqual(result["flags"], [])

    def test_missing_payment_is_flagged(self):
        result = repayment_check.check(baseline(), current([]))
        self.assertEqual(len(result["flags"]), 1)
        flag = result["flags"][0]
        self.assertEqual((flag["kind"], flag["date"], flag["expected"], flag["received"]),
                         ("missing", "2026-10-15", 200.0, 0.0))

    def test_short_payment_is_flagged(self):
        result = repayment_check.check(baseline(), current([paid("2026-10-15", 150.0)]))
        self.assertEqual(result["flags"][0]["kind"], "short")
        self.assertEqual(result["flags"][0]["received"], 150.0)

    def test_rounding_difference_is_tolerated(self):
        result = repayment_check.check(baseline(), current([paid("2026-10-15", 199.5)]))
        self.assertEqual(result["flags"], [])

    def test_payment_not_yet_past_grace_is_not_checked(self):
        result = repayment_check.check(baseline(), current([], as_of="2026-10-17"))
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["flags"], [])

    def test_no_baseline_says_so_and_flags_nothing(self):
        result = repayment_check.check(None, current([]))
        self.assertIsNone(result["baseline"])
        self.assertEqual(result["flags"], [])
        self.assertIn("no baseline", result["note"])


class TestPickBaseline(unittest.TestCase):
    def test_baseline_is_strictly_earlier(self):
        older = {"as_of": "2026-09-01"}
        same_day = {"as_of": "2026-10-02"}
        cur = {"as_of": "2026-10-02"}
        self.assertEqual(repayment_check.pick_baseline([older, same_day], cur), older)
        self.assertIsNone(repayment_check.pick_baseline([same_day], cur))


if __name__ == "__main__":
    unittest.main()
