#!/usr/bin/env python3
"""Write the check-up report from the latest analysis.

    python3 scripts/report.py [--summary] [--root R]

Writes data/skill-data/REPORT-<as-of>.md and prints it, or with --summary
prints a short version (at most 15 lines) for the chat.
"""
import argparse
import glob
import os
import re

import common

ADVISER = "This is analysis, not advice from a licensed financial adviser."
KIND_TEXT = {"duplicate": "Same amount to the same payee twice on one day",
             "tiny_debit": "Very small debit (sometimes a card-testing charge)",
             "new_payee_large": "Large payment to a payee seen for the first time",
             "outlier": "Much larger than usual for this payee",
             "foreign": "Foreign-currency or international transaction"}
NICE = {"card_spend_unexpanded": "card spend (not broken down)"}


def _inr(x):
    return f"₹{x:,.0f}"


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _glossary():
    path = os.path.join(common.SKILL_DIR, "references", "glossary.md")
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"- \*\*(.+?)\*\*: (.+)", line.strip())
            if m:
                out[m.group(1)] = m.group(2)
    return out


def _spending(a):
    months = list(a["monthly"])
    cats = sorted({c for m in a["monthly"].values() for c in m},
                  key=lambda c: -sum(m.get(c, 0) for m in a["monthly"].values()))
    out = ["## Spending", "", "| Category | " + " | ".join(months) + " | Total |",
           "|---" * (len(months) + 2) + "|"]
    for c in cats:
        vals = [a["monthly"][m].get(c, 0.0) for m in months]
        out.append(f"| {NICE.get(c, c)} | " + " | ".join(f"{v:,.0f}" for v in vals) +
                   f" | **{sum(vals):,.0f}** |")
    tot = [sum(a["monthly"][m].values()) for m in months]
    out.append("| **Total** | " + " | ".join(f"{v:,.0f}" for v in tot) + f" | **{sum(tot):,.0f}** |")
    unexp = sum(m.get("card_spend_unexpanded", 0) for m in a["monthly"].values())
    if unexp:
        out += ["", f"Card bills of {_inr(unexp)} were paid from a bank account whose card statement "
                    "has not been read, so that spending is not broken down yet. Add the card "
                    "statements to see what it went on."]
    if a.get("top_payees"):
        out += ["", "Top payees:", "", "| Payee | Category | Count | ₹ |", "|---|---|---|---|"]
        out += [f"| {p['payee']} | {NICE.get(p['category'], p['category'])} | {p['count']} | "
                f"{p['total']:,.0f} |" for p in a["top_payees"][:10]]
    if a.get("addon_spend"):
        out += ["", "Add-on card spending (counted in your spending above):", ""]
        for who, m in a["addon_spend"].items():
            out.append(f"- **{who}**: {_inr(sum(m.values()))} — " +
                       ", ".join(f"{k} {_inr(v)}" for k, v in m.items()))
    return out


def _savings(a):
    r = a["rates"]
    out = ["## Savings vs investing", "", "| | ₹ |", "|---|---|",
           f"| Income | {r['income']:,.0f} |", f"| Spending | {r['spend']:,.0f} |",
           f"| Tax | {r['tax']:,.0f} |", f"| Sent to family | {r['family']:,.0f} |",
           f"| Invested (net) | {r['invest_net']:,.0f} |"]
    if r.get("own_moved_out"):
        out.append(f"| Moved to your untracked accounts | {r['own_moved_out']:,.0f} |")
    out += ["", f"**Savings rate** {_pct(r['savings_rate'])} · **Investing rate** {_pct(r['investing_rate'])}"]
    mx = a["mix"]
    if mx.get("flows_by_type"):
        out += ["", "New money into investments this period: " +
                ", ".join(f"{k} {_inr(v)}" for k, v in sorted(mx["flows_by_type"].items(), key=lambda x: -x[1]))]
    if mx.get("holdings_missing"):
        out += ["", "Current holdings not provided (data/holdings.csv), so the overall mix is not shown."]
    else:
        out += ["", f"Holdings as of {mx.get('as_of')}: total {_inr(mx['total'])}", "",
                "| Asset type | ₹ | Share |", "|---|---|---|"]
        out += [f"| {k} | {v['value']:,.0f} | {v['share_pct']}% |"
                for k, v in sorted(mx["by_type"].items(), key=lambda x: -x[1]["value"])]
        for f in mx["flags"]:
            what = "asset type" if f["kind"] == "type_over_cap" else "single holding"
            out.append(f"- Concentration: {what} **{f['name']}** is {f['share_pct']}% of the total.")
    out += ["", f"_{ADVISER}_"]
    return out


