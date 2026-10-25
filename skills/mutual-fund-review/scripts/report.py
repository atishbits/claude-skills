#!/usr/bin/env python3
"""Turn an analysis JSON into data/skill-data/PORTFOLIO.md: a compact, dated
scorecard with a glossary of every term used. Formatting only; no arithmetic
beyond rounding.

    python3 scripts/report.py [--root R] [--analysis FILE]
"""
import argparse
import glob
import json
import os

import common

GLOSSARY = {
    "XIRR": "Extended Internal Rate of Return: your yearly return, worked out from the date and amount of every purchase and sale.",
    "Same money in index": "what the same purchases on the same dates would be worth in the fund's benchmark index; separates your fund choice from your timing.",
    "Rolling win %": "share of every 3-year window (one starting each month) in which the fund beat its index.",
    "Expense ratio (ER)": "the yearly fee the fund takes out of your money, already reflected in its NAV.",
    "NAV": "Net Asset Value: the price of one unit of the fund.",
    "FD hurdle": "what a bank fixed deposit earns after your income tax; every fund should beat it after its own tax.",
    "LTCG / STCG": "long-term / short-term capital gains: profit on units held longer / shorter than the holding period (12 months for equity funds), taxed at different rates.",
    "IDCW": "Income Distribution cum Capital Withdrawal: the plan that pays out dividends instead of growing the NAV.",
    "CAS": "Consolidated Account Statement: one statement of every fund you hold across fund houses, linked to your PAN.",
}

FLAG_TEXT = {
    "keeps_fee": "earns its fee", "fails_fee_test": "fee not earned", "index_fund": "index fund",
    "below_fd_hurdle_rolling": "below FD hurdle", "short_history": "short history",
    "transactions_incomplete": "history incomplete", "idcw_growth_proxy": "IDCW plan",
    "er_missing": "ER missing", "sold": "sold", "exit_load_period_unknown": "exit-load period unknown",
    "held_under_1y": "held under a year", "no_benchmark": "no benchmark",
    "idcw_no_growth_series": "IDCW plan, no growth series", "lots_error": "tax lots don't add up",
}


def _inr(x):
    if x is None:
        return "–"
    neg, x = x < 0, abs(round(x))
    s = str(int(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-₹" if neg else "₹") + s


def _pct(x, scale=100, nd=1):
    return "–" if x is None else f"{x * scale:.{nd}f}%"


def _fund_return(f):
    if f.get("xirr_meaningful") is False and f.get("abs_return") is not None:
        return f"{f['abs_return'] * 100:.1f}% (under 1 yr)"
    return _pct(f["xirr"])


def render(a):
    t, h = a["totals"], a.get("hurdle")
    lines = [f"# Mutual funds — {a['as_of']}", ""]
    lines.append(f"**{_inr(t['value'])}** now, {_inr(t['invested'])} invested, "
                 f"{_inr(t['pnl'])} gain. XIRR {_pct(t['xirr'])}"
                 + (f" (covers {t['xirr_covers_value_pct']}% of value)"
                    if t.get("xirr_covers_value_pct") not in (None, 100.0) else "") + ".")
    if h:
        lines.append(f"FD hurdle: {h['fd_rate_pct']}% FD (as of {h['fd_rate_as_of']}) = "
                     f"**{h['post_tax_pct']:.2f}%** after tax; an equity fund needs "
                     f"{h['required_pretax_pct']['equity']:.2f}% before tax to match it "
                     f"({h['equity_with_premium_pct']:.2f}% with the risk premium).")
    lines += ["", "| Source | Value | Invested | Gain | XIRR |", "|---|---|---|---|---|"]
    for name, s in sorted(a["by_source"].items()):
        lines.append(f"| {name} | {_inr(s['value'])} | {_inr(s['invested'])} | {_inr(s['pnl'])} "
                     f"| {_pct(s['xirr'])} |")
    lines += ["", "| Fund | Value | XIRR (or gain if under 1 yr) | vs same money in index | 3y fund / index | "
              "Rolling win % | ER | Flags |", "|---|---|---|---|---|---|---|---|"]
    for f in a["funds"]:
        sf = f.get("same_flows") or {}
        diff = sf.get("diff_pts")
        roll = f.get("rolling") or {}
        lines.append(
            f"| {f['scheme']} | {_inr(f['value'])} | {_fund_return(f)} | "
            f"{'–' if diff is None else f'{diff:+.1f} pts'} | "
            f"{_pct(f['trailing'].get('3y'))} / {_pct(f['bench_trailing'].get('3y'))} | "
            f"{'–' if roll.get('win_pct') is None else str(roll['win_pct']) + '%'} | "
            f"{'–' if f['er_pct'] is None else str(f['er_pct']) + '%'} | "
            f"{', '.join(FLAG_TEXT.get(x, x) for x in f['flags'])} |")
    c = a["costs"]
    er = "–" if c["weighted_er_pct"] is None else f"{c['weighted_er_pct']:.3f}%"
    lines += ["", f"**Costs:** weighted ER {er} ≈ {_inr(c['annual_cost_inr'])} a year."
              + (f" ER missing for {len(c['missing_er'])} fund(s)." if c["missing_er"] else "")
              + (" ERs mix pre- and post-April-2026 bases." if c["mixed_basis"] else "")]
    tx = a.get("tax")
    if tx:
        lines.append(f"**Tax if everything were sold today:** {_inr(tx['tax_if_all_sold'])} "
                     f"(equity long-term gain {_inr(tx['equity_lt_net'])}, short-term "
                     f"{_inr(tx['equity_st_net'])}; assumes the ₹1.25L exemption is unused this year)."
                     + (f" Excludes {len(tx['excluded_isins'])} fund(s) with incomplete history."
                        if tx["excluded_isins"] else ""))
    if a.get("period"):
        p = a["period"]
        lines.append(f"**{p['start']} → {p['end']}:** gain {_inr(p['pnl'])} on "
                     f"{_inr(p['start_value'])} start value and {_inr(p['net_flows'])} added; "
                     f"XIRR {_pct(p['xirr'])}.")
    for n in a.get("notes", []):
        lines.append(f"_Note: {n}_")
    lines += ["", "Advisory only: nothing here buys or sells anything.", "", "**Terms used**", ""]
    lines += [f"- **{k}** — {v}" for k, v in GLOSSARY.items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--root")
    ap.add_argument("--analysis")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    sd = common.paths(root)["skill_data"]
    path = a.analysis or max(glob.glob(os.path.join(sd, "analysis-*.json")))
    with open(path) as f:
        md = render(json.load(f))
    with open(os.path.join(sd, "PORTFOLIO.md"), "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
