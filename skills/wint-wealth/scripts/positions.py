#!/usr/bin/env python3
"""One row per bond held, from the newest snapshot: what went in, what has
come back, what is still to come and when.

    python3 scripts/positions.py [--root PATH]   # also writes data/skill-data/POSITIONS.md

Every amount is the Master Report's own figure, summed per bond; nothing here
recomputes interest. `past_due` is a scheduled payment dated before the
report that the report does not show as received: a late payment or a report
that lags the bank. It is counted inside `to_come`.

`return_pct` is the yearly return (XIRR) on the bond's own dated cash flows:
what was paid on each purchase date, what the report says came back, and what
it schedules, with TDS added back because it is tax paid, not money lost.
`post_tax_return_pct` applies the profile's tax rate to it. Ratings come from
bond-facts.json."""
import argparse
import datetime as dt
import json
import os
import sys

import bond_facts
import common


def xirr(flows):
    """Yearly rate at which dated flows [(iso_date, amount), ...] net to zero,
    as a percentage, or None when they never do (no outlay, or no return)."""
    flows = [(dt.date.fromisoformat(d), a) for d, a in flows if d and a]
    if not flows or min(a for _, a in flows) >= 0 or max(a for _, a in flows) <= 0:
        return None
    start = min(d for d, _ in flows)

    def npv(rate):
        return sum(a / (1 + rate) ** ((d - start).days / 365) for d, a in flows)

    low, high = -0.99, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return round(100 * (low + high) / 2, 2)


def _gross(rows):
    return [(r["date"], (r.get("amount") or 0) + (r.get("tds") or 0)) for r in rows]


def _sums(rows):
    out = {"principal": 0.0, "interest_net": 0.0, "tds": 0.0, "total": 0.0}
    for r in rows:
        out["principal"] += r.get("principal") or 0
        out["interest_net"] += r.get("interest_net") or 0
        out["tds"] += r.get("tds") or 0
        out["total"] += r.get("amount") or 0
    return {k: round(v, 2) for k, v in out.items()}


def position(holding, snapshot, facts=(), tax_rate_pct=None):
    isin, as_of = holding["isin"], snapshot["as_of"]
    received = [r for r in snapshot["received_cashflows"] if r["isin"] == isin]
    expected = sorted((f for f in snapshot["expected_cashflows"] if f["isin"] == isin and f["date"]),
                      key=lambda f: f["date"])
    buys = [p for p in snapshot["purchases"] if p["isin"] == isin and p["date"]]
    bought = sorted(p["date"] for p in buys)
    fact = bond_facts.lookup(facts, isin=isin) or {}
    rate = xirr([(p["date"], -(p["invested"] or 0)) for p in buys]
                + _gross(received) + _gross(expected))
    late = [f for f in expected if f["date"] < as_of]
    ahead = [f for f in expected if f["date"] >= as_of]
    got, due = _sums(received), _sums(expected)
    invested = holding["invested"] or 0
    return {
        "issuer": holding["issuer"], "isin": isin, "bought": bought[0] if bought else None,
        "rating": fact.get("rating"), "rating_scope": fact.get("rating_scope"),
        "agency": fact.get("agency"), "outlook": fact.get("outlook"),
        "invested": invested, "ytm": holding["ytm"], "return_pct": rate,
        "post_tax_return_pct": (round(rate * (1 - tax_rate_pct / 100), 2)
                                if rate is not None and tax_rate_pct is not None else None),
        "current_value": holding["current_value"],
        "received": got, "to_come": due,
        "past_due": round(sum(f["amount"] or 0 for f in late), 2),
        "next_payment": {"date": ahead[0]["date"], "amount": ahead[0]["amount"]} if ahead else None,
        "principal_dates": [{"date": f["date"], "principal": f["principal"]}
                            for f in expected if (f["principal"] or 0) > 0],
        "last_payment_date": expected[-1]["date"] if expected else holding["maturity_date"],
        "net_if_all_paid": round(got["total"] + due["total"] - invested, 2),
    }


