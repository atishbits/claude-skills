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


class TestOverdue(unittest.TestCase):
    """A payment the report still lists as upcoming although its date has
    passed, with no receipt recorded: detectable from one snapshot."""

    def snap(self, received, as_of="2026-10-02"):
        return {"as_of": as_of, "received_cashflows": received, "expected_cashflows": [
            {"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-09-21", "principal": 3000.0,
             "interest_gross": 400.0},
            {"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-10-01", "principal": None,
             "interest_gross": 80.0},
            {"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-10-21", "principal": None,
             "interest_gross": 80.0}]}

    def test_past_due_with_no_receipt_is_flagged_with_days_late(self):
        flags = repayment_check.overdue(self.snap([]))
        self.assertEqual(flags, [{"issuer": "Alpha Finance", "isin": ALPHA, "date": "2026-09-21",
                                  "expected": 3400.0, "received": 0.0, "days_late": 11,
                                  "kind": "overdue"}])

    def test_within_grace_or_in_future_is_not_flagged(self):
        dates = [f["date"] for f in repayment_check.overdue(self.snap([]))]
        self.assertNotIn("2026-10-01", dates)
        self.assertNotIn("2026-10-21", dates)

    def test_receipt_near_the_due_date_clears_it(self):
        self.assertEqual(repayment_check.overdue(self.snap([paid("2026-09-22", 400.0, 3000.0)])), [])

    def test_part_payment_is_still_flagged(self):
        flags = repayment_check.overdue(self.snap([paid("2026-09-21", 400.0)]))
        self.assertEqual(flags[0]["received"], 400.0)


class TestPickBaseline(unittest.TestCase):
    def test_baseline_is_strictly_earlier(self):
        older = {"as_of": "2026-09-01"}
        same_day = {"as_of": "2026-10-02"}
        cur = {"as_of": "2026-10-02"}
        self.assertEqual(repayment_check.earlier_snapshots([older, same_day], cur), [older])
        self.assertEqual(repayment_check.earlier_snapshots([same_day], cur), [])



class TestReviewFindings(unittest.TestCase):
    def due(self, date, gross=0.0, principal=None):
        return {"issuer": "Alpha Finance", "isin": ALPHA, "date": date, "principal": principal,
                "interest_gross": gross}

    def test_close_snapshots_still_check_a_due_from_an_older_schedule(self):
        earlier = [{"as_of": "2026-10-01", "expected_cashflows": [self.due("2026-10-03", 200.0)]},
                   {"as_of": "2026-10-04", "expected_cashflows": []},
                   {"as_of": "2026-10-07", "expected_cashflows": []}]
        result = repayment_check.check(earlier, current([], as_of="2026-10-10"))
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["flags"][0]["kind"], "missing")
        self.assertEqual(result["flags"][0]["date"], "2026-10-03")

    def test_due_just_before_a_monthly_snapshot_is_checked_next_time(self):
        earlier = [{"as_of": "2026-10-01", "expected_cashflows": [self.due("2026-10-30", 200.0)]},
                   {"as_of": "2026-11-01", "expected_cashflows": []}]
        result = repayment_check.check(earlier, current([], as_of="2026-12-01"))
        self.assertEqual([f["date"] for f in result["flags"]], ["2026-10-30"])

    def test_newest_schedule_before_the_due_date_wins(self):
        earlier = [{"as_of": "2026-10-01", "expected_cashflows": [self.due("2026-10-20", 200.0)]},
                   {"as_of": "2026-10-10", "expected_cashflows": [self.due("2026-10-20", 150.0)]}]
        result = repayment_check.check(earlier, current([paid("2026-10-20", 150.0)]))
        self.assertEqual(result["flags"], [])

    def test_same_date_rows_for_one_bond_are_summed(self):
        base = {"as_of": "2026-10-02", "expected_cashflows": [
            self.due("2026-10-15", 100.0), self.due("2026-10-15", 0.0, principal=10000.0)]}
        result = repayment_check.check(base, current([paid("2026-10-15", 0.0, 10000.0)]))
        self.assertEqual(result["checked"], 1)
        flag = result["flags"][0]
        self.assertEqual((flag["kind"], flag["expected"], flag["received"]),
                         ("short", 10100.0, 10000.0))

    def test_overdue_sums_same_date_rows_too(self):
        snap = {"as_of": "2026-10-02", "received_cashflows": [paid("2026-09-21", 0.0, 10000.0)],
                "expected_cashflows": [self.due("2026-09-21", 100.0),
                                       self.due("2026-09-21", 0.0, principal=10000.0)]}
        flags = repayment_check.overdue(snap)
        self.assertEqual((flags[0]["expected"], flags[0]["received"]), (10100.0, 10000.0))

    def test_nothing_checkable_is_said_plainly(self):
        result = repayment_check.check(baseline(), current([], as_of="2026-10-05"))
        self.assertEqual(result["checked"], 0)
        self.assertIn("nothing was checkable", result["note"])


if __name__ == "__main__":
    unittest.main()
