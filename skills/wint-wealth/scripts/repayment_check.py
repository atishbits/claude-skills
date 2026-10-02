#!/usr/bin/env python3
"""Did every payment that was due actually arrive, in full?

    python3 scripts/repayment_check.py [--root PATH]

Compares the payments received in the newest snapshot against the schedule
recorded in an EARLIER snapshot (the newest one dated before it). A payment
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


def pick_baseline(snapshots, current):
    earlier = [s for s in snapshots if s["as_of"] < current["as_of"]]
    return max(earlier, key=lambda s: s["as_of"]) if earlier else None


def check(baseline, current, grace_days=5, tolerance=1.0):
    if baseline is None:
        return {"baseline": None, "checked": 0, "flags": [],
                "note": "no baseline yet: this is the first snapshot, so late or short payments "
                        "cannot be detected until the next one"}
    grace = dt.timedelta(days=grace_days)
    cutoff = (dt.date.fromisoformat(current["as_of"]) - grace).isoformat()
    flags, checked = [], 0
    for due in baseline["expected_cashflows"]:
        if not due["date"] or not (baseline["as_of"] <= due["date"] <= cutoff):
            continue
        checked += 1
        due_date = dt.date.fromisoformat(due["date"])
        received = round(sum(
            _gross(r) for r in current["received_cashflows"]
            if r["isin"] == due["isin"] and r["date"]
            and abs(dt.date.fromisoformat(r["date"]) - due_date) <= grace), 2)
        expected = _gross(due)
        if received + tolerance < expected:
            flags.append({"issuer": due["issuer"], "isin": due["isin"], "date": due["date"],
                          "expected": expected, "received": received,
                          "kind": "missing" if received == 0 else "short"})
    return {"baseline": baseline["as_of"], "checked": checked, "flags": flags,
            "note": f"compared against the schedule recorded on {baseline['as_of']}"}


def overdue(current, grace_days=5, tolerance=1.0):
    """Payments the report still lists as upcoming although their date passed
    more than `grace_days` ago and no matching receipt is recorded. Needs only
    one snapshot, so it works on the first run. It can also mean the report
    lags the bank: check the bank statement before drawing a conclusion."""
    grace = dt.timedelta(days=grace_days)
    as_of = dt.date.fromisoformat(current["as_of"])
    flags = []
    for due in current["expected_cashflows"]:
        if not due["date"]:
            continue
        due_date = dt.date.fromisoformat(due["date"])
        if due_date >= as_of - grace:
            continue
        received = round(sum(
            _gross(r) for r in current["received_cashflows"]
            if r["isin"] == due["isin"] and r["date"]
            and abs(dt.date.fromisoformat(r["date"]) - due_date) <= grace), 2)
        expected = _gross(due)
        if received + tolerance < expected:
            flags.append({"issuer": due["issuer"], "isin": due["isin"], "date": due["date"],
                          "expected": expected, "received": received,
                          "days_late": (as_of - due_date).days, "kind": "overdue"})
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
    result = check(pick_baseline(snapshots, current), current)
    result["overdue"] = overdue(current)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
