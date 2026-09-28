import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import three_year_case as tyc  # noqa: E402


def profit_loss_doc(dates, eps_values):
    """A minimal fragment matching screener's own markup closely enough for
    fetch_fundamentals.parse_table to read it -- real fixture shape, not a
    mock of the parser."""
    header = "".join(f'<th data-date-key="{d}">{d}</th>' for d in dates)
    cells = "".join(f"<td>{v}</td>" for v in eps_values)
    return (
        '<div id="profit-loss"><table>'
        f"<thead><tr>{header}</tr></thead>"
        f'<tbody><tr><td class="text">EPS in Rs</td>{cells}</tr></tbody>'
        "</table></div>"
    )


class TestMedianOf(unittest.TestCase):
    def test_odd_count(self):
        self.assertEqual(tyc.median_of([3, 1, 2]), 2)

    def test_even_count(self):
        self.assertEqual(tyc.median_of([1, 2, 3, 4]), 2.5)

    def test_single_value(self):
        self.assertEqual(tyc.median_of([7]), 7)


class TestPercentileOf(unittest.TestCase):
    def test_empty_series(self):
        self.assertIsNone(tyc.percentile_of(10, []))

    def test_at_bottom(self):
        series = [("y1", 5), ("y2", 10), ("y3", 15), ("y4", 20)]
        self.assertEqual(tyc.percentile_of(5, series), 25)

    def test_at_top(self):
        series = [("y1", 5), ("y2", 10), ("y3", 15), ("y4", 20)]
        self.assertEqual(tyc.percentile_of(20, series), 100)

    def test_above_range(self):
        series = [("y1", 5), ("y2", 10)]
        self.assertEqual(tyc.percentile_of(999, series), 100)


class TestCloseOnOrBefore(unittest.TestCase):
    def test_finds_prior_close(self):
        series = [("2020-01-01", 100.0), ("2020-06-01", 110.0), ("2021-01-01", 120.0)]
        self.assertEqual(tyc.close_on_or_before(series, "2020-12-31"), ("2020-06-01", 110.0))

    def test_no_prior_date(self):
        series = [("2020-06-01", 100.0)]
        self.assertIsNone(tyc.close_on_or_before(series, "2019-01-01"))

    def test_exact_match(self):
        series = [("2020-01-01", 100.0), ("2020-06-01", 110.0)]
        self.assertEqual(tyc.close_on_or_before(series, "2020-06-01"), ("2020-06-01", 110.0))


