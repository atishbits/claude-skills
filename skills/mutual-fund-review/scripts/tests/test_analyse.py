import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyse  # noqa: E402
import common  # noqa: E402
import freshness  # noqa: E402
import ledger  # noqa: E402
import report  # noqa: E402

FOLIO = "5555666677"


def series(start, end, cagr, base=10.0):
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out, d = {}, d0
    while d <= d1:
        if d.weekday() < 5:
            out[d.isoformat()] = base * (1 + cagr) ** ((d - d0).days / 365.25)
        d += dt.timedelta(days=1)
    return out


def mfapi(s):
    return json.dumps({"data": [{"date": dt.date.fromisoformat(d).strftime("%d-%m-%Y"),
                                 "nav": f"{v:.5f}"} for d, v in sorted(s.items(), reverse=True)]})


AS_OF = "2026-10-23"
FUND = series("2019-01-01", AS_OF, 0.12)        # active fund, 12%/yr
BENCH = series("2019-01-01", AS_OF, 0.10)       # its index, 10%/yr
TWIN = dict(BENCH)                              # an index fund identical to the index
SERIES = {"900001": FUND, "120716": BENCH, "900002": TWIN}


def stub_fetch(url):
    return mfapi(SERIES[url.rstrip("/").split("/")[-1]])


def make_root(tmp, src_date="2026-10-20", second_src_date="2026-09-10"):
    p = common.paths(tmp)
    os.makedirs(p["skill_data"])
    common.write_json(p["profile"], {
        "fd_rate_pct": 6.5, "fd_rate_as_of": "2026-10-24",
        "tax": {"slab_pct": 30.0, "surcharge_multiplier": 1.15, "cess": 1.04,
                "effective_slab_pct": 35.88, "ltcg_multiplier": 1.196}})
    common.write_json(p["fund_meta"], {
        "INF000X01AA1": {"amfi_code": "900001", "category": "large_cap", "benchmark_key": "large_cap",
                         "expense_ratio_pct": 0.59, "tax_class": "equity", "option": "growth"},
        "INF000X01BB2": {"amfi_code": "900002", "category": "index_nifty50",
                         "benchmark_key": "index_nifty50", "expense_ratio_pct": 0.10,
                         "tax_class": "equity", "option": "growth"}})
    fref = common.folio_ref(FOLIO)
    rows, holdings = [], []
    for isin, src, s, dates in (("INF000X01AA1", "srca", FUND, ["2020-03-02", "2023-06-01"]),
                                ("INF000X01BB2", "srcb", TWIN, ["2025-01-06", "2026-02-02"])):
        units = 0.0
        for i, d in enumerate(dates):
            u = 10000 / s[d]
            units += u
            rows.append({"date": d, "source": src, "owner": "self", "folio_ref": fref, "isin": isin,
                         "amfi_code": "", "scheme": isin, "plan": "direct", "option": "growth",
                         "type": "buy", "amount": 10000.0, "units": round(u, 3), "nav": s[d],
                         "row_id": ledger.make_row_id(src, f"{isin}{d}", i)})
        holdings.append({"source": src, "owner": "self", "folio_ref": fref, "isin": isin,
                         "scheme": "Example " + isin[-3:], "plan": "direct", "option": "growth",
                         "units": round(units, 3), "invested": 20000.0,
                         "current_value": round(units * s[AS_OF], 2), "nav": s[AS_OF]})
    ledger.write_transactions(p["transactions"], rows)
    recon = ledger.reconcile(rows, holdings)
    ledger.write_snapshot(tmp, "2026-10-20", holdings, recon,
                          {"srca": {"holdings_as_of": src_date, "transactions_complete": True},
                           "srcb": {"holdings_as_of": second_src_date,
                                    "transactions_complete": True}})
    return tmp


