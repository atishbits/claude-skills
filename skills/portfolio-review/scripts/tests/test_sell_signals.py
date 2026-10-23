import unittest
from datetime import date

import sell_signals

Q = {"period_end": ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"],
     "net_profit": [10, 10, 10, 10, 10]}

SPLIT = {"rise_pct": 30.0, "eps_pct": 0.0, "pe_pct": 30.0, "pe_share": 1.0}
HOT = {"pe_high": True, "earnings_above_trend": False, "above_consensus": None, "count": 1}
COLD = {"pe_high": False, "earnings_above_trend": False, "above_consensus": None, "count": 0}


class TtmTests(unittest.TestCase):
    def test_ttm_respects_result_lag(self):
        self.assertEqual(sell_signals.ttm_profit_asof(Q, date(2026, 8, 20)), 40)
        self.assertIsNone(sell_signals.ttm_profit_asof(Q, date(2026, 8, 1)))

    def test_ttm_none_for_loss_or_missing(self):
        loss = {"period_end": Q["period_end"], "net_profit": [-50, 10, 10, 10, 10]}
        self.assertIsNone(sell_signals.ttm_profit_asof(loss, date(2026, 8, 20)))
        self.assertIsNone(sell_signals.ttm_profit_asof(None, date(2026, 8, 20)))
        gap = {"period_end": Q["period_end"], "net_profit": [10, None, 10, 10, 10]}
        self.assertIsNone(sell_signals.ttm_profit_asof(gap, date(2026, 8, 20)))


class RiseSplitTests(unittest.TestCase):
    def test_rise_all_from_pe_when_profit_flat(self):
        s = sell_signals.rise_split(33.0, 40.0, 40.0)
        self.assertAlmostEqual(s["pe_share"], 1.0)
        self.assertAlmostEqual(s["eps_pct"], 0.0)
        self.assertAlmostEqual(s["pe_pct"], 33.0)

    def test_rise_all_from_eps(self):
        self.assertAlmostEqual(sell_signals.rise_split(20.0, 48.0, 40.0)["pe_share"], 0.0)

    def test_share_clamped_when_pe_falls(self):
        s = sell_signals.rise_split(10.0, 60.0, 40.0)
        self.assertEqual(s["pe_share"], 0.0)

    def test_no_split_for_fall_or_loss(self):
        self.assertIsNone(sell_signals.rise_split(-5.0, 40.0, 40.0))
        self.assertIsNone(sell_signals.rise_split(20.0, None, 40.0))
        self.assertIsNone(sell_signals.rise_split(20.0, 40.0, None))
        self.assertIsNone(sell_signals.rise_split(None, 40.0, 40.0))


class PeakTests(unittest.TestCase):
    def test_counts_only_true(self):
        st = {"price": 120, "own_pe_band": {"percentile": 90},
              "growth_ranges": {"earnings_above_trend": True}}
        t = sell_signals.peak_tests(st, 100.0)
        self.assertEqual(t, {"pe_high": True, "earnings_above_trend": True,
                             "above_consensus": True, "count": 3})

    def test_unknowns_never_raise(self):
        t = sell_signals.peak_tests({"growth_ranges": None, "own_pe_band": None}, None)
        self.assertIsNone(t["pe_high"])
        self.assertIsNone(t["above_consensus"])
        self.assertFalse(t["earnings_above_trend"])
        self.assertEqual(t["count"], 0)
        self.assertEqual(sell_signals.peak_tests({}, 50.0)["above_consensus"], None)

    def test_percentile_none_and_low(self):
        self.assertIsNone(sell_signals.peak_tests({"own_pe_band": {"percentile": None}}, None)["pe_high"])
        self.assertFalse(sell_signals.peak_tests({"own_pe_band": {"percentile": 50}}, None)["pe_high"])


class KindTests(unittest.TestCase):
    def test_business_kind(self):
        self.assertEqual(sell_signals.business_kind({"signal_row": 3}), "weak")
        self.assertEqual(sell_signals.business_kind({"signal_row": 4}), "weak")
        self.assertEqual(sell_signals.business_kind(
            {"signal_row": 1, "ratio_history": {"roce_fading": True}}), "weak")
        machine = {"signal_row": 1, "roce": 30.0,
                   "growth_ranges": {"profit_growth": {"5_years": 18.0}},
                   "ratio_history": {"roce_fading": False}}
        self.assertEqual(sell_signals.business_kind(machine), "machine")
        self.assertEqual(sell_signals.business_kind({"signal_row": 2, "roce": 20.0}), "ordinary")
        self.assertEqual(sell_signals.business_kind(
            {"roce": 30.0, "growth_ranges": None}), "ordinary")


class TierTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(sell_signals.case_tier(SPLIT, HOT, "weak"), "trim_half")
        self.assertEqual(sell_signals.case_tier(SPLIT, HOT, "machine"), "trim_third")
        self.assertEqual(sell_signals.case_tier(SPLIT, COLD, "ordinary"), "watch")
        self.assertEqual(sell_signals.case_tier(None, COLD, "ordinary"), "none")

    def test_two_tests_are_strong_without_stretch(self):
        two = {"pe_high": True, "earnings_above_trend": True, "above_consensus": None, "count": 2}
        self.assertEqual(sell_signals.case_tier(None, two, "ordinary"), "trim_third")

    def test_one_test_alone_is_watch(self):
        self.assertEqual(sell_signals.case_tier(None, HOT, "ordinary"), "watch")

    def test_small_or_eps_driven_rise_not_stretched(self):
        eps = dict(SPLIT, pe_share=0.3)
        small = dict(SPLIT, rise_pct=10.0)
        self.assertEqual(sell_signals.case_tier(eps, COLD, "ordinary"), "none")
        self.assertEqual(sell_signals.case_tier(small, COLD, "ordinary"), "none")


def _stock(**kw):
    base = {"price": 133.0, "pe": 40.0, "roce": 12.0, "signal_row": 3, "quarters": Q,
            "technicals": {"return_3m_pct": 33.0, "return_6m_pct": 5.0},
            "growth_ranges": None, "ratio_history": None,
            "own_pe_band": {"years": 10, "percentile": 88}}
    base.update(kw)
    return base


class EvaluateTests(unittest.TestCase):
    TODAY = date(2026, 12, 1)

    def test_evaluate_weak_stretch(self):
        # ttm now = 4 quarters (Sep-26 known by 14 Nov) = 40; 91 days ago also 40 (flat)
        ev = sell_signals.evaluate(_stock(), self.TODAY)
        self.assertEqual(ev["kind"], "weak")
        self.assertEqual(ev["tier"], "trim_half")
        self.assertEqual(ev["pe_percentile"], 88)
        self.assertAlmostEqual(ev["split_3m"]["pe_share"], 1.0)
        self.assertIsNone(ev["split_6m"])
        self.assertTrue(ev["tests"]["pe_high"])

    def test_evaluate_missing_everything_does_not_raise(self):
        ev = sell_signals.evaluate({}, self.TODAY)
        self.assertEqual(ev["tier"], "none")
        self.assertIsNone(ev["pe_percentile"])
        self.assertIsNone(sell_signals.flag_text("STOCKA", ev))

    def test_evaluate_uses_better_window(self):
        st = _stock(technicals={"return_3m_pct": 20.0, "return_6m_pct": 40.0})
        ev = sell_signals.evaluate(st, self.TODAY)
        self.assertEqual(ev["window"], "3m")  # both flat profit, both share 1.0: tie keeps 3m
        q8 = {"period_end": ["2025-03-31"] + Q["period_end"], "net_profit": [10] + Q["net_profit"]}
        st2 = _stock(quarters=q8, technicals={"return_3m_pct": 3.0, "return_6m_pct": 40.0})
        self.assertEqual(sell_signals.evaluate(st2, self.TODAY)["window"], "6m")


class FlagTextTests(unittest.TestCase):
    def test_flag_text_quiet_when_none(self):
        self.assertIsNone(sell_signals.flag_text("STOCKA", {"tier": "none"}))

    def test_flag_text_format(self):
        ev = sell_signals.evaluate(_stock(), date(2026, 12, 1))
        self.assertEqual(
            sell_signals.flag_text("STOCKA", ev),
            "STOCKA: +33% in 3m, ~100% from P/E stretch (profit flat); "
            "P/E at 88th pct of own 10y band; weak business - trim_half candidate")

    def test_flag_text_without_stretch(self):
        ev = {"tier": "watch", "kind": "ordinary", "split_3m": None, "split_6m": None,
              "window": None, "tests": {"pe_high": None, "earnings_above_trend": True,
                                        "above_consensus": None, "count": 1},
              "pe_percentile": None}
        txt = sell_signals.flag_text("STOCKB", ev)
        self.assertIn("STOCKB:", txt)
        self.assertIn("profit above trend", txt)
        self.assertTrue(txt.endswith("ordinary business - watch"))