class TestThreeYearCagr(unittest.TestCase):
    def test_flat_case_zero_cagr(self):
        # exit price == current price -> 0% price CAGR
        out = tyc.three_year_cagr(current_price=100, fwd_eps=10, exit_pe=10, div_yield_pct=0)
        self.assertAlmostEqual(out["exit_price"], 100)
        self.assertAlmostEqual(out["price_cagr_pct"], 0.0, places=6)
        self.assertAlmostEqual(out["total_cagr_pct"], 0.0, places=6)

    def test_doubling_in_three_years(self):
        # exit price = 2x current -> CAGR = 2**(1/3) - 1 ~= 25.99%
        out = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, div_yield_pct=0)
        self.assertAlmostEqual(out["price_cagr_pct"], (2 ** (1 / 3) - 1) * 100, places=4)

    def test_dividend_is_simple_addition(self):
        out = tyc.three_year_cagr(current_price=100, fwd_eps=10, exit_pe=10, div_yield_pct=2.5)
        self.assertAlmostEqual(out["total_cagr_pct"], out["price_cagr_pct"] + 2.5, places=9)

    def test_rejects_non_positive_price(self):
        with self.assertRaises(ValueError):
            tyc.three_year_cagr(current_price=0, fwd_eps=10, exit_pe=10)

    def test_rejects_non_positive_eps(self):
        with self.assertRaises(ValueError):
            tyc.three_year_cagr(current_price=100, fwd_eps=-5, exit_pe=10)

    def test_rejects_non_positive_exit_pe(self):
        with self.assertRaises(ValueError):
            tyc.three_year_cagr(current_price=100, fwd_eps=10, exit_pe=0)

    def test_rejects_non_positive_years(self):
        with self.assertRaises(ValueError):
            tyc.three_year_cagr(current_price=100, fwd_eps=10, exit_pe=10, years=0)

    def test_default_horizon_is_three_years(self):
        out_default = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10)
        out_explicit = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, years=3.0)
        self.assertAlmostEqual(out_default["price_cagr_pct"], out_explicit["price_cagr_pct"], places=9)

    def test_longer_horizon_gives_lower_annualised_cagr_for_same_multiple(self):
        # Same doubling, but over 6 years instead of 3 -> a lower annual rate.
        cagr_3y = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, years=3)["price_cagr_pct"]
        cagr_6y = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, years=6)["price_cagr_pct"]
        self.assertLess(cagr_6y, cagr_3y)

    def test_total_price_return_is_horizon_independent(self):
        # The un-annualised total move is the same regardless of years -- only
        # the annualised CAGR should change with the horizon.
        out_short = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, years=1)
        out_long = tyc.three_year_cagr(current_price=100, fwd_eps=20, exit_pe=10, years=5)
        self.assertAlmostEqual(out_short["total_price_return_pct"], 100.0)
        self.assertAlmostEqual(out_long["total_price_return_pct"], 100.0)
        self.assertNotAlmostEqual(out_short["price_cagr_pct"], out_long["price_cagr_pct"], places=1)

    def test_short_horizon_inflates_annualised_spread_vs_total_spread(self):
        # Same base/bear exit prices; a short horizon should widen the CAGR
        # gap relative to the (horizon-independent) total-return gap -- the
        # exact distortion the ITC/TMCV test runs surfaced.
        base_short = tyc.three_year_cagr(current_price=100, fwd_eps=18, exit_pe=18, years=1.7)
        bear_short = tyc.three_year_cagr(current_price=100, fwd_eps=15, exit_pe=15, years=1.7)
        base_long = tyc.three_year_cagr(current_price=100, fwd_eps=18, exit_pe=18, years=5)
        bear_long = tyc.three_year_cagr(current_price=100, fwd_eps=15, exit_pe=15, years=5)
        total_spread = base_short["total_price_return_pct"] - bear_short["total_price_return_pct"]
        cagr_spread_short = base_short["price_cagr_pct"] - bear_short["price_cagr_pct"]
        cagr_spread_long = base_long["price_cagr_pct"] - bear_long["price_cagr_pct"]
        self.assertAlmostEqual(
            base_long["total_price_return_pct"] - bear_long["total_price_return_pct"], total_spread)
        self.assertGreater(cagr_spread_short, cagr_spread_long)


class TestExitHorizonYears(unittest.TestCase):
    def test_roughly_three_years_out(self):
        today = date(2026, 9, 28)
        # 3 years out plus the 60-day lag this function always adds.
        eps_asof = date(2029, 9, 28)
        years = tyc.exit_horizon_years(eps_asof, today=today)
        self.assertAlmostEqual(years, 3 + 60 / 365.25, places=2)

    def test_rejects_a_past_asof_date(self):
        with self.assertRaises(ValueError):
            tyc.exit_horizon_years(date(2025, 3, 31), today=date(2026, 9, 28))

    def test_asof_date_is_today_gives_just_the_lag(self):
        # Not a rejection -- an FY that ends today still has ~2 months of
        # results/re-rating lag before the exit is "priced in".
        years = tyc.exit_horizon_years(date(2026, 9, 28), today=date(2026, 9, 28))
        self.assertAlmostEqual(years, 60 / 365.25, places=4)


