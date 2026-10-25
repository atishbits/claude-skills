#!/usr/bin/env python3
"""The cached review: every number the report and Claude's verdicts rest on,
computed from the newest snapshot, the ledger, fund metadata and NAVs (the
only network use, through nav.history and its cache).

    python3 scripts/analyse.py [--root R] [--as-of YYYY-MM-DD] [--from D --to D]

Writes data/skill-data/analysis-<as_of>.json and prints a short summary.
Each fund gets deterministic flags; Claude words verdicts from them:
  below_fd_hurdle_rolling  rolling median return under the pre-tax FD equivalent
  keeps_fee / fails_fee_test  active fund: beat an index fund on its benchmark in
                           >= keep_min_window_win_pct of rolling windows AND by a positive
                           median margin (both NAVs are after fees, so the fee is already paid)
  index_fund               an index fund (judged on cost and tracking, not the fee test)
  short_history            fewer than 12 rolling windows
  transactions_incomplete  history does not add up to units held: no XIRR or tax lots
  idcw_growth_proxy        IDCW plan compared with a growth-plan index proxy
  er_missing               no expense ratio recorded
  exit_load_period_unknown a load applies but its period is not recorded: switch cost unknown
"""
import argparse
import datetime as dt
import json
import os
import sys

import common
import costs
import fund_meta
import ledger
import nav
import returns
import tax

MIN_WINDOWS = 12


def xirr_meaningful(first_date, as_of):
    """An annualised return on money held under a year exaggerates: a 2% move
    in ten days reads as 100%+. Show the absolute return instead."""
    return (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(first_date)).days >= 365


def _units_at(rows, date):
    u = 0.0
    for r in rows:
        if r["date"] > date:
            continue
        if r["type"] in ledger.UNITS_IN:
            u += float(r["units"] or 0)
        elif r["type"] in ledger.UNITS_OUT:
            u -= abs(float(r["units"] or 0))
    return u


def _rows_for(h, txs):
    return [r for r in txs if r["source"] == h["source"] and r["isin"] == h["isin"]
            and (not h.get("folio_ref") or r["folio_ref"] == h["folio_ref"])]


