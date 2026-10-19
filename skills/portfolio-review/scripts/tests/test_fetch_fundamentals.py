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
        lots = ff.parse_lots("2025-06-02 10@400.00; 2025-09-15 1@350.00")
        self.assertEqual(lots, [
            {"date": "2025-06-02", "qty": 10.0, "cost": 400.0},
            {"date": "2025-09-15", "qty": 1.0, "cost": 350.0},
        ])

    def test_non_numeric_cost_kept_as_text(self):
        lots = ff.parse_lots("2024-01-01 5@demerger")
        self.assertEqual(lots, [{"date": "2024-01-01", "qty": 5.0, "cost": "demerger"}])

    def test_none_in_tradebook(self):
        self.assertEqual(ff.parse_lots("None in tradebook"), [])

    def test_empty_cell(self):
        self.assertEqual(ff.parse_lots(""), [])


class TestRupees(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(ff._rupees("₹1,500"), 1500.0)

    def test_negative(self):
        self.assertEqual(ff._rupees("-60,000"), -60000.0)

    def test_k_suffix(self):
        self.assertEqual(ff._rupees("12.5k"), 12500.0)

    def test_none(self):
        self.assertIsNone(ff._rupees(None))


class TestParseTaxPosition(unittest.TestCase):
    SAMPLE = """\
## Tax position FY 2026-27 (broker tax P&L, Q1-Q2)

- Realised STCG: ₹0 · Realised LTCG: ₹1,500 · Charges ₹100
- Broker's tax-loss harvesting page: unrealised STCL ₹12.5k, unrealised LTCL ₹7.5k (includes MFs); 'save up to' ₹200
- Stocks only (lot-level, this file): unrealised LT gains ₹40,000 · LT losses ₹-60,000 · ST gains ₹10,000 · ST losses ₹-20,000
- Rates: STCG 20%, LTCG 12.5% above ₹1.25L/yr exemption.

## Holdings with lots
"""

    def test_parses_real_shaped_section(self):
        out = ff.parse_tax_position(self.SAMPLE)
        self.assertEqual(out["fy"], "FY 2026-27")
        self.assertEqual(out["realised_stcg"], 0.0)
        self.assertEqual(out["realised_ltcg"], 1500.0)
        self.assertEqual(out["broker_harvest_savings"], 200.0)
        self.assertEqual(out["stocks_only"], {
            "lt_gains": 40000.0, "lt_losses": -60000.0,
            "st_gains": 10000.0, "st_losses": -20000.0,
        })

    def test_absent_section_returns_none(self):
        self.assertIsNone(ff.parse_tax_position("## Holdings with lots\n"))

    def test_empty_text_returns_none(self):
        self.assertIsNone(ff.parse_tax_position(""))


class TestReadHoldingsMd(unittest.TestCase):
    """A row with fewer cells than the template's 13 columns must be skipped,
    not crash the whole parse -- an earlier version's `len(cells) < 12`
    guard let a 12-cell row through into a 13-name unpack."""

    HEADER = ("## Holdings with lots\n\n"
              "| Symbol | Qty | Avg ₹ | LTP ₹ | Value ₹ | P&L ₹ | P&L % | LT qty | ST qty | "
              "Next lot turns LT | Unrealised LT / ST ₹ | Sector | Lots (date qty@cost) |\n"
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|---|---|---|---|\n")

    def write(self, tmp_path, body):
        path = os.path.join(tmp_path, "broker-portfolio-2026-09-27.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.HEADER + body)
        return path

    def test_full_row_parses(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            row = ("| EXAMPLEA | 10 | 100.00 | 120.00 | 1200 | 200 | 20.0% | 10 | 0 | - | "
                   "+0 / +0 | IT | 2024-01-01 10@100.00 |\n")
            path = self.write(tmp, row)
            holdings = ff.read_holdings_md(path)
            self.assertEqual(len(holdings), 1)
            self.assertEqual(holdings[0]["ticker"], "EXAMPLEA")

    def test_short_row_is_skipped_not_a_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # 12 cells -- one short of the required 13 (missing Lots column
            # and its separating pipe).
            short_row = ("| EXAMPLEA | 10 | 100.00 | 120.00 | 1200 | 200 | 20.0% | 10 | 0 | - | "
                         "+0 / +0 | IT |\n")
            good_row = ("| EXAMPLEB | 5 | 500.00 | 450.00 | 2250 | -250 | -10.0% | 5 | 0 | - | "
                        "+0 / +0 | IT | 2024-01-01 5@500.00 |\n")
            path = self.write(tmp, short_row + good_row)
            holdings = ff.read_holdings_md(path)  # must not raise
            self.assertEqual([h["ticker"] for h in holdings], ["EXAMPLEB"])


class TestParseArgs(unittest.TestCase):
    """A pure-function test of the CLI parsing -- no network involved. `--root`
    resets `ff.ROOT` as a side effect, so each test restores it."""

    def setUp(self):
        self.saved_root = ff.ROOT

    def tearDown(self):
        ff.set_root(self.saved_root)

    def test_scan_parses_index_name(self):
        force, screen, only, nse, scan_index = ff.parse_args(["--scan", "NIFTY MIDCAP 150"])
        self.assertEqual(scan_index, "NIFTY MIDCAP 150")
        self.assertFalse(force)
        self.assertFalse(screen)
        self.assertEqual(only, [])
        self.assertTrue(nse)

    def test_scan_with_screen_exits(self):
        with self.assertRaises(SystemExit):
            ff.parse_args(["--scan", "NIFTY 500", "--screen", "TICKER"])

    def test_scan_with_bare_ticker_exits(self):
        with self.assertRaises(SystemExit):
            ff.parse_args(["--scan", "NIFTY 500", "TICKER"])


class TestRunScanEmptyConstituents(unittest.TestCase):
    """A mistyped index name comes back from NSE as HTTP 200 with no rows.
    run_scan must exit before writing anything, so an existing same-day
    screen file survives."""

    def setUp(self):
        import tempfile
        self.saved_root = ff.ROOT
        self.saved_fetch = ff.nse_index.fetch_constituents
        self.tmp = tempfile.TemporaryDirectory()
        ff.set_root(self.tmp.name)

    def tearDown(self):
        ff.nse_index.fetch_constituents = self.saved_fetch
        ff.set_root(self.saved_root)
        self.tmp.cleanup()

    def test_empty_list_exits_and_leaves_existing_screen_file_untouched(self):
        from datetime import date
        os.makedirs(ff.SKILL_DATA_DIR, exist_ok=True)
        existing = os.path.join(ff.SKILL_DATA_DIR, f"screen-{date.today().isoformat()}.json")
        with open(existing, "w", encoding="utf-8") as fh:
            fh.write('{"stocks": [{"ticker": "ZENTRO"}]}')
        ff.nse_index.fetch_constituents = lambda index_name: []
        with self.assertRaises(SystemExit) as ctx:
            ff.run_scan("NIFTY TYPO 999", held=[], force=False, use_nse=False)
        self.assertIn("NIFTY TYPO 999", str(ctx.exception.code))
        self.assertIn("--screen", str(ctx.exception.code))
        with open(existing, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{"stocks": [{"ticker": "ZENTRO"}]}')
        self.assertEqual(os.listdir(ff.SKILL_DATA_DIR), [os.path.basename(existing)])


class TestLatestHoldingsFile(unittest.TestCase):
    """A freshly-downloaded export can land with an older mtime than a stale
    file still sitting in the folder (a cloud-synced copy, a moved file).
    Selection must go by the date in the filename, not mtime."""

    def test_prefers_filename_date_over_mtime(self):
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as tmp:
            saved_root = ff.ROOT
            try:
                ff.set_root(tmp)
                os.makedirs(ff.DATA_DIR, exist_ok=True)
                old = os.path.join(ff.DATA_DIR, "broker_holdings_2025-01-01.csv")
                new = os.path.join(ff.DATA_DIR, "broker_holdings_2026-09-27.csv")
                # Write the "new" (by filename date) file first so its mtime is
                # OLDER than the "old" file's -- the failure mode this guards.
                # Selection is by filename/mtime only, so the content just
                # needs to exist -- not a real (or even realistic) export.
                with open(new, "w") as fh:
                    fh.write("placeholder\n")
                time.sleep(0.01)
                with open(old, "w") as fh:
                    fh.write("placeholder\n")
                self.assertGreater(os.path.getmtime(old), os.path.getmtime(new))

                picked = ff.latest_holdings_files()
                self.assertEqual([os.path.basename(p) for p in picked], ["broker_holdings_2026-09-27.csv"])
            finally:
                ff.set_root(saved_root)


class TestHoldingsPerBroker(unittest.TestCase):
    """Accounts at more than one broker: the newest export of each broker is
    read and merged, so one broker's export never hides another's holdings."""

    def _files(self, names):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        saved_root = ff.ROOT
        self.addCleanup(ff.set_root, saved_root)
        ff.set_root(tmp.name)
        os.makedirs(ff.DATA_DIR, exist_ok=True)
        for name in names:
            with open(os.path.join(ff.DATA_DIR, name), "w") as fh:
                fh.write("placeholder\n")

    def test_broker_of(self):
        self.assertEqual(ff.broker_of("alphabroker_holdings_2026-10-01.csv"), "alphabroker")
        self.assertEqual(ff.broker_of("alphabroker-portfolio-2026-10-01.md"), "alphabroker")
        self.assertEqual(ff.broker_of("Beta-Broker_holdings_6September2026.csv"), "beta-broker")
        self.assertEqual(ff.broker_of("holdings.csv"), "")

    def test_newest_export_of_each_broker(self):
        self._files(["alphabroker_holdings_2026-09-01.csv", "alphabroker_holdings_2026-10-01.csv",
                     "betabroker-portfolio-2026-08-01.md"])
        picked = [os.path.basename(p) for p in ff.latest_holdings_files()]
        self.assertEqual(picked, ["alphabroker_holdings_2026-10-01.csv",
                                  "betabroker-portfolio-2026-08-01.md"])

    def test_same_day_prefers_lot_level_export(self):
        self._files(["alphabroker-portfolio-2026-10-01.md", "alphabroker_holdings_2026-10-01.csv"])
        picked = [os.path.basename(p) for p in ff.latest_holdings_files()]
        self.assertEqual(picked, ["alphabroker-portfolio-2026-10-01.md"])

    def test_none_found(self):
        self._files([])
        self.assertEqual(ff.latest_holdings_files(required=False), [])
        with self.assertRaises(SystemExit):
            ff.latest_holdings_files()

    def test_merge_combines_a_stock_held_at_two_brokers(self):
        a = [{"ticker": "TESTCO", "qty": 10.0, "avg_cost": 100.0, "ltp": 150.0, "invested": 1000.0,
              "current_value": 1500.0, "pnl": 500.0, "pnl_pct": 50.0, "lt_qty": 10.0, "st_qty": 0.0,
              "next_lot_turns_lt": None, "unrealized_lt_pnl": 500.0, "unrealized_st_pnl": 0.0,
              "broker_sector": "Industrials", "lots": [{"date": "2024-01-02", "qty": 10.0, "cost": 100.0}]},
             {"ticker": "ONLYA", "qty": 1.0, "avg_cost": 50.0, "ltp": 40.0, "invested": 50.0,
              "current_value": 40.0, "pnl": -10.0, "pnl_pct": -20.0}]
        b = [{"ticker": "TESTCO", "qty": 30.0, "avg_cost": 200.0, "ltp": 150.0, "invested": 6000.0,
              "current_value": 4500.0, "pnl": -1500.0, "pnl_pct": -25.0, "lt_qty": 0.0, "st_qty": 30.0,
              "next_lot_turns_lt": "2026-12-01", "unrealized_lt_pnl": 0.0, "unrealized_st_pnl": -1500.0,
              "broker_sector": None, "lots": [{"date": "2025-11-30", "qty": 30.0, "cost": 200.0}]}]
        merged = ff.merge_holdings([("alphabroker", a), ("betabroker", b)])
        self.assertEqual([h["ticker"] for h in merged], ["ONLYA", "TESTCO"])
        t = merged[1]
        self.assertEqual(t["qty"], 40.0)
        self.assertEqual(t["invested"], 7000.0)
        self.assertEqual(t["avg_cost"], 175.0)
        self.assertEqual(t["current_value"], 6000.0)
        self.assertEqual(t["pnl"], -1000.0)
        self.assertAlmostEqual(t["pnl_pct"], -1000.0 / 7000.0 * 100)
        self.assertEqual((t["lt_qty"], t["st_qty"]), (10.0, 30.0))
        self.assertEqual(t["next_lot_turns_lt"], "2026-12-01")
        self.assertEqual((t["unrealized_lt_pnl"], t["unrealized_st_pnl"]), (500.0, -1500.0))
        self.assertEqual(t["broker_sector"], "Industrials")
        self.assertEqual(t["brokers"], {"alphabroker": 10.0, "betabroker": 30.0})
        self.assertEqual([(l["date"], l["broker"]) for l in t["lots"]],
                         [("2024-01-02", "alphabroker"), ("2025-11-30", "betabroker")])
        self.assertEqual(merged[0]["brokers"], {"alphabroker": 1.0})

    def test_merge_unknown_lot_split_stays_unknown(self):
        a = [{"ticker": "TESTCO", "qty": 1.0, "avg_cost": 10.0, "ltp": 10.0, "invested": 10.0,
              "current_value": 10.0, "pnl": 0.0, "pnl_pct": 0.0}]                 # plain CSV: no lot split
        b = [{"ticker": "TESTCO", "qty": 2.0, "avg_cost": 10.0, "ltp": 10.0, "invested": 20.0,
              "current_value": 20.0, "pnl": 0.0, "pnl_pct": 0.0, "lt_qty": 2.0, "st_qty": 0.0,
              "next_lot_turns_lt": None, "unrealized_lt_pnl": 0.0, "unrealized_st_pnl": 0.0, "lots": []}]
        t = ff.merge_holdings([("alphabroker", a), ("betabroker", b)])[0]
        self.assertIsNone(t["lt_qty"])
        self.assertIsNone(t["st_qty"])
        self.assertIsNone(t["unrealized_lt_pnl"])

    def test_single_broker_is_unchanged_apart_from_tags(self):
        a = [{"ticker": "TESTCO", "qty": 3.0, "avg_cost": 10.0, "ltp": 12.0, "invested": 30.0,
              "current_value": 36.0, "pnl": 6.0, "pnl_pct": 20.0}]
        t = ff.merge_holdings([("alphabroker", a)])[0]
        self.assertEqual({k: t[k] for k in a[0]}, a[0])
        self.assertNotIn("lt_qty", t)

    def test_tax_positions_add_realised_gains(self):
        one = {"fy": "FY 2026-27", "realised_stcg": 100.0, "realised_ltcg": 1000.0,
               "broker_harvest_savings": 50.0,
               "stocks_only": {"lt_gains": 1.0, "lt_losses": -2.0, "st_gains": 3.0, "st_losses": -4.0}}
        two = {"fy": "FY 2026-27", "realised_stcg": 10.0, "realised_ltcg": 0.0}
        self.assertIsNone(ff.merge_tax_positions([None, None]))
        self.assertIs(ff.merge_tax_positions([None, one]), one)
        both = ff.merge_tax_positions([one, two])
        self.assertEqual((both["realised_stcg"], both["realised_ltcg"]), (110.0, 1000.0))
        self.assertEqual(both["broker_harvest_savings"], 50.0)
        self.assertEqual(both["stocks_only"], one["stocks_only"])
        self.assertEqual(both["fy"], "FY 2026-27")


class TestLoadPortfolio(unittest.TestCase):
    """What a run reads: every broker's newest export, merged."""

    def test_two_brokers_merged_with_tax_position_and_oldest_date(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            saved_root = ff.ROOT
            self.addCleanup(ff.set_root, saved_root)
            ff.set_root(tmp)
            os.makedirs(ff.DATA_DIR, exist_ok=True)
            with open(os.path.join(ff.DATA_DIR, "alphabroker_holdings_2026-10-02.csv"), "w") as fh:
                # Column header from the skill's own template: the format is
                # documented there, and only template files may carry it.
                template = os.path.join(os.path.dirname(__file__), "..", "..", "holdings-template.csv")
                with open(template, encoding="utf-8") as tf:
                    header = tf.readline()
                fh.write(header +
                         "TESTCO,10,100,150,1000,1500,500,50\n"
                         "ONLYA,1,50,40,50,40,-10,-20\n")
            with open(os.path.join(ff.DATA_DIR, "betabroker-portfolio-2026-10-01.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("## Tax position FY 2026-27 (broker)\n\n"
                         "- Realised STCG: ₹10 · Realised LTCG: ₹20\n\n"
                         + TestReadHoldingsMd.HEADER +
                         "| TESTCO | 30 | 200.00 | 150.00 | 4500 | -1500 | -25.0% | 30 | 0 | all LT | "
                         "-1500 / +0 | IT | 2024-01-01 30@200.00 |\n")
            paths, held, as_of, tax = ff.load_portfolio()
            self.assertEqual([os.path.basename(p) for p in paths],
                             ["alphabroker_holdings_2026-10-02.csv", "betabroker-portfolio-2026-10-01.md"])
            self.assertEqual(as_of, "2026-10-01")
            testco = next(h for h in held if h["ticker"] == "TESTCO")
            self.assertEqual(testco["qty"], 40.0)
            self.assertEqual(testco["brokers"], {"alphabroker": 10.0, "betabroker": 30.0})
            self.assertEqual((tax["realised_stcg"], tax["realised_ltcg"]), (10.0, 20.0))

    def test_no_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            saved_root = ff.ROOT
            self.addCleanup(ff.set_root, saved_root)
            ff.set_root(tmp)
            self.assertEqual(ff.load_portfolio(required=False), ([], [], None, None))


class TestSlugOverrides(unittest.TestCase):
    """The broker-symbol -> slug map is the user's own data/slug-overrides.json."""

    def run_in(self, content):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            saved_root = ff.ROOT
            try:
                ff.set_root(tmp)
                os.makedirs(ff.DATA_DIR, exist_ok=True)
                if content is not None:
                    with open(os.path.join(ff.DATA_DIR, "slug-overrides.json"), "w") as fh:
                        fh.write(content)
                return ff.slug_overrides()
            finally:
                ff.set_root(saved_root)

    def test_reads_the_map_and_uppercases_symbols(self):
        self.assertEqual(self.run_in('{"examplea-rr": "EXAMPLEA"}'), {"EXAMPLEA-RR": "EXAMPLEA"})

    def test_no_file_means_no_overrides(self):
        self.assertEqual(self.run_in(None), {})

    def test_unreadable_or_wrong_shape_means_no_overrides(self):
        self.assertEqual(self.run_in("not json"), {})
        self.assertEqual(self.run_in('["EXAMPLEA"]'), {})


if __name__ == "__main__":
    unittest.main()
