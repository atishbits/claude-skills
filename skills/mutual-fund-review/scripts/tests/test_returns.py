import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import returns  # noqa: E402


def tx(date, type_, amount, units=0.0):
    return {"date": date, "type": type_, "amount": amount, "units": units}


def series(start, years, cagr):
    """Daily NAV growing at cagr, weekdays only."""
    d0 = dt.date.fromisoformat(start)
    out = {}
    for k in range(int(365.25 * years) + 1):
        d = d0 + dt.timedelta(days=k)
        if d.weekday() < 5:
            out[d.isoformat()] = 10.0 * (1 + cagr) ** (k / 365.25)
    return out


class TestXirr(unittest.TestCase):
    def test_xirr_simple_year(self):
        self.assertAlmostEqual(returns.xirr([("2025-01-01", -100.0), ("2026-01-01", 110.0)]),
                               0.10, places=3)

    def test_xirr_loss(self):
        self.assertAlmostEqual(returns.xirr([("2025-01-01", -100.0), ("2026-01-01", 90.0)]),
                               -0.10, places=3)

    def test_xirr_one_sign_none(self):
        self.assertIsNone(returns.xirr([("2025-01-01", -1.0)]))
        self.assertIsNone(returns.xirr([]))

    def test_flows_from_tx(self):
        f = returns.flows_from_tx([tx("2025-01-01", "buy", 1000), tx("2025-03-01", "stamp", 1),
                                   tx("2025-06-01", "dividend_payout", 50),
                                   tx("2025-07-01", "sell", 300),
                                   tx("2025-08-01", "dividend_reinvest", 20)])
        self.assertEqual(f, [("2025-01-01", -1000.0), ("2025-06-01", 50.0),
                             ("2025-07-01", 300.0)])


class TestBenchmark(unittest.TestCase):
    def test_same_flows_identical_series_zero_diff(self):
        s = series("2023-01-02", 3, 0.10)
        rows = [tx("2023-06-01", "buy", 1000, 1000 / returns.nav_on(s, "2023-06-01")),
                tx("2024-06-03", "buy", 1000, 1000 / returns.nav_on(s, "2024-06-03"))]
        units = sum(r["units"] for r in rows)
        end = "2025-12-31"
        value = units * returns.nav_on(s, end)
        r = returns.same_flows_benchmark(rows, s, end, value)
        self.assertAlmostEqual(r["diff_pts"], 0.0, places=2)
        self.assertAlmostEqual(r["bench_value"], value, places=2)

    def test_same_flows_sell_reduces_bench_units(self):
        s = series("2023-01-02", 3, 0.0)  # flat at 10
        rows = [tx("2023-06-01", "buy", 1000, 100), tx("2024-06-03", "sell", 400, 40)]
        r = returns.same_flows_benchmark(rows, s, "2025-12-31", 600.0)
        self.assertAlmostEqual(r["bench_value"], 600.0, places=6)

    def test_trailing_cagr(self):
        s = series("2020-01-01", 6, 0.12)
        self.assertAlmostEqual(returns.trailing_cagr(s, "2025-12-31", 5), 0.12, places=2)
        self.assertIsNone(returns.trailing_cagr(s, "2025-12-31", 10))


class TestRolling(unittest.TestCase):
    def test_rolling_counts_and_win_pct(self):
        f, b = series("2020-01-01", 5, 0.12), series("2020-01-01", 5, 0.10)
        r = returns.rolling(f, b, 3, "2024-12-31", hurdle_pct=11.0)
        self.assertGreater(r["windows"], 15)
        self.assertEqual(r["win_pct"], 100.0)
        self.assertAlmostEqual(r["fund_median"], 12.0, places=0)
        self.assertAlmostEqual(r["bench_median"], 10.0, places=0)
        self.assertEqual(r["above_hurdle_pct"], 100.0)
        self.assertEqual(r["bench_above_hurdle_pct"], 0.0)
        self.assertEqual(r["first_start"], "2020-01-01")

    def test_rolling_short_history_none(self):
        f, b = series("2023-01-01", 2, 0.12), series("2023-01-01", 2, 0.10)
        r = returns.rolling(f, b, 3, "2024-12-31")
        self.assertEqual(r["windows"], 0)
        self.assertIsNone(r["fund_median"])
        self.assertIsNone(r["win_pct"])


class TestPeriod(unittest.TestCase):
    def test_period_pnl(self):
        s = series("2024-01-01", 2, 0.0)  # flat at 10
        rows = [tx("2024-01-02", "buy", 1000, 100), tx("2025-03-03", "buy", 500, 50)]
        units_on = lambda d: sum(r["units"] for r in rows if r["date"] <= d)  # noqa: E731
        value_at = lambda d: units_on(d) * 11.0 if d >= "2025-06-01" else units_on(d) * 10.0  # noqa: E731
        p = returns.period_pnl(rows, value_at, "2025-01-01", "2025-12-31")
        self.assertEqual(p["start_value"], 1000.0)
        self.assertEqual(p["end_value"], 1650.0)
        self.assertEqual(p["net_flows"], 500.0)
        self.assertEqual(p["pnl"], 150.0)
        self.assertGreater(p["xirr"], 0)


if __name__ == "__main__":
    unittest.main()
