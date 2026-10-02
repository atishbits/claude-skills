#!/usr/bin/env python3
"""Cash coming in from the bonds held, from the newest snapshot's expected
schedule: what is due in the next few weeks, income by month, principal that
is about to come back and sit idle, and bonds maturing soon.

    python3 scripts/cashflows.py [--days N] [--root PATH]

--days defaults to the profile's lookahead_days. Amounts and TDS are the ones
the Master Report states; nothing here recomputes interest."""
import argparse
import datetime as dt
import json
import sys

import common


def _end(start, days):
    return (dt.date.fromisoformat(start) + dt.timedelta(days=days)).isoformat()


def upcoming(snapshot, start, days):
    end = _end(start, days)
    rows = [f for f in snapshot["expected_cashflows"] if f["date"] and start <= f["date"] <= end]
    return sorted(rows, key=lambda f: (f["date"], f["issuer"]))


def monthly(snapshot):
    months = {}
    for f in sorted(snapshot["expected_cashflows"], key=lambda f: f["date"] or ""):
        if not f["date"]:
            continue
        m = months.setdefault(f["date"][:7], {"amount": 0.0, "principal": 0.0, "interest_net": 0.0,
                                              "interest_gross": 0.0, "tds": 0.0})
        for key in m:
            m[key] = round(m[key] + (f[key] or 0), 2)
    return months


def idle_cash(snapshot, start, days):
    rows = upcoming(snapshot, start, days)
    events = [{"date": f["date"], "issuer": f["issuer"], "isin": f["isin"],
               "principal": f["principal"]} for f in rows if (f["principal"] or 0) > 0]
    principal = round(sum(e["principal"] for e in events), 2)
    interest = round(sum(f["interest_net"] or 0 for f in rows), 2)
    return {"window_days": days, "from": start, "to": _end(start, days),
            "total_principal": principal, "total_interest_net": interest,
            "total": round(principal + interest, 2),
            "available_by": events[-1]["date"] if events else None, "events": events}


def maturities(snapshot, start, days):
    end = _end(start, days)
    due = [{"issuer": h["issuer"], "isin": h["isin"], "maturity_date": h["maturity_date"],
            "current_value": h["current_value"]}
           for h in snapshot["holdings"]
           if h["maturity_date"] and start <= h["maturity_date"] <= end]
    return sorted(due, key=lambda h: h["maturity_date"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int)
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    snapshots = common.dated_files(common.skill_data_dir(root), "snapshot-")
    if not snapshots:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    snapshot = common.load_json(snapshots[-1])
    days = args.days
    if days is None:
        try:
            days = common.load_profile(root)["lookahead_days"]
        except (FileNotFoundError, ValueError) as err:
            print(err, file=sys.stderr)
            return 1
    start = snapshot["as_of"]
    print(json.dumps({"as_of": start, "upcoming": upcoming(snapshot, start, days),
                      "monthly": monthly(snapshot), "idle_cash": idle_cash(snapshot, start, days),
                      "maturities": maturities(snapshot, start, days)},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