class TestFreshness(unittest.TestCase):
    def test_stale_source_suggested(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp)
            f = freshness.check(tmp, "2026-10-25")
            self.assertFalse(f["sources"]["srca"]["stale"])
            self.assertTrue(f["sources"]["srcb"]["stale"])
            self.assertEqual(f["suggest_refresh"], ["srcb"])
            self.assertEqual(f["fd_rate_age_days"], 1)
            self.assertEqual(f["missing_meta"], [])

    def test_no_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(freshness.check(tmp, "2026-10-25")["sources"], {})


class TestAnalyse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        make_root(self.tmp.name)
        self.a = analyse.run(self.tmp.name, AS_OF, fetch=stub_fetch)
        self.funds = {f["isin"]: f for f in self.a["funds"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_totals(self):
        self.assertAlmostEqual(self.a["totals"]["invested"], 40000.0)
        self.assertAlmostEqual(self.a["totals"]["value"],
                               sum(f["value"] for f in self.a["funds"]), places=2)
        self.assertIsNotNone(self.a["totals"]["xirr"])
        self.assertEqual(set(self.a["by_source"]), {"srca", "srcb"})

    def test_twin_of_index_has_zero_diff_and_fails_fee_test(self):
        tw = self.funds["INF000X01BB2"]
        self.assertAlmostEqual(tw["same_flows"]["diff_pts"], 0.0, places=1)
        self.assertNotIn("keeps_fee", tw["flags"])

    def test_active_fund_keeps_fee(self):
        f = self.funds["INF000X01AA1"]
        self.assertEqual(f["rolling"]["win_pct"], 100.0)
        self.assertIn("keeps_fee", f["flags"])
        self.assertAlmostEqual(f["xirr"], 0.12, places=2)
        self.assertAlmostEqual(f["er_gap_vs_index"], 0.39, places=2)

    def test_hurdle(self):
        h = self.a["hurdle"]
        self.assertAlmostEqual(h["post_tax_pct"], 4.17, places=2)
        self.assertEqual(h["fd_rate_as_of"], "2026-10-24")

    def test_tax_and_costs(self):
        self.assertGreater(self.a["tax"]["equity_lt_net"], 0)
        self.assertAlmostEqual(self.a["costs"]["annual_cost_inr"],
                               sum(f["value"] * f["er_pct"] / 100 for f in self.a["funds"]), places=1)

    def test_period(self):
        a = analyse.run(self.tmp.name, AS_OF, fetch=stub_fetch, period=("2025-10-23", AS_OF))
        p = a["period"]
        self.assertAlmostEqual(p["end_value"] - p["start_value"] - p["net_flows"], p["pnl"], places=1)
        self.assertEqual(p["net_flows"], 10000.0)

    def test_written_and_no_folio(self):
        path = os.path.join(common.paths(self.tmp.name)["skill_data"], f"analysis-{AS_OF}.json")
        with open(path) as f:
            blob = f.read()
        self.assertNotIn(FOLIO, blob)

    def test_incomplete_history_flagged_not_crashing(self):
        p = common.paths(self.tmp.name)
        rows = [r for r in ledger.read_transactions(p["transactions"]) if r["date"] != "2020-03-02"]
        ledger.write_transactions(p["transactions"], rows)
        a = analyse.run(self.tmp.name, AS_OF, fetch=stub_fetch)
        f = {x["isin"]: x for x in a["funds"]}["INF000X01AA1"]
        self.assertIn("transactions_incomplete", f["flags"])
        self.assertIsNone(f["xirr"])
        self.assertIn("INF000X01AA1", a["tax"]["excluded_isins"])


class TestReport(unittest.TestCase):
    def test_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_root(tmp)
            a = analyse.run(tmp, AS_OF, fetch=stub_fetch)
            md = report.render(a)
            self.assertIn("Example AA1", md)
            self.assertIn("Example BB2", md)
            self.assertIn("Terms used", md)
            self.assertIn("XIRR", md)
            self.assertIn("4.17", md)
            self.assertNotIn(FOLIO, md)


if __name__ == "__main__":
    unittest.main()
