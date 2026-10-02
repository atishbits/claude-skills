import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cashflows  # noqa: E402
import common  # noqa: E402
import ingest  # noqa: E402
from helpers import BETA, sample_report  # noqa: E402


def snapshot():
    return ingest.build_snapshot(sample_report(), common.load_config(), "2026-10-02", "abc")


class TestCashflows(unittest.TestCase):
    def test_upcoming_is_windowed_and_sorted(self):
        rows = cashflows.upcoming(snapshot(), "2026-10-02", 30)
        self.assertEqual([r["date"] for r in rows], ["2026-10-15", "2026-10-30"])

    def test_monthly_totals(self):
        months = cashflows.monthly(snapshot())
        self.assertEqual(list(months), ["2026-10", "2026-11"])
        self.assertEqual(months["2026-10"], {"amount": 5430.0, "principal": 5000.0,
                                             "interest_net": 430.0, "interest_gross": 450.0,
                                             "tds": 20.0})

    def test_idle_cash_counts_principal_coming_back(self):
        idle = cashflows.idle_cash(snapshot(), "2026-10-02", 45)
        self.assertEqual(idle["total_principal"], 5000.0)
        self.assertEqual(idle["total_interest_net"], 610.0)
        self.assertEqual(idle["total"], 5610.0)
        self.assertEqual(idle["available_by"], "2026-10-30")
        self.assertEqual(idle["events"], [{"date": "2026-10-30", "issuer": "Beta Capital",
                                           "isin": BETA, "principal": 5000.0}])

    def test_idle_cash_with_nothing_due(self):
        idle = cashflows.idle_cash(snapshot(), "2027-06-01", 30)
        self.assertEqual(idle["total"], 0)
        self.assertIsNone(idle["available_by"])
        self.assertEqual(idle["events"], [])

    def test_maturities_in_window(self):
        self.assertEqual(cashflows.maturities(snapshot(), "2026-10-02", 30), [])
        due = cashflows.maturities(snapshot(), "2027-06-01", 45)
        self.assertEqual([m["issuer"] for m in due], ["Beta Capital"])
        self.assertEqual(due[0]["maturity_date"], "2027-06-30")


if __name__ == "__main__":
    unittest.main()