class TrimPlanTests(unittest.TestCase):
    def test_weak_half_on_90(self):
        self.assertEqual(sell_signals.trim_plan(90, "trim_half", "weak"),
                         {"step1_qty": 45, "step2_qty": 45, "core_qty": 0})

    def test_machine_third_on_90(self):
        self.assertEqual(sell_signals.trim_plan(90, "trim_third", "machine"),
                         {"step1_qty": 30, "step2_qty": 15, "core_qty": 45})

    def test_full_exit_ignores_kind(self):
        for kind in ("weak", "machine", "ordinary"):
            self.assertEqual(sell_signals.trim_plan(90, "trim_third", kind, full_exit=True),
                             {"step1_qty": 45, "step2_qty": 45, "core_qty": 0})

    def test_watch_and_none_sell_nothing(self):
        for tier in ("watch", "none"):
            p = sell_signals.trim_plan(90, tier, "ordinary")
            self.assertEqual(p["step1_qty"], 0)
            self.assertEqual(sum(p.values()), 90)

    def test_quantities_always_sum_to_qty(self):
        for qty in (1, 7, 10, 91):
            for tier in sell_signals.TIERS:
                for kind in sell_signals.CORE_FRACTION:
                    p = sell_signals.trim_plan(qty, tier, kind)
                    self.assertEqual(sum(p.values()), qty)


class Step2Tests(unittest.TestCase):
    def test_off_peak_from_recent_high(self):
        t = sell_signals.step2_triggers(100.0, {"recent_high_60d": 120.0, "dma50": 95.0})
        self.assertAlmostEqual(t["off_peak_price"], 105.6)
        self.assertEqual(t["peak"], 120.0)
        self.assertEqual(t["dma50"], 95.0)

    def test_price_above_high_is_the_peak(self):
        t = sell_signals.step2_triggers(130.0, {"recent_high_60d": 120.0})
        self.assertEqual(t["peak"], 130.0)
        self.assertIsNone(t["dma50"])


