#!/usr/bin/env python3
"""Append-only ledger of scan-history entries from mechanical screen, judgment,
and deep-dive reviews of candidates in the multibagger scan.

Two jobs:

  1. Record a scan entry at the moment a ticker is screened or reviewed:

         python3 scripts/scan_history.py record TICKER STAGE OUTCOME REASON
             [--date YYYY-MM-DD] [--next-checkin YYYY-MM-DD]

     STAGE is one of MECHANICAL, JUDGMENT, or DEEP-DIVE. OUTCOME is one of
     PASS, FAIL, or BORDERLINE. REASON is the justification for the outcome.
     NEXT_CHECKIN is an optional reminder date to re-check this ticker.

  2. Review the scan history and overdue re-checks:

         python3 scripts/scan_history.py report [TICKER ...] [--borderline]

     Prints every recorded entry per ticker, in order. With --borderline,
     restricts to entries whose outcome is BORDERLINE. Then always prints
     a final section of overdue re-checks (tickets whose latest entry has
     a next_checkin date in the past).

The ledger is a fact log of every scan decision and its justification.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")
LEDGER_PATH = os.path.join(DATA_DIR, "scan-history.jsonl")

VALID_STAGES = {"MECHANICAL", "JUDGMENT", "DEEP-DIVE"}
VALID_OUTCOMES = {"PASS", "FAIL", "BORDERLINE"}


def normalise_stage(stage):
    """MECHANICAL/JUDGMENT/DEEP-DIVE, case- and whitespace-insensitive.
    Raises ValueError on anything else rather than silently recording junk."""
    s = stage.strip().upper()
    if s not in VALID_STAGES:
        raise ValueError(f"stage must be one of {', '.join(sorted(VALID_STAGES))}, got {stage!r}")
    return s


def normalise_outcome(outcome):
    """PASS/FAIL/BORDERLINE, case- and whitespace-insensitive.
    Raises ValueError on anything else rather than silently recording junk."""
    o = outcome.strip().upper()
    if o not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(sorted(VALID_OUTCOMES))}, got {outcome!r}")
    return o


def append_entry(ticker, stage, outcome, reason, asof=None, next_checkin=None, ledger_path=None):
    """Append one entry to the ledger. Reason must be non-empty after stripping.
    Returns the entry dict."""
    ledger_path = ledger_path or LEDGER_PATH
    asof = asof or date.today().isoformat()
    reason = reason.strip()
    if not reason:
        raise ValueError("reason must be non-empty")
    entry = {
        "ticker": ticker.strip().upper(),
        "date": asof,
        "stage": normalise_stage(stage),
        "outcome": normalise_outcome(outcome),
        "reason": reason,
    }
    if next_checkin is not None:
        entry["next_checkin"] = next_checkin
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_history(ticker=None, ledger_path=None):
    """Load all entries from the ledger, optionally filtered to one ticker.
    Sorted by (ticker, date)."""
    ledger_path = ledger_path or LEDGER_PATH
    if not os.path.exists(ledger_path):
        return []
    entries = []
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if ticker is None or entry["ticker"] == ticker.strip().upper():
                entries.append(entry)
    entries.sort(key=lambda e: (e["ticker"], e["date"]))
    return entries


def days_overdue(checkin_date, today=None):
    """Calculate how many days past the checkin date. Returns 0 if today equals
    checkin_date, positive if overdue, negative if not yet due."""
    today = today or date.today().isoformat()
    return (datetime.fromisoformat(today) - datetime.fromisoformat(checkin_date)).days


def overdue_checkins(entries, today=None):
    """Find entries that are overdue for re-checking.
    Only the chronologically latest entry per ticker counts -- an earlier
    entry's next_checkin is superseded if the latest entry has one (or none).
    Returns sorted list of overdue entries (by next_checkin date ascending)."""
    today = today or date.today().isoformat()
    # Group by ticker, keeping only the latest entry per ticker
    latest_by_ticker = {}
    for e in entries:
        ticker = e["ticker"]
        if ticker not in latest_by_ticker or e["date"] > latest_by_ticker[ticker]["date"]:
            latest_by_ticker[ticker] = e

    # Filter to those with a next_checkin that is past
    overdue = []
    for e in latest_by_ticker.values():
        if "next_checkin" in e and e["next_checkin"] <= today:
            overdue.append(e)

    # Sort by next_checkin date ascending
    overdue.sort(key=lambda e: e["next_checkin"])
    return overdue


def build_report(entries, today=None):
    """Pure formatting: entries in, printable lines out.
    Groups by ticker, one line per entry with date, stage, outcome, reason,
    and next_checkin if present."""
    today = today or date.today().isoformat()
    by_ticker = {}
    for e in entries:
        by_ticker.setdefault(e["ticker"], []).append(e)

    lines = []
    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        lines.append(f"{ticker}")
        for e in rows:
            checkin_str = f"  next: {e['next_checkin']}" if "next_checkin" in e else ""
            lines.append(f"  {e['date']}  {e['stage']:<10}  {e['outcome']:<10}  {e['reason']}{checkin_str}")
        lines.append("")

    return lines


def cmd_record(args):
    entry = append_entry(args.ticker, args.stage, args.outcome, args.reason,
                        args.asof, args.next_checkin)
    print(f"Recorded: {entry['ticker']} {entry['stage']} {entry['outcome']} on {entry['date']}")


def cmd_report(args):
    all_entries = load_history()
    entries = all_entries

    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        entries = [e for e in entries if e["ticker"] in wanted]

    if args.borderline:
        entries = [e for e in entries if e["outcome"] == "BORDERLINE"]

    if not entries:
        print("No scan history entries yet.")
        return

    # Print the filtered entries report
    by_ticker = {}
    for e in entries:
        by_ticker.setdefault(e["ticker"], []).append(e)

    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        print(f"{ticker}")
        for e in rows:
            checkin_str = f"  next: {e['next_checkin']}" if "next_checkin" in e else ""
            print(f"  {e['date']}  {e['stage']:<10}  {e['outcome']:<10}  {e['reason']}{checkin_str}")
        print()

    # Always add overdue re-checks section (regardless of filters)
    # This always checks the FULL history
    overdue = overdue_checkins(all_entries)
    print("Overdue re-checks:")
    if overdue:
        for e in overdue:
            days = days_overdue(e["next_checkin"])
            print(f"  {e['ticker']:8}  {e['reason']:40}  {days}d overdue")
    else:
        print("  none.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append one scan entry to the ledger")
    rec.add_argument("ticker")
    rec.add_argument("stage")
    rec.add_argument("outcome")
    rec.add_argument("reason")
    rec.add_argument("--date", dest="asof")
    rec.add_argument("--next-checkin", dest="next_checkin")
    rec.set_defaults(func=cmd_record)

    rep = sub.add_parser("report", help="review the scan history and overdue re-checks")
    rep.add_argument("tickers", nargs="*")
    rep.add_argument("--borderline", action="store_true",
                    help="restrict to BORDERLINE outcomes")
    rep.set_defaults(func=cmd_report)

    args = p.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
