#!/usr/bin/env python3
"""Append-only ledger of scan-history entries from mechanical screen, judgment,
and deep-dive reviews of candidates in the multibagger scan.

Three jobs:

  1. Record a scan entry at the moment a ticker is screened or reviewed:

         python3 scripts/scan_history.py record TICKER STAGE OUTCOME REASON
             [--date YYYY-MM-DD] [--next-checkin YYYY-MM-DD]

     STAGE is one of MECHANICAL, JUDGMENT, or DEEP-DIVE. OUTCOME is one of
     PASS, FAIL, or BORDERLINE. REASON is the justification for the outcome.
     NEXT_CHECKIN is an optional reminder date to re-check this ticker.

  2. Record every stock in a multibagger_screen.py shortlist in one go:

         python3 scripts/scan_history.py record-shortlist FILE
             [--stage mechanical] [--date YYYY-MM-DD]

     FILE is a multibagger-shortlist-*.json written by multibagger_screen.py.
     Appends one entry per stock in its "stocks" list, using the stock's
     quality_verdict as OUTCOME and its mechanical "reason" field as REASON.

  3. Review the scan history and overdue re-checks:

         python3 scripts/scan_history.py report [TICKER ...] [--borderline]

     Prints every recorded entry per ticker, in order. With --borderline,
     restricts to entries whose outcome is BORDERLINE. Then always prints
     a final section of overdue re-checks: tickers whose most recent
     reminder (the latest entry that carries a next_checkin) is due today
     or earlier. A later entry without a next_checkin does not clear an
     earlier reminder -- see overdue_checkins.

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


def record_shortlist(shortlist_path, stage="mechanical", asof=None, ledger_path=None):
    """Append one entry per stock in a multibagger_screen.py shortlist file
    (multibagger-shortlist-*.json): outcome is the stock's quality_verdict
    (pass/fail/borderline), reason is its mechanical "reason" string.

    Every stock is validated (ticker, stage, outcome and non-blank reason)
    before anything is written, so a malformed file raises ValueError and
    leaves the ledger untouched instead of recording half of it. A file
    with an empty "stocks" list records nothing. Returns the appended
    entries in file order."""
    with open(shortlist_path, encoding="utf-8") as fh:
        data = json.load(fh)
    stocks = data.get("stocks") if isinstance(data, dict) else None
    if not isinstance(stocks, list):
        raise ValueError(f"{shortlist_path}: no \"stocks\" list -- is this a multibagger-shortlist file?")

    normalise_stage(stage)
    rows = []
    for i, s in enumerate(stocks):
        if not isinstance(s, dict):
            raise ValueError(f"{shortlist_path}: stocks[{i}] is not an object")
        ticker, verdict, reason = s.get("ticker"), s.get("quality_verdict"), s.get("reason")
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError(f"{shortlist_path}: stocks[{i}] has no ticker")
        ticker = ticker.strip()
        if not isinstance(verdict, str):
            raise ValueError(f"{shortlist_path}: {ticker} has no quality_verdict")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason:
            raise ValueError(f"{shortlist_path}: {ticker} has no \"reason\" -- "
                             "re-run multibagger_screen.py to regenerate the shortlist")
        normalise_outcome(verdict)
        rows.append((ticker, verdict, reason))

    return [append_entry(t, stage, v, r, asof=asof, ledger_path=ledger_path) for t, v, r in rows]


def load_history(ticker=None, ledger_path=None):
    """Load all entries from the ledger, optionally filtered to one ticker.
    Sorted by (ticker, date). The sort is stable, so entries sharing a
    ticker and date keep their file (append) order -- overdue_checkins
    relies on that to break same-day ties."""
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
    """Find tickers whose current reminder is due for re-checking.

    Per ticker, only entries that carry a non-None next_checkin are
    candidates; entries without one are ignored entirely, so a later
    entry with no next_checkin never erases an earlier entry's reminder.
    Among the candidates, the one with the latest (date, list position)
    is that ticker's current reminder -- same-date ties go to the entry
    that appears later in `entries` (for load_history's output, that is
    the one appended later in the ledger file, since its sort is stable).
    A later reminder therefore supersedes an earlier one, whether it moves
    the date earlier or later. That reminder is overdue when its
    next_checkin is on or before `today`. A ticker with no next_checkin on
    any entry contributes nothing.

    This is what lets the multibagger-scan funnel record mechanical,
    judgment and deep-dive stages for one ticker on the same day while
    only the deep-dive entry sets the reminder.

    Returns the overdue reminder entries, sorted by next_checkin ascending."""
    today = today or date.today().isoformat()
    # Per ticker, the latest (date, position) entry that carries a reminder
    current_by_ticker = {}
    for pos, e in enumerate(entries):
        if e.get("next_checkin") is None:
            continue
        key = (e["date"], pos)
        best = current_by_ticker.get(e["ticker"])
        if best is None or key > best[0]:
            current_by_ticker[e["ticker"]] = (key, e)

    overdue = [e for _, e in current_by_ticker.values() if e["next_checkin"] <= today]

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


def cmd_record_shortlist(args):
    entries = record_shortlist(args.file, args.stage, args.asof)
    counts = {}
    for e in entries:
        counts[e["outcome"]] = counts.get(e["outcome"], 0) + 1
    summary = ", ".join(f"{counts[o]} {o}" for o in sorted(counts)) or "nothing to record"
    stage = entries[0]["stage"] if entries else normalise_stage(args.stage)
    print(f"Recorded {len(entries)} {stage} entries from {os.path.basename(args.file)} ({summary})")


def cmd_report(args):
    all_entries = load_history()
    entries = all_entries

    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        entries = [e for e in entries if e["ticker"] in wanted]

    if args.borderline:
        entries = [e for e in entries if e["outcome"] == "BORDERLINE"]

    # Print the filtered entries report (if any)
    if entries:
        for line in build_report(entries):
            print(line)
    elif not args.tickers and not args.borderline:
        # Only show "no entries" if we're showing the full ledger (no filters)
        print("No scan history entries yet.")

    # Always add overdue re-checks section (regardless of filters)
    # This always checks the FULL history, not the filtered view
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

    rs = sub.add_parser("record-shortlist",
                        help="append one entry per stock in a multibagger-shortlist-*.json file")
    rs.add_argument("file")
    rs.add_argument("--stage", default="mechanical")
    rs.add_argument("--date", dest="asof")
    rs.set_defaults(func=cmd_record_shortlist)

    rep = sub.add_parser("report", help="review the scan history and overdue re-checks")
    rep.add_argument("tickers", nargs="*")
    rep.add_argument("--borderline", action="store_true",
                    help="restrict to BORDERLINE outcomes")
    rep.set_defaults(func=cmd_report)

    args = p.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
