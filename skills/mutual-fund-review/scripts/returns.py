#!/usr/bin/env python3
"""Return arithmetic: XIRR, profit and loss over any period, "the same money in
the index on the same dates", trailing CAGR and rolling-window records.
Pure functions over ledger rows and NAV series ({iso_date: nav}). Returns are
decimals (0.10 = 10%) except rolling(), which reports percentages for display.
"""
import datetime as dt
import statistics

from nav import nav_on  # noqa: F401  (re-exported for callers and tests)

MONEY_IN = {"buy", "sip", "switch_in"}
MONEY_OUT = {"sell", "switch_out", "dividend_payout"}


def _d(s):
    return dt.date.fromisoformat(s)


def flows_from_tx(rows):
    """The investor's cash flows: money put in negative, money taken out positive."""
    out = []
    for r in rows:
        amt = abs(float(r["amount"] or 0))
        if r["type"] in MONEY_IN:
            out.append((r["date"], -amt))
        elif r["type"] in MONEY_OUT:
            out.append((r["date"], amt))
    return sorted(out)


def xirr(flows):
    flows = [(d, a) for d, a in flows if a]
    if not flows or all(a > 0 for _, a in flows) or all(a < 0 for _, a in flows):
        return None
    t0 = min(_d(d) for d, _ in flows)
    pts = [((_d(d) - t0).days / 365.0, a) for d, a in flows]

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in pts)

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return (lo + hi) / 2


def period_pnl(rows, value_at, start, end):
    """Profit over [start, end]: end value - start value - net money added in
    between, and the XIRR of that period treating the start value as invested
    on the start date."""
    start_value, end_value = float(value_at(start)), float(value_at(end))
    inside = [(d, a) for d, a in flows_from_tx(rows) if start < d <= end]
    net = -sum(a for _, a in inside)
    flows = ([(start, -start_value)] if start_value else []) + inside + [(end, end_value)]
    return {"start": start, "end": end, "start_value": round(start_value, 2),
            "end_value": round(end_value, 2), "net_flows": round(net, 2),
            "pnl": round(end_value - start_value - net, 2), "xirr": xirr(flows)}


def same_flows_benchmark(rows, bench_series, end, end_value):
    """What the same purchases and sales on the same dates would be worth in the
    benchmark: a buy of X buys X of benchmark units; a sale or dividend paid out
    of X sells X of them, so both sides return the same cash."""
    units = 0.0
    for r in sorted(rows, key=lambda r: r["date"]):
        if r["type"] not in MONEY_IN | MONEY_OUT:
            continue
        price = nav_on(bench_series, r["date"])
        if price is None:
            return {"bench_value": None, "bench_xirr": None, "actual_xirr": None,
                    "diff_pts": None, "note": f"no benchmark NAV on {r['date']}"}
        amt = abs(float(r["amount"] or 0))
        units += amt / price if r["type"] in MONEY_IN else -amt / price
    end_price = nav_on(bench_series, end)
    if end_price is None:
        return {"bench_value": None, "bench_xirr": None, "actual_xirr": None,
                "diff_pts": None, "note": f"no benchmark NAV on {end}"}
    flows = flows_from_tx(rows)
    bench_value = units * end_price
    actual = xirr(flows + [(end, end_value)])
    bench = xirr(flows + [(end, bench_value)])
    diff = (actual - bench) * 100 if actual is not None and bench is not None else None
    return {"bench_value": round(bench_value, 2), "bench_xirr": bench, "actual_xirr": actual,
            "diff_pts": diff}


def trailing_cagr(series, end, years):
    start = (_d(end) - dt.timedelta(days=round(365.25 * years))).isoformat()
    if not series or min(series) > start:
        return None
    a, b = nav_on(series, start), nav_on(series, end)
    if not a or not b:
        return None
    return (b / a) ** (1 / years) - 1


def rolling(fund, bench, years, end, step_days=30, hurdle_pct=None):
    """Every `years`-long window starting each `step_days` from the first date
    both series cover, ending on or before `end`. Percentages."""
    empty = {"windows": 0, "first_start": None, "fund_median": None, "bench_median": None,
             "win_pct": None, "above_hurdle_pct": None, "bench_above_hurdle_pct": None,
             "worst": None, "median_excess": None}
    if not fund or not bench:
        return empty
    start = _d(max(min(fund), min(bench)))
    span = dt.timedelta(days=round(365.25 * years))
    last = _d(end)
    f_r, b_r, starts = [], [], []
    d = start
    while d + span <= last:
        e = (d + span).isoformat()
        fa, fb = nav_on(fund, d.isoformat()), nav_on(fund, e)
        ba, bb = nav_on(bench, d.isoformat()), nav_on(bench, e)
        if fa and fb and ba and bb:
            f_r.append(((fb / fa) ** (1 / years) - 1) * 100)
            b_r.append(((bb / ba) ** (1 / years) - 1) * 100)
            starts.append(d.isoformat())
        d += dt.timedelta(days=step_days)
    if not f_r:
        return empty
    n = len(f_r)
    out = {"windows": n, "first_start": starts[0],
           "fund_median": round(statistics.median(f_r), 2),
           "bench_median": round(statistics.median(b_r), 2),
           "win_pct": round(100 * sum(f > b for f, b in zip(f_r, b_r)) / n, 1),
           "median_excess": round(statistics.median(f - b for f, b in zip(f_r, b_r)), 2),
           "worst": round(min(f_r), 2), "above_hurdle_pct": None,
           "bench_above_hurdle_pct": None}
    if hurdle_pct is not None:
        out["above_hurdle_pct"] = round(100 * sum(f > hurdle_pct for f in f_r) / n, 1)
        out["bench_above_hurdle_pct"] = round(100 * sum(b > hurdle_pct for b in b_r) / n, 1)
    return out