class TestClearsHurdle(unittest.TestCase):
    def test_clears(self):
        clears, margin = tyc.clears_hurdle(total_cagr_pct=12.0, hurdle_cagr_pct=7.0)
        self.assertTrue(clears)
        self.assertAlmostEqual(margin, 5.0)

    def test_does_not_clear(self):
        clears, margin = tyc.clears_hurdle(total_cagr_pct=3.0, hurdle_cagr_pct=7.0)
        self.assertFalse(clears)
        self.assertAlmostEqual(margin, -4.0)

    def test_exactly_at_hurdle_does_not_clear(self):
        # margin == 0 is not a clear -- strictly greater only.
        clears, margin = tyc.clears_hurdle(total_cagr_pct=7.0, hurdle_cagr_pct=7.0)
        self.assertFalse(clears)
        self.assertAlmostEqual(margin, 0.0)


class TestPriceSeries(unittest.TestCase):
    def test_extracts_price_dataset(self):
        chart = {"datasets": [
            {"metric": "DMA50", "values": [["2020-01-01", "1"]]},
            {"metric": "Price", "values": [["2020-01-01", "100.5"], ["2020-01-02", "101.0"]]},
        ]}
        self.assertEqual(tyc.price_series(chart), [("2020-01-01", 100.5), ("2020-01-02", 101.0)])

    def test_none_chart(self):
        self.assertEqual(tyc.price_series(None), [])

    def test_no_price_dataset(self):
        self.assertEqual(tyc.price_series({"datasets": [{"metric": "Volume", "values": []}]}), [])


class TestPeBand(unittest.TestCase):
    """The real behaviour under test: excluding non-positive and near-zero
    EPS years so a distortion year can't corrupt the band (the SBIN FY17
    case -- EPS 0.30 against a ~40 median gave a nonsensical 978x P/E before
    this exclusion existed)."""

    def test_excludes_negative_and_near_zero_eps(self):
        dates = ["2020-03-31", "2021-03-31", "2022-03-31", "2023-03-31", "2024-03-31"]
        eps = [-5.11, 0.30, 22.15, 25.11, 39.64]
        doc = profit_loss_doc(dates, eps)
        series = [(d, 1000.0) for d in dates]  # flat price simplifies expected P/E
        valid, excluded, latest_eps = tyc.pe_band(doc, series, years=5)
        valid_years = {y for y, _ in valid}
        self.assertNotIn("2020-03-31", valid_years)  # negative EPS
        self.assertNotIn("2021-03-31", valid_years)  # near-zero outlier
        self.assertIn("2022-03-31", valid_years)
        self.assertIn("2023-03-31", valid_years)
        self.assertIn("2024-03-31", valid_years)
        self.assertEqual(len(excluded), 2)

    def test_normal_years_all_valid(self):
        dates = ["2022-03-31", "2023-03-31", "2024-03-31"]
        eps = [10.0, 12.0, 15.0]
        doc = profit_loss_doc(dates, eps)
        series = [(d, 100.0) for d in dates]
        valid, excluded, latest_eps = tyc.pe_band(doc, series, years=3)
        self.assertEqual(len(valid), 3)
        self.assertEqual(excluded, [])

    def test_no_eps_row_returns_empty(self):
        doc = '<div id="profit-loss"><table><tbody></tbody></table></div>'
        valid, excluded, latest_eps = tyc.pe_band(doc, [], years=5)
        self.assertEqual(valid, [])
        self.assertEqual(excluded, [])
        self.assertIsNone(latest_eps)

    def test_price_before_chart_history_is_excluded(self):
        dates = ["2015-03-31", "2020-03-31"]
        eps = [10.0, 12.0]
        doc = profit_loss_doc(dates, eps)
        series = [("2020-03-31", 100.0)]  # chart only covers the later year
        valid, excluded, latest_eps = tyc.pe_band(doc, series, years=2)
        self.assertEqual([y for y, _ in valid], ["2020-03-31"])
        self.assertEqual(excluded, [("2015-03-31", "before the chart's history starts")])


if __name__ == "__main__":
    unittest.main()