class PlanStoreTests(unittest.TestCase):
    def test_round_trip_and_close(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nested", "sell-plans.json")
            self.assertEqual(sell_signals.load_plans(path), {})
            plan = {"opened": "2026-10-23", "step1_qty": 30}
            sell_signals.save_plan("stocka", plan, path)
            self.assertEqual(sell_signals.load_plans(path), {"STOCKA": plan})
            sell_signals.close_plan("STOCKA", path)
            self.assertEqual(sell_signals.load_plans(path), {})


class ConsensusTests(unittest.TestCase):
    def _note(self, d, as_of):
        import os
        with open(os.path.join(d, "STOCKA.md"), "w", encoding="utf-8") as fh:
            fh.write("# STOCKA\n\n**Research:**\n"
                     f"- consensus: avg TP ₹1,234, 3 of 5 post-result — http://x as of {as_of}\n\n")

    def test_fresh_and_stale(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._note(d, "2026-10-10")
            self.assertEqual(sell_signals.consensus_avg("stocka", d, date(2026, 10, 23)), 1234.0)
            self._note(d, "2026-08-01")
            self.assertIsNone(sell_signals.consensus_avg("STOCKA", d, date(2026, 10, 23)))
            self.assertIsNone(sell_signals.consensus_avg("NOPE", d, date(2026, 10, 23)))


class AdviceTests(unittest.TestCase):
    ST_NEAR = [{"date": "2025-10-01", "qty": 10, "cost": 100.0, "cost_is_estimate": False, "taxable": True}]

    def test_wait_for_lot_only_on_watch(self):
        a = sell_signals.advice("watch", [40], 5.0, 20.0)
        self.assertIn("wait for that lot", a)
        self.assertIn("trim now", sell_signals.advice("trim_third", [40], 5.0, 20.0))

    def test_trim_now_when_breakeven_small(self):
        self.assertIn("trim now", sell_signals.advice("trim_third", [], 5.0, -20.0))

    def test_close_call(self):
        self.assertIn("close call", sell_signals.advice("trim_third", [], 15.0, -20.0))

    def test_no_wait_case(self):
        self.assertIn("no short-term", sell_signals.advice("trim_third", [], None, -20.0))


class HeadroomTests(unittest.TestCase):
    def test_no_gains_log_assumes_full_exemption(self):
        import tax_lots
        from unittest import mock
        with mock.patch.object(sell_signals, "_gains_log", return_value=None):
            h, note = sell_signals.lt_headroom(date(2026, 10, 23))
        self.assertEqual(h, tax_lots.LTCG_EXEMPTION_PER_FY)
        self.assertIn("no gains log yet", note)


class CliTests(unittest.TestCase):
    TODAY = date(2026, 10, 23)

    def setUp(self):
        import io
        import json
        import os
        import tempfile
        from contextlib import redirect_stdout
        from unittest import mock
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        sd = os.path.join(self._tmp.name, "skill-data")
        os.makedirs(sd)
        self.stock = {
            "ticker": "STOCKA", "qty": 90, "avg_cost": 100, "price": 150,
            "brokers": {"a": 60, "b": 30},
            "lots": [{"broker": "a", "date": "2026-01-15", "qty": 60, "cost": 100},
                     {"broker": "b", "date": "2025-09-01", "qty": 20, "cost": 90},
                     {"broker": "b", "date": "2015-01-01", "qty": 10, "cost": 20}],
            "technicals": {"max_drawdown_1y_pct": -25, "recent_high_60d": 160}}
        with open(os.path.join(sd, "snapshot-2026-10-23.json"), "w") as fh:
            json.dump({"stocks": [self.stock]}, fh)
        self.plans = os.path.join(sd, "sell-plans.json")
        for target, name, val in ((sell_signals.tax_lots, "SKILL_DATA_DIR", sd),
                                  (sell_signals, "PLANS_PATH", self.plans),
                                  (sell_signals, "NEAR_LT_DAYS", 60)):
            p = mock.patch.object(target, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(sell_signals, "consensus_avg", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        self.io, self.redirect = io, redirect_stdout

    def run_cli(self, *argv):
        buf = self.io.StringIO()
        with self.redirect(buf):
            sell_signals.main(list(argv), today=self.TODAY)
        return buf.getvalue()

    def open_plan(self, tier="trim_third"):
        import json
        plan = {"opened": "2026-10-23", "deciding_sentence": "s", "qty_at_open": 90, "tier": tier,
                "kind": "ordinary", "step1_qty": 30, "step2_qty": 30, "core_qty": 30,
                "triggers": {}, "core_ends_on": None}
        with open(self.plans, "w") as fh:
            json.dump({"STOCKA": plan}, fh)

    def test_each_account_previews_own_lots_and_totals(self):
        self.open_plan()
        out = self.run_cli("STOCKA")
        a, b = out.split("-- if sold from b")
        self.assertIn("if sold from a (holds 60): 30 share(s)", a)
        self.assertIn("2026-01-15: 30 sh", a)
        self.assertNotIn("2025-09-01", a)
        self.assertIn("total: gain ₹1,500", a)
        self.assertIn("(holds 30): 30 share(s)", b)
        self.assertIn("2015-01-01", b)
        self.assertIn("tax not estimated", b)
        self.assertIn("10 shares tax not estimated (pre-2018/undated), excluded", b)

    def test_watch_preview_shows_lots_and_wait_advice(self):
        self.stock["lots"][1]["date"] = "2025-11-20"   # turns long-term in ~28 days
        import json
        import os
        with open(os.path.join(os.path.dirname(self.plans), "snapshot-2026-10-23.json"), "w") as fh:
            json.dump({"stocks": [self.stock]}, fh)
        with mock_tier("watch"):
            out = self.run_cli("STOCKA")
        self.assertIn("preview: if you trimmed a third", out)
        self.assertIn("2025-11-20", out)
        self.assertIn("wait for that lot", out)

    def test_sale_on_opening_day_counts(self):
        from unittest import mock
        self.open_plan()
        gl = mock.Mock()
        gl.fold.return_value = [{"ticker": "STOCKA", "sell_date": "2026-10-23", "qty": 30}]
        gl.read_entries.return_value = []
        gl.fy_running.return_value = {"fy_tax": {"exempt_left": 125000}}
        with mock.patch.object(sell_signals, "_gains_log", return_value=gl):
            out = self.run_cli("STOCKA")
        self.assertIn("30 sold since 2026-10-23", out)

    def test_open_plan_refused_for_watch_and_when_open(self):
        with mock_tier("watch"):
            with self.assertRaises(SystemExit) as cm:
                self.run_cli("STOCKA", "--open-plan", "why")
        self.assertIn("step 1 would be 0", str(cm.exception))
        self.assertEqual(sell_signals.load_plans(self.plans), {})
        self.open_plan()
        with mock_tier("trim_third"):
            with self.assertRaises(SystemExit) as cm:
                self.run_cli("STOCKA", "--open-plan", "again")
        self.assertIn("--close-plan", str(cm.exception))


def mock_tier(tier):
    from unittest import mock
    real = sell_signals.evaluate

    def fake(stock, today, consensus=None):
        ev = real(stock, today, consensus)
        ev["tier"] = tier
        return ev
    return mock.patch.object(sell_signals, "evaluate", fake)


if __name__ == "__main__":
    unittest.main()
