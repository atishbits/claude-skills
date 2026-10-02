#!/usr/bin/env python3
"""Did every payment that was due actually arrive, in full?

    python3 scripts/repayment_check.py [--root PATH]

Compares the payments received in the newest snapshot against the schedules
recorded in every EARLIER snapshot (for each due, the newest schedule dated on
or before it). Rows for one bond on the same date are summed before comparing. A payment
that is missing, or short by more than a rupee, is flagged; SKILL.md treats a
flag as an automatic REVIEW of that holding, because a late or short payment
shows up here before any rating agency acts.

The first run has no earlier snapshot. It reports "no baseline yet" and flags
nothing: that is not a clean result, only an absent one.

Separately, `overdue` lists payments the newest report still shows as upcoming
although their date has passed with no receipt recorded. That needs only one
snapshot. It may be a late payment or a report that lags the bank; either way
the holding goes to REVIEW until the bank statement settles it.

Amounts are compared gross (principal plus interest before TDS), so a change
in TDS is not mistaken for a short payment."""
import argparse
import datetime as dt
import json
import sys

import common


def _gross(row):
    return round((row.get("principal") or 0) + (row.get("interest_gross") or 0), 2)


def earlier_snapshots(snapshots, current):
    """Snapshots dated strictly before the one being checked, oldest first."""
    return sorted((s for s in snapshots if s["as_of"] < current["as_of"]),
                  key=lambda s: s["as_of"])


def _add(groups, due):
    group = groups.setdefault((due["isin"], due["date"]), {"issuer": due["issuer"],
                                                           "expected": 0.0})
    group["expected"] = round(group["expected"] + _gross(due), 2)


def _clusters(groups, grace):
    """Dues for one bond whose matching windows overlap are judged together,
    so one receipt is never counted against two dues."""
    by_isin = {}
    for (isin, date), group in sorted(groups.items()):
        by_isin.setdefault(isin, []).append((dt.date.fromisoformat(date), group))
    for isin, dues in by_isin.items():
        cluster = [dues[0]]
        for due in dues[1:]:
            if due[0] - cluster[-1][0] <= 2 * grace:
                cluster.append(due)
            else:
                yield isin, cluster
                cluster = [due]
        yield isin, cluster


def _shortfalls(groups, current, grace, tolerance):
    for isin, cluster in _clusters(groups, grace):
        first, last = cluster[0][0], cluster[-1][0]
        expected = round(sum(g["expected"] for _, g in cluster), 2)
        received = round(sum(
            _gross(r) for r in current["received_cashflows"]
            if r["isin"] == isin and r["date"]
            and first - grace <= dt.date.fromisoformat(r["date"]) <= last + grace), 2)
        if received + tolerance < expected:
            yield {"issuer": cluster[0][1]["issuer"], "isin": isin, "date": first.isoformat(),
                   "expected": expected, "received": received}, first


def check(baselines, current, grace_days=5, tolerance=1.0):
    """`baselines` is every earlier snapshot (one dict is accepted too). Each
    due is taken from the newest schedule recorded on or before its date, so a
    due is still checked when snapshots are days apart or a month apart."""
    if isinstance(baselines, dict):
        baselines = [baselines]
    earlier = earlier_snapshots(baselines or [], current)
    if not earlier:
        return {"baseline": None, "checked": 0, "flags": [],
                "note": "no baseline yet: this is the first snapshot, so late or short payments "
                        "cannot be detected until the next one"}
    grace = dt.timedelta(days=grace_days)
    cutoff = (dt.date.fromisoformat(current["as_of"]) - grace).isoformat()
    groups = {}
    for snapshot in earlier:
        own = {}
        for due in snapshot["expected_cashflows"]:
            if due["date"] and snapshot["as_of"] <= due["date"] <= cutoff:
                _add(own, due)
        groups.update(own)
    flags = []
    for flag, _ in _shortfalls(groups, current, grace, tolerance):
        flag["kind"] = "missing" if flag["received"] == 0 else "short"
        flags.append(flag)
    since = earlier[0]["as_of"]
    note = (f"compared against schedules recorded since {since}" if groups else
            f"nothing was checkable: no payment recorded since {since} fell due more than "
            f"{grace_days} days before {current['as_of']}. This is not a clean result.")
    return {"baseline": earlier[-1]["as_of"], "checked": len(groups), "flags": flags,
            "note": note}


def overdue(current, grace_days=5, tolerance=1.0):
    """Payments the report still lists as upcoming although their date passed
    more than `grace_days` ago and no matching receipt is recorded. Needs only
    one snapshot, so it works on the first run. It can also mean the report
    lags the bank: check the bank statement before drawing a conclusion."""
    grace = dt.timedelta(days=grace_days)
    as_of = dt.date.fromisoformat(current["as_of"])
    groups = {}
    for due in current["expected_cashflows"]:
        if due["date"] and dt.date.fromisoformat(due["date"]) < as_of - grace:
            _add(groups, due)
    flags = []
    for flag, first in _shortfalls(groups, current, grace, tolerance):
        flag["days_late"] = (as_of - first).days
        flag["kind"] = "overdue"
        flags.append(flag)
    return flags


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    paths = common.dated_files(common.skill_data_dir(common.resolve_root(args.root)), "snapshot-")
    if not paths:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    snapshots = [common.load_json(p) for p in paths]
    current = snapshots[-1]
    result = check(snapshots, current)
    result["overdue"] = overdue(current)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