def run(root, as_of, fetch=nav.default_fetch, period=None):
    p = common.paths(root)
    prof = common.load_profile(root)
    rules = common.load_tax_rules()
    person = prof.get("tax")
    snap_path = ledger.latest_snapshot(root)
    if not snap_path:
        raise ValueError("no snapshot yet: ingest a capture, CAS or CSV first")
    with open(snap_path) as f:
        snap = json.load(f)
    txs = ledger.read_transactions(p["transactions"])
    meta = fund_meta.load(root)
    series_cache = {}

    def series(code):
        if not code:
            return {}
        if code not in series_cache:
            try:
                series_cache[code] = nav.history(str(code), root, fetch=fetch)
            except (OSError, ValueError):
                series_cache[code] = {}
        return series_cache[code]

    hurdle = None
    if person:
        post = tax.fd_hurdle(prof["fd_rate_pct"], person["effective_slab_pct"])
        yrs = prof["rolling_years"]
        hurdle = {"fd_rate_pct": prof["fd_rate_pct"], "fd_rate_as_of": prof.get("fd_rate_as_of"),
                  "post_tax_pct": round(post, 2), "years": yrs,
                  "required_pretax_pct": {c: round(tax.required_pretax(post, yrs, c, rules, person), 2)
                                          for c in ("equity", "hybrid_gold_intl", "specified_debt")}}
        hurdle["equity_with_premium_pct"] = round(hurdle["required_pretax_pct"]["equity"]
                                                  + prof["equity_risk_premium_pts"], 2)

    funds, complete_rows, all_flows, by_source = [], [], [], {}
    keys = {}
    for h in snap["holdings"]:
        m = meta.get(h["isin"], {})
        rows = _rows_for(h, txs)
        s = series(m.get("amfi_code"))
        price = nav.nav_on(s, as_of) if s else None
        if price is None:
            price = h.get("nav") or ((h.get("current_value") or 0) / h["units"] if h["units"] else 0)
        value = round(h["units"] * price, 2)
        src_ok = h.get("transactions_complete",
                       snap.get("sources", {}).get(h["source"], {}).get("transactions_complete", False))
        units_ok = abs(_units_at(rows, as_of) - h["units"]) <= ledger.UNIT_TOLERANCE
        complete = bool(src_ok and units_ok and rows)
        flags = []
        cls = m.get("tax_class", "equity")
        bench = fund_meta.benchmark_for(m) if m else None
        bseries = series(bench["proxy_amfi_code"]) if bench and bench.get("proxy_amfi_code") else {}
        is_index = (m.get("category") or "").startswith("index_")
        record = series(m.get("growth_amfi_code")) if m.get("growth_amfi_code") else s
        f = {"isin": h["isin"], "scheme": h.get("scheme", ""), "source": h["source"],
             "category": m.get("category"), "tax_class": cls, "units": h["units"],
             "nav": price, "value": value, "invested": h.get("invested"),
             "benchmark": bench.get("index") if bench else None,
             "benchmark_note": bench.get("note") if bench else None,
             "er_pct": m.get("expense_ratio_pct"), "er_as_of": m.get("er_as_of"),
             "xirr": None, "same_flows": None, "trailing": {}, "bench_trailing": {},
             "rolling": None, "er_gap_vs_index": None, "flags": flags,
             "xirr_meaningful": None, "abs_return": None, "first_buy": None,
             "switch": {"exit_load_inr": None, "tax_if_sold_inr": None,
                        "breakeven_years_to_index": None}}
        keys[id(f)] = (h["source"], h.get("folio_ref") or None, h["isin"], is_index, m)
        if complete:
            flows = returns.flows_from_tx(rows)
            f["xirr"] = returns.xirr(flows + [(as_of, value)])
            put_in = -sum(a for _, a in flows if a < 0)
            taken_out = sum(a for _, a in flows if a > 0)
            f["first_buy"] = flows[0][0] if flows else None
            f["xirr_meaningful"] = xirr_meaningful(flows[0][0], as_of) if flows else None
            f["abs_return"] = (value + taken_out) / put_in - 1 if put_in else None
            all_flows += flows
            complete_rows += rows
            if bseries:
                f["same_flows"] = returns.same_flows_benchmark(rows, bseries, as_of, value)
        else:
            flags.append("transactions_incomplete")
        for y in (1, 3, 5):
            f["trailing"][f"{y}y"] = returns.trailing_cagr(record, as_of, y) if record else None
            f["bench_trailing"][f"{y}y"] = returns.trailing_cagr(bseries, as_of, y) if bseries else None
        hurdle_pre = hurdle["required_pretax_pct"].get(cls) if hurdle else None
        if m.get("option") == "idcw" and not m.get("growth_amfi_code"):
            record = {}  # the IDCW NAV drops at each payout: no fair record without the growth plan
            f["trailing"] = {k: None for k in f["trailing"]}
        if record and bseries:
            f["rolling"] = returns.rolling(record, bseries, prof["rolling_years"], as_of,
                                           hurdle_pct=hurdle_pre)
        roll = f["rolling"] or {}
        if f["er_pct"] is None:
            flags.append("er_missing")
        else:
            f["er_gap_vs_index"] = costs.vs_index(f["er_pct"], prof.get("index_fund_er_pct", 0.2))
        if m.get("option") == "idcw" or h.get("option") == "idcw":
            flags.append("idcw_growth_proxy" if m.get("growth_amfi_code") else "idcw_no_growth_series")
        if not bseries:
            flags.append("no_benchmark")
        elif roll.get("windows", 0) < MIN_WINDOWS:
            flags.append("short_history")
        if f["xirr_meaningful"] is False:
            flags.append("held_under_1y")
        if roll.get("fund_median") is not None and hurdle_pre is not None \
                and roll["fund_median"] < hurdle_pre:
            flags.append("below_fd_hurdle_rolling")
        if is_index:
            flags.append("index_fund")
        elif roll.get("windows", 0) >= MIN_WINDOWS and f["er_gap_vs_index"] is not None:
            # Both NAVs are already net of their own fees, so a positive median
            # excess means the fund earned its higher fee.
            keeps = (roll["win_pct"] >= prof["keep_min_window_win_pct"]
                     and roll["median_excess"] > 0)
            flags.append("keeps_fee" if keeps else "fails_fee_test")
        funds.append(f)
        b = by_source.setdefault(h["source"], {"value": 0.0, "invested": 0.0, "flows": [],
                                               "complete": True})
        b["value"] += value
        b["invested"] += float(h.get("invested") or 0)
        if complete:
            b["flows"] += returns.flows_from_tx(rows)
        else:
            b["complete"] = False

    def summarise(value, invested, flows, complete):
        return {"value": round(value, 2), "invested": round(invested, 2),
                "pnl": round(value - invested, 2),
                "xirr": returns.xirr(flows + [(as_of, value)]) if flows and complete else None}

    total_value = sum(f["value"] for f in funds)
    total_inv = sum(float(f["invested"] or 0) for f in funds)
    complete_value = sum(f["value"] for f in funds if "transactions_incomplete" not in f["flags"])
    totals = summarise(total_value, total_inv, all_flows, True)
    totals["xirr"] = returns.xirr(sorted(all_flows) + [(as_of, complete_value)]) if all_flows else None
    totals["xirr_covers_value_pct"] = round(100 * complete_value / total_value, 1) if total_value else None
    sources = {k: summarise(v["value"], v["invested"], v["flows"], v["complete"])
               for k, v in by_source.items()}

    tax_out = None
    if person:
        incomplete = sorted({f["isin"] for f in funds if "transactions_incomplete" in f["flags"]})
        lot_map = {}
        for f in funds:
            if "transactions_incomplete" in f["flags"]:
                continue
            src, folio, isin, _ix, _m = keys[id(f)]
            try:
                lot_map.update(tax.lots(_rows_for({"source": src, "folio_ref": folio, "isin": isin}, txs)))
            except ValueError:
                f["flags"].append("lots_error")
                incomplete.append(isin)
        navs = {f["isin"]: f["nav"] for f in funds}
        classes = {f["isin"]: f["tax_class"] for f in funds}
        u = tax.unrealised(lot_map, navs, as_of, rules, classes, person)
        tax_out = u["totals"]
        tax_out["excluded_isins"] = sorted(set(incomplete))
        by_h = u["by_holding"]
        for f in funds:
            src, folio, isin, is_index, m = keys[id(f)]
            hk = (src, folio, isin)
            if hk not in by_h:
                continue
            sw = f["switch"]
            sw["tax_if_sold_inr"] = tax.holding_tax(by_h[hk], rules, person)
            sw["exit_load_inr"] = costs.exit_load_inr(lot_map.get(hk, []), as_of,
                                                      m.get("exit_load_pct"),
                                                      m.get("exit_load_days"), f["nav"])
            if sw["exit_load_inr"] is None:
                f["flags"].append("exit_load_period_unknown")
            if not is_index and f["er_pct"] is not None:
                sw["breakeven_years_to_index"] = costs.switch_breakeven(
                    f["value"], sw["exit_load_inr"], sw["tax_if_sold_inr"],
                    prof["expected_return_pct"], f["er_pct"], prof.get("index_fund_er_pct", 0.2))

    cost = costs.weighted_er([{"isin": f["isin"], "value": f["value"]} for f in funds], meta)

    period_out = None
    if period:
        start, end = period
        included, excluded, prow = [], [], []
        for f in funds:
            if "transactions_incomplete" in f["flags"]:
                excluded.append(f["isin"])
                continue
            src, folio, isin, _ix, m = keys[id(f)]
            rows = _rows_for({"source": src, "folio_ref": folio, "isin": isin}, txs)
            s_ = series(m.get("amfi_code"))
            needs_start = _units_at(rows, start) > ledger.UNIT_TOLERANCE
            if not s_ or nav.nav_on(s_, end) is None or (needs_start and nav.nav_on(s_, start) is None):
                excluded.append(isin)  # never value a fund at zero for want of a price
                continue
            included.append((rows, s_))
            prow += rows

        def value_at(d):
            return sum(_units_at(rows, d) * (nav.nav_on(s_, d) or 0) for rows, s_ in included
                       if _units_at(rows, d) > ledger.UNIT_TOLERANCE)
        period_out = returns.period_pnl(prow, value_at, start, end)
        period_out["excluded"] = sorted(set(excluded))

    out = {"as_of": as_of, "snapshot": os.path.basename(snap_path), "totals": totals,
           "by_source": sources, "funds": sorted(funds, key=lambda f: -f["value"]),
           "costs": cost, "tax": tax_out, "hurdle": hurdle, "period": period_out,
           "notes": [] if person else ["no tax rates: run `tax.py import --write`"]}
    common.write_json(os.path.join(p["skill_data"], f"analysis-{as_of}.json"), out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--root")
    ap.add_argument("--as-of")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    as_of = a.as_of or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    period = (a.start, a.end or as_of) if a.start else None
    out = run(root, as_of, period=period)
    print(json.dumps({"as_of": out["as_of"], "totals": out["totals"], "by_source": out["by_source"],
                      "hurdle": out["hurdle"], "costs": {k: out["costs"][k] for k in
                                                         ("weighted_er_pct", "annual_cost_inr")},
                      "flags": {f["scheme"]: f["flags"] for f in out["funds"]},
                      "period": out["period"]}, indent=1))


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
