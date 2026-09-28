import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import multibagger_screen as mb  # noqa: E402

THRESHOLDS = dict(mb.DEFAULT_THRESHOLDS)


def make_record(**overrides):
    """A record that clears every one of the five checks by a comfortable
    margin, and is not near a local low -- override just the fields a test
    cares about."""
    record = {
        "ticker": "ACME",
        "market_cap_cr": 5000.0,
        "roce": 25.0,
        "pe": 20.0,
        "pe_runrate": None,
        "leverage": {"applicable": False, "trend": "flat"},
        "ratio_history": {"roce_fading": False},
        "cash_flow": {"applicable": True, "cfo_to_pat": 0.9},
        "growth_ranges": {"profit_growth": {"5_years": 22.0, "3_years": 20.0}},
        "pct_of_52wk_range": 60.0,
        "technicals": {"pct_vs_dma200": 10.0, "rsi14": 55.0},
    }
    for key, value in overrides.items():
        record[key] = value
    return record


class TestClassifyQuality(unittest.TestCase):
    def test_clean_all_pass_case(self):
        verdict, checks = mb.classify_quality(make_record(), THRESHOLDS)
        self.assertEqual(verdict, "pass")
        for check in checks.values():
            self.assertTrue(check["passed"])
            self.assertIsNone(check["margin"])

    def test_leverage_fail_is_always_fail_never_borderline(self):
        # Leverage fails outright; every other check still comfortably
        # passes, so if leverage were borderline-eligible this would read
        # "borderline" instead -- it must not.
        record = make_record(
            leverage={"applicable": True, "trend": "rising"},
            roce=10.0,  # < 15, satisfies the leverage-fail condition
        )
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertEqual(verdict, "fail")
        self.assertFalse(checks["leverage"]["passed"])
        self.assertIsNone(checks["leverage"]["margin"])

    def test_leverage_fail_even_with_tiny_margins_elsewhere(self):
        # leverage fails via roce_fading; cash_conversion separately misses
        # by a small margin (5% short of the 0.6 floor). Even though that
        # margin alone would read as a borderline-eligible near-miss,
        # leverage's failure must force the overall verdict to "fail".
        record = make_record(
            ratio_history={"roce_fading": True},
            leverage={"applicable": True, "trend": "rising"},
            cash_flow={"applicable": True, "cfo_to_pat": 0.57},
        )
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["leverage"]["passed"])
        self.assertFalse(checks["cash_conversion"]["passed"])
        self.assertLessEqual(checks["cash_conversion"]["margin"], 0.10)
        self.assertEqual(verdict, "fail")

    def test_single_near_miss_within_ten_percent_is_borderline(self):
        # roce_min=18.0; roce=16.4 -> margin = (18-16.4)/18 = 8.89% <= 10%
        record = make_record(roce=16.4)
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertEqual(verdict, "borderline")
        self.assertFalse(checks["roce"]["passed"])
        self.assertAlmostEqual(checks["roce"]["margin"], (18.0 - 16.4) / 18.0)
        self.assertLessEqual(checks["roce"]["margin"], 0.10)

    def test_same_near_miss_at_eleven_percent_is_fail(self):
        # margin = (18 - roce) / 18 = 0.11 -> roce = 18 - 1.98 = 16.02
        record = make_record(roce=16.02)
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        margin = checks["roce"]["margin"]
        self.assertGreater(margin, 0.10)
        self.assertEqual(verdict, "fail")

    def test_two_simultaneous_failures_is_fail_even_if_each_within_ten_percent(self):
        # roce and growth both miss by a small margin individually, but
        # with two of the four margin-eligible checks failing the overall
        # verdict must be "fail", not "borderline".
        record = make_record(
            roce=16.4,   # ~8.9% short on roce_min=18.0
            growth_ranges={"profit_growth": {"5_years": 14.0, "3_years": 13.0}},  # ~6.7% short on 15.0
        )
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["roce"]["passed"])
        self.assertFalse(checks["growth"]["passed"])
        self.assertLessEqual(checks["roce"]["margin"], 0.10)
        self.assertLessEqual(checks["growth"]["margin"], 0.10)
        self.assertEqual(verdict, "fail")

    def test_lender_fails_every_other_check_but_passes_cash_conversion(self):
        record = make_record(
            roce=5.0,
            pe=50.0,
            pe_runrate=None,
            growth_ranges={"profit_growth": {"5_years": 1.0, "3_years": 0.5}},
            cash_flow={"applicable": False, "cfo_to_pat": None},
        )
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["roce"]["passed"])
        self.assertFalse(checks["growth"]["passed"])
        self.assertFalse(checks["pe_growth"]["passed"])
        self.assertTrue(checks["cash_conversion"]["passed"])
        self.assertIsNone(checks["cash_conversion"]["margin"])
        # three of the four margin-eligible checks failed -> fail regardless
        self.assertEqual(verdict, "fail")

    def test_none_roce_fails_with_margin_none_not_borderline_eligible(self):
        record = make_record(roce=None)
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["roce"]["passed"])
        self.assertIsNone(checks["roce"]["margin"])
        # Only one check failed, but its margin is None so it cannot become
        # borderline -- must fall through to fail.
        self.assertEqual(verdict, "fail")

    def test_roce_fading_fails_with_margin_none(self):
        record = make_record(ratio_history={"roce_fading": True})
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["roce"]["passed"])
        self.assertIsNone(checks["roce"]["margin"])
        self.assertEqual(verdict, "fail")

    def test_growth_check_uses_max_of_5y_and_3y(self):
        record = make_record(growth_ranges={"profit_growth": {"5_years": 5.0, "3_years": 25.0}})
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertTrue(checks["growth"]["passed"])
        self.assertEqual(verdict, "pass")

    def test_pe_growth_check_prefers_pe_runrate_over_pe(self):
        # pe is far too high, but pe_runrate is within the multiple -- the
        # check must use pe_runrate.
        record = make_record(pe=100.0, pe_runrate=30.0)  # growth 22.0 (5y) -> allowed 55.0
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertTrue(checks["pe_growth"]["passed"])

    def test_pe_growth_check_fails_when_growth_non_positive(self):
        record = make_record(growth_ranges={"profit_growth": {"5_years": -5.0, "3_years": None}})
        verdict, checks = mb.classify_quality(record, THRESHOLDS)
        self.assertFalse(checks["pe_growth"]["passed"])
        self.assertIsNone(checks["pe_growth"]["margin"])


