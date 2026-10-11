#!/usr/bin/env python3
"""The period a briefing covers: from the last run to now, never more than
seven days.

    python3 scripts/window.py [--days N] [--last-run TS] [--now TS] [--state PATH]

Prints JSON: start, end (UTC), basis (why this start was chosen), label (for the
digest heading) and hours (the window's length). --last-run overrides the state
file, for a surface that has no local state and read the time from elsewhere."""
import argparse
import json
import os
from datetime import timedelta

from common import data_dir, format_ts, now_utc, parse_ts, read_last_run

MAX_DAYS = 7


def compute_window(now, last_run=None, days=None, max_days=MAX_DAYS):
    cap = now - timedelta(days=max_days)
    if days is not None:
        used = max(1, min(days, max_days))
        basis = f"last {used} days (requested)"
        if used != days:
            basis = f"last {used} days (requested {days}; the limit is 1 to {max_days})"
        return now - timedelta(days=used), now, basis
    if last_run is None:
        return cap, now, f"last {max_days} days (no earlier run recorded)"
    if last_run > now:
        return cap, now, f"last {max_days} days (the recorded last run is in the future)"
    if last_run < cap:
        return cap, now, f"last {max_days} days (last run was earlier)"
    return last_run, now, "since last run"


def label(start, end):
    return f"{start.day} {start:%b} to {end.day} {end:%b}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int)
    ap.add_argument("--last-run")
    ap.add_argument("--now")
    ap.add_argument("--state", default=os.path.join(data_dir(), "state.json"))
    args = ap.parse_args(argv)

    now = parse_ts(args.now) if args.now else now_utc()
    last_run = parse_ts(args.last_run) if args.last_run else read_last_run(args.state)
    start, end, basis = compute_window(now, last_run, args.days)
    print(json.dumps({
        "start": format_ts(start), "end": format_ts(end), "basis": basis,
        "label": label(start, end),
        "hours": round((end - start).total_seconds() / 3600, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