def _flags(a):
    out = ["## Flags for review", "", "Nothing here is acted on; each item is for you to check."]
    active = [r for r in a["recurring"] if r["active"]]
    if active:
        out += ["", "**Recurring payments and auto-debits**", "",
                "| Payee | Category | How often | Usual ₹ | ₹ a year | Last | Auto-debit |",
                "|---|---|---|---|---|---|---|"]
        out += [f"| {r['payee']} | {r['category']} | {r['cadence']} | {r['typical']:,.0f} | "
                f"{'' if r['yearly_cost'] is None else format(r['yearly_cost'], ',.0f')} | {r['last']} | "
                f"{'yes' if r['mandate'] else ''} |" for r in active]
    stopped = [r for r in a["recurring"] if not r["active"]]
    if stopped:
        out += ["", "Stopped recently: " + ", ".join(f"{r['payee']} (last {r['last']})" for r in stopped)]
    if a["fees"]["items"]:
        out += ["", f"**Fees and charges: {_inr(a['fees']['total'])}**", ""]
        out += [f"- {i['date']} {i['account']}: {i['description'][:60]} — {_inr(i['amount'])}"
                for i in a["fees"]["items"][:15]]
    if a["anomalies"]:
        out += ["", "**Transactions to check**", ""]
        for x in a["anomalies"]:
            extra = f" ×{x['count']}" if x.get("count") else ""
            out.append(f"- {KIND_TEXT.get(x['kind'], x['kind'])}: {x['date']} {x['payee']} "
                       f"{_inr(abs(x['amount']))}{extra} ({x['account']})")
    if a.get("warnings"):
        out += ["", "**Data warnings**", ""]
        out += [f"- {w['date']}: {w['kind']} {_inr(abs(w['amount']))} — {w['detail']}" for w in a["warnings"]]
    if a.get("uncategorised"):
        out += ["", "**Not yet labelled** (tell Claude what these are):", ""]
        out += [f"- {u['payee']}: {u['count']} transactions, {_inr(abs(u['total']))}" for u in a["uncategorised"][:15]]
    return out


def render(a):
    head = [f"# Spending check-up — {a['from']} to {a['to']}", "",
            f"Accounts: {', '.join(a['accounts'])}. {a['rows']} transactions. Data as of {a['as_of']}."]
    if a["spend_12m"].get("annualised"):
        head.append(f"Yearly figures are scaled up from {a['spend_12m']['months_covered']} months of statements.")
    body = head + [""] + _spending(a) + [""] + _savings(a) + [""] + _flags(a) + \
        ["", "## Decisions", "", "None asked this run."]
    text = "\n".join(body)
    g = _glossary()
    used = [k for k in g if k.split(" (")[0].split(" /")[0].lower() in text.lower()]
    for k in ("Savings rate", "Investing rate"):
        if k not in used:
            used.append(k)
    return text + "\n\n## Terms used\n\n" + "\n".join(f"- **{k}**: {g[k]}" for k in used) + "\n"


def summary(a):
    r = a["rates"]
    cats = {}
    for m in a["monthly"].values():
        for c, v in m.items():
            cats[c] = cats.get(c, 0) + v
    top = sorted(cats.items(), key=lambda x: -x[1])[:3]
    kinds = {}
    for x in a["anomalies"]:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
    lines = [f"Period {a['from']} to {a['to']} ({', '.join(a['accounts'])})",
             f"Income {_inr(r['income'])} · spending {_inr(r['spend'])} · invested {_inr(r['invest_net'])} · tax {_inr(r['tax'])}",
             f"Savings rate {_pct(r['savings_rate'])} · investing rate {_pct(r['investing_rate'])}",
             "Top spending: " + ", ".join(f"{NICE.get(c, c)} {_inr(v)}" for c, v in top),
             f"Active recurring payments: {sum(1 for x in a['recurring'] if x['active'])}, "
             f"fees {_inr(a['fees']['total'])}",
             "Transactions to check: " + (", ".join(f"{k} {v}" for k, v in kinds.items()) or "none")]
    if a.get("warnings"):
        lines.append(f"Data warnings: {len(a['warnings'])}")
    if a.get("uncategorised"):
        lines.append(f"Payees not yet labelled: {len(a['uncategorised'])}")
    if cats.get("card_spend_unexpanded"):
        lines.append(f"Card spend not broken down: {_inr(cats['card_spend_unexpanded'])} (card statements missing)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--root")
    a = ap.parse_args()
    p = common.paths(common.resolve_root(a.root))
    files = sorted(glob.glob(os.path.join(p["skill_data"], "analysis-*.json")))
    if not files:
        raise SystemExit("No analysis yet: run analyse.py first.")
    an = common.load_json(files[-1])
    md = render(an)
    out = os.path.join(p["skill_data"], f"REPORT-{an['as_of']}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(summary(an) + f"\n\nFull report: {out}" if a.summary else md)


if __name__ == "__main__":
    main()