def positions(snapshot, facts=(), tax_rate_pct=None):
    rows = sorted((position(h, snapshot, facts, tax_rate_pct) for h in snapshot["holdings"]),
                  key=lambda r: (r["last_payment_date"] or "", r["issuer"]))
    totals = {"invested": round(sum(r["invested"] for r in rows), 2),
              "received": _total(rows, "received"), "to_come": _total(rows, "to_come"),
              "past_due": round(sum(r["past_due"] for r in rows), 2),
              "net_if_all_paid": round(sum(r["net_if_all_paid"] for r in rows), 2)}
    everything = [(p["date"], -(p["invested"] or 0)) for p in snapshot["purchases"]] \
        + _gross(snapshot["received_cashflows"]) + _gross(snapshot["expected_cashflows"])
    totals["return_pct"] = xirr(everything)
    return {"as_of": snapshot["as_of"], "positions": rows, "totals": totals,
            "return_basis": "return_pct is XIRR on the report's dated flows, before income tax, "
                            "and assumes every scheduled payment arrives in full and on time. "
                            + (f"post_tax_return_pct = return_pct x (1 - {tax_rate_pct}%): an "
                               "approximation that treats the whole return as slab-taxed interest."
                               if tax_rate_pct is not None else "No tax rate given."),
            "basis": "amounts are after TDS; TDS is tax already paid on your behalf, not a loss. "
                     "net_if_all_paid = received + to come - invested, before income tax."}


def _total(rows, key):
    return {k: round(sum(r[key][k] for r in rows), 2)
            for k in ("principal", "interest_net", "tds", "total")}


def _cell(value):
    return "" if value is None else str(value).replace("|", "/")


def _principal_text(dates):
    if not dates:
        return "none scheduled"
    if len(dates) <= 3:
        return "; ".join(f"{d['principal']} on {d['date']}" for d in dates)
    return f"{len(dates)} payments, {dates[0]['date']} to {dates[-1]['date']}"


def _rating_text(row):
    if not row["rating"]:
        return "unrated"
    scope = "" if row["rating_scope"] == "this bond" else f" ({row['rating_scope'] or 'scope not recorded'})"
    return row["rating"] + scope


HEADER = ["Issuer", "ISIN", "Rating", "Outlook", "Bought", "Invested", "Return % a year",
          "Post-tax % a year", "Interest received", "Principal received", "Principal to come",
          "Interest to come", "Past due", "Principal comes back", "Net if all paid"]


def table_rows(result):
    """The per-bond table as lists of cells, with the totals as the last row."""
    rows = [[r["issuer"], r["isin"], _rating_text(r), r["outlook"] or "not recorded", r["bought"],
             r["invested"], r["return_pct"], r["post_tax_return_pct"],
             r["received"]["interest_net"], r["received"]["principal"], r["to_come"]["principal"],
             r["to_come"]["interest_net"], r["past_due"], _principal_text(r["principal_dates"]),
             r["net_if_all_paid"]] for r in result["positions"]]
    t = result["totals"]
    rows.append(["Total", "", "", "", "", t["invested"], t["return_pct"], "",
                 t["received"]["interest_net"], t["received"]["principal"],
                 t["to_come"]["principal"], t["to_come"]["interest_net"], t["past_due"], "",
                 t["net_if_all_paid"]])
    return rows


def render_table(result):
    lines = ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(HEADER)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in table_rows(result)]
    return "\n".join(lines)


def render_markdown(result):
    return "\n\n".join([
        "# Wint Wealth: returns by bond",
        f"As of {result['as_of']}. Generated by positions.py; do not edit by hand.",
        render_table(result), result["basis"], result["return_basis"]]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    snapshots = common.dated_files(common.skill_data_dir(root), "snapshot-")
    if not snapshots:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    try:
        rate = common.tax_rate(common.load_profile(root))
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        return 1
    data = common.skill_data_dir(root)
    result = positions(common.load_json(snapshots[-1]),
                       bond_facts.load(bond_facts.facts_path(root)), rate)
    with open(os.path.join(data, "POSITIONS.md"), "w", encoding="utf-8") as fh:
        fh.write(render_markdown(result))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
