import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fetch_fundamentals as ff  # noqa: E402


class TestNum(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(ff.num("123.45"), 123.45)

    def test_strips_commas(self):
        self.assertEqual(ff.num("1,23,456"), 123456)

    def test_none_input(self):
        self.assertIsNone(ff.num(None))

    def test_empty_string(self):
        self.assertIsNone(ff.num(""))

    def test_non_numeric(self):
        self.assertIsNone(ff.num("demerger"))


class TestToFloat(unittest.TestCase):
    def test_strips_currency_and_percent(self):
        self.assertEqual(ff.to_float("₹1,234.5"), 1234.5)
        self.assertEqual(ff.to_float("12.5%"), 12.5)

    def test_strips_cr_suffix(self):
        self.assertEqual(ff.to_float("4,849 Cr."), 4849)

    def test_empty_is_none(self):
        self.assertIsNone(ff.to_float(""))
        self.assertIsNone(ff.to_float(None))


class TestPctAbove(unittest.TestCase):
    def test_above(self):
        self.assertEqual(ff.pct_above(110, 100), 10.0)

    def test_below(self):
        self.assertEqual(ff.pct_above(90, 100), -10.0)

    def test_missing_price(self):
        self.assertIsNone(ff.pct_above(None, 100))

    def test_zero_level(self):
        self.assertIsNone(ff.pct_above(100, 0))


class TestPctChange(unittest.TestCase):
    def test_yoy_growth(self):
        series = [10, 10, 10, 10, 20]  # index -5 is the "year ago" quarter
        self.assertEqual(ff.pct_change(series), 100.0)

    def test_too_short(self):
        self.assertIsNone(ff.pct_change([1, 2, 3]))

    def test_year_ago_zero(self):
        self.assertIsNone(ff.pct_change([0, 1, 1, 1, 5]))

    def test_none_values(self):
        self.assertIsNone(ff.pct_change([None, 1, 1, 1, 5]))

    def test_decline_uses_abs_denominator(self):
        # year-ago is negative; % change should still be well-defined via abs()
        series = [1, 1, 1, 1, -10]
        self.assertEqual(ff.pct_change(series), -1100.0)


class TestIsFinancial(unittest.TestCase):
    def test_bank_industry_matches(self):
        self.assertTrue(ff.is_financial({"industry": "Private Sector Bank"}, "SOMEBANK"))

    def test_amc_matches_broad_financial_word(self):
        # is_financial is intentionally broad -- ROCE doesn't fit an AMC either.
        self.assertTrue(ff.is_financial({"industry": "Asset Management Company",
                                          "sector": "Financial Services"}, "SOMEAMC"))

    def test_manufacturing_does_not_match(self):
        self.assertFalse(ff.is_financial({"industry": "Aluminium", "sector": "Metals"}, "HINDALCO"))

    def test_ticker_override(self):
        self.assertTrue(ff.is_financial({"industry": "Holding Company"}, "BAJAJFINSV"))


class TestIsLender(unittest.TestCase):
    def test_bank_matches(self):
        self.assertTrue(ff.is_lender({"industry": "Public Sector Bank"}, "SBIN"))

    def test_nbfc_matches(self):
        self.assertTrue(ff.is_lender({"industry": "Non Banking Financial Company (NBFC)"}, "BAJFINANCE"))

    def test_insurance_matches(self):
        self.assertTrue(ff.is_lender({"industry": "Life Insurance"}, "LICI"))

    def test_housing_finance_matches(self):
        self.assertTrue(ff.is_lender({"industry": "Housing Finance Company"}, "SOMEHFC"))

    def test_amc_does_not_match_by_industry(self):
        self.assertFalse(ff.is_lender({"industry": "Asset Management Company"}, "HDFCAMC"))

    def test_exchange_does_not_match(self):
        self.assertFalse(ff.is_lender({"industry": "Exchange and Data Platform"}, "IEX"))

    def test_ticker_override_catches_holding_company(self):
        # BAJAJFINSV's industry label alone ("Holding Company") wouldn't match
        # any lender keyword -- the FINANCIAL_TICKERS override is what catches it.
        self.assertTrue(ff.is_lender({"industry": "Holding Company"}, "BAJAJFINSV"))

    def test_ticker_override_catches_investment_company(self):
        self.assertTrue(ff.is_lender({"industry": "Investment Company"}, "JIOFIN"))

    def test_no_ticker_falls_back_to_industry_only(self):
        self.assertFalse(ff.is_lender({"industry": "Asset Management Company"}))

    def test_non_financial_ticker_not_swept_in(self):
        # A ticker not in the override list must be judged on industry text alone.
        self.assertFalse(ff.is_lender({"industry": "Asset Management Company"}, "HDFCAMC"))


class TestClassify(unittest.TestCase):
    """Signal-row placement: row 1 = cheap + high quality, row 2 = rich + high
    quality, row 3 = rich + low quality, row 4 = cheap + low quality."""

    def test_row1_cheap_and_high_quality(self):
        row, detail = ff.classify(pe=10, roe=20, roce=20,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertEqual(row, 1)

    def test_row2_expensive_and_high_quality(self):
        row, detail = ff.classify(pe=100, roe=20, roce=20,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertEqual(row, 2)

    def test_row3_expensive_and_low_quality(self):
        row, detail = ff.classify(pe=100, roe=2, roce=2,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertEqual(row, 3)

    def test_row4_cheap_and_low_quality(self):
        row, detail = ff.classify(pe=10, roe=2, roce=2,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertEqual(row, 4)

    def test_loss_making_has_no_pe(self):
        row, detail = ff.classify(pe=None, roe=2, roce=2,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertEqual(detail["pe_level"], "none")
        self.assertEqual(row, 3)  # "high" PE lean + low quality

    def test_financial_uses_roe_only(self):
        # ROCE is structurally low for a lender -- classify must not let a low
        # ROCE alone drag a genuinely high-ROE bank into a low-quality row.
        row, detail = ff.classify(pe=10, roe=20, roce=6,
                                   sector_info={"industry": "Public Sector Bank"}, ticker="SBIN")
        self.assertEqual(row, 1)
        self.assertTrue(detail["financial"])

    def test_missing_roe_is_unknown_confidence(self):
        row, detail = ff.classify(pe=10, roe=None, roce=20,
                                   sector_info={"industry": "Aluminium"}, ticker="X")
        self.assertIsNone(row)
        self.assertEqual(detail["confidence"], "none")


class TestParseLots(unittest.TestCase):
    def test_parses_multiple_lots(self):
        lots = ff.parse_lots("2025-11-28 10@381.75; 2026-01-13 1@358.85")
        self.assertEqual(lots, [
            {"date": "2025-11-28", "qty": 10.0, "cost": 381.75},
            {"date": "2026-01-13", "qty": 1.0, "cost": 358.85},
        ])

    def test_non_numeric_cost_kept_as_text(self):
        lots = ff.parse_lots("2024-01-01 5@demerger")
        self.assertEqual(lots, [{"date": "2024-01-01", "qty": 5.0, "cost": "demerger"}])

    def test_none_in_tradebook(self):
        self.assertEqual(ff.parse_lots("None in tradebook"), [])

    def test_empty_cell(self):
        self.assertEqual(ff.parse_lots(""), [])


if __name__ == "__main__":
    unittest.main()