class TestIsNearLocalLow(unittest.TestCase):
    def test_true_when_both_within_caps(self):
        record = make_record(pct_of_52wk_range=10.0, technicals={"pct_vs_dma200": -2.0, "rsi14": 40.0})
        self.assertTrue(mb.is_near_local_low(record, THRESHOLDS))

    def test_false_when_pct52_over_cap(self):
        record = make_record(pct_of_52wk_range=25.0, technicals={"pct_vs_dma200": -2.0, "rsi14": 40.0})
        self.assertFalse(mb.is_near_local_low(record, THRESHOLDS))

    def test_false_when_pct200dma_over_cap(self):
        record = make_record(pct_of_52wk_range=10.0, technicals={"pct_vs_dma200": 5.0, "rsi14": 40.0})
        self.assertFalse(mb.is_near_local_low(record, THRESHOLDS))

    def test_false_when_either_missing(self):
        record = make_record(pct_of_52wk_range=None, technicals={"pct_vs_dma200": -2.0, "rsi14": 40.0})
        self.assertFalse(mb.is_near_local_low(record, THRESHOLDS))

    def test_independent_of_quality_verdict_pass_but_not_near_low(self):
        record = make_record(pct_of_52wk_range=90.0, technicals={"pct_vs_dma200": 30.0, "rsi14": 60.0})
        verdict, _ = mb.classify_quality(record, THRESHOLDS)
        self.assertEqual(verdict, "pass")
        self.assertFalse(mb.is_near_local_low(record, THRESHOLDS))

    def test_independent_of_quality_verdict_fail_but_near_low(self):
        record = make_record(
            roce=None,
            pct_of_52wk_range=5.0,
            technicals={"pct_vs_dma200": -3.0, "rsi14": 30.0},
        )
        verdict, _ = mb.classify_quality(record, THRESHOLDS)
        self.assertEqual(verdict, "fail")
        self.assertTrue(mb.is_near_local_low(record, THRESHOLDS))


class TestRsiTag(unittest.TestCase):
    def test_oversold_at_or_below_45(self):
        self.assertEqual(mb.rsi_tag(45.0), "oversold")
        self.assertEqual(mb.rsi_tag(20.0), "oversold")

    def test_neutral_above_45(self):
        self.assertEqual(mb.rsi_tag(45.1), "neutral/n/a")

    def test_neutral_when_none(self):
        self.assertEqual(mb.rsi_tag(None), "neutral/n/a")

    def test_rsi_never_affects_near_local_low_or_verdict(self):
        base = make_record(pct_of_52wk_range=5.0, technicals={"pct_vs_dma200": -3.0, "rsi14": 90.0})
        low_rsi = make_record(pct_of_52wk_range=5.0, technicals={"pct_vs_dma200": -3.0, "rsi14": 5.0})
        self.assertEqual(mb.is_near_local_low(base, THRESHOLDS), mb.is_near_local_low(low_rsi, THRESHOLDS))
        v1, _ = mb.classify_quality(base, THRESHOLDS)
        v2, _ = mb.classify_quality(low_rsi, THRESHOLDS)
        self.assertEqual(v1, v2)


class TestRunScreen(unittest.TestCase):
    def test_ticker_filter_restricts_to_named_tickers(self):
        stocks = [make_record(ticker="AAA"), make_record(ticker="BBB"), make_record(ticker="CCC")]
        results = mb.run_screen(stocks, ["bbb"], THRESHOLDS)
        self.assertEqual([r["ticker"] for r in results], ["BBB"])

    def test_no_ticker_filter_screens_everything(self):
        stocks = [make_record(ticker="AAA"), make_record(ticker="BBB")]
        results = mb.run_screen(stocks, [], THRESHOLDS)
        self.assertEqual(len(results), 2)


class TestBuildShortlist(unittest.TestCase):
    def test_shape_has_required_top_level_keys(self):
        stocks = [make_record(ticker="AAA")]
        results = mb.run_screen(stocks, [], THRESHOLDS)
        shortlist = mb.build_shortlist(results, "/tmp/screen-2026-09-28.json", THRESHOLDS)
        self.assertEqual(shortlist["source_file"], "screen-2026-09-28.json")
        self.assertEqual(shortlist["screened"], 1)
        self.assertEqual(shortlist["thresholds"], THRESHOLDS)
        self.assertEqual(len(shortlist["stocks"]), 1)
        self.assertIn("generated_at", shortlist)

    def test_shortlist_includes_every_stock_not_just_survivors(self):
        stocks = [
            make_record(ticker="PASSER"),
            make_record(ticker="FAILER", roce=None),
        ]
        results = mb.run_screen(stocks, [], THRESHOLDS)
        shortlist = mb.build_shortlist(results, "/tmp/screen-2026-09-28.json", THRESHOLDS)
        tickers = {s["ticker"] for s in shortlist["stocks"]}
        self.assertEqual(tickers, {"PASSER", "FAILER"})


if __name__ == "__main__":
    unittest.main()
