#!/usr/bin/env python3
"""Append-only ledger of every BUY/HOLD/SELL rating this skill has written, and
a report that scores realised performance since each one -- so the skill's
own track record is checked, not assumed.

Two jobs:

  1. Record a rating at the moment a note is written or rewritten (SKILL.md
     3g does this for every note it just verified):

         python3 scripts/rating_ledger.py record TICKER RATING PRICE "deciding sentence"
             [--date YYYY-MM-DD]

     PRICE is the price the rating was made against -- the note's own
     snapshot price, not a web price. The deciding sentence is the one that
     says why it's this rating and not the adjacent one (SKILL.md 3g.3's
     "deciding sentence"); it is what a later `report` run reads back so
     scoring the call is a short, targeted re-check against news since that
     date, not a blind guess.

  2. Score the ledger against today's prices:

         python3 scripts/rating_ledger.py report [TICKER ...]

     Prints every recorded rating per ticker, in order, with its price at
     the time, today's price from the newest snapshot, the realised return
     and days held, and the deciding sentence recorded then.

The ledger is intentionally just a fact log. Whether a thesis actually held
up is a judgment call against real news and the next result, the same as
everything else in SKILL.md 3d -- this script does not grade itself, it only
keeps the facts a grading pass needs from disappearing past the next note
rewrite, which the note template's single-hop-back `(prev ...)` field does
not preserve.
"""
import argparse
import glob
import json
import os
import sys
from datetime import date, datetime

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")
LEDGER_PATH = os.path.join(DATA_DIR, "ratings-ledger.jsonl")

VALID_RATINGS = {"BUY", "HOLD", "SELL"}
TRIM_ALIASES = {"SELL/TRIM", "SELL / TRIM", "TRIM"}


def normalise_rating(rating):
    """BUY/HOLD/SELL, case- and whitespace-insensitive; a trim is SELL.
    Raises ValueError on anything else rather than silently recording junk."""
    r = rating.strip().upper()
    if r in TRIM_ALIASES:
        return "SELL"
    if r not in VALID_RATINGS:
        raise ValueError(f"rating must be BUY, HOLD or SELL (or a trim alias), got {rating!r}")
    return r


def append_entry(ticker, rating, price, thesis, asof=None, ledger_path=None):
    ledger_path = ledger_path or LEDGER_PATH
    asof = asof or date.today().isoformat()
    price = float(price)
    if price <= 0:
        raise ValueError(f"price must be positive, got {price!r}")
    entry = {
        "ticker": ticker.strip().upper(),
        "date": asof,
        "rating": normalise_rating(rating),
        "price": price,
        "thesis": thesis.strip(),
    }
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_ledger(ticker=None, ledger_path=None):
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


def latest_snapshot_prices(data_dir=None):
    """ticker -> price from the newest snapshot-*.json, and that file's own
    path -- scoring never triggers a network call of its own, since a normal
    review already refreshed the snapshot in Step 1."""
    data_dir = data_dir or DATA_DIR
    files = sorted(glob.glob(os.path.join(data_dir, "snapshot-*.json")))
    if not files:
        return {}, None
    with open(files[-1], encoding="utf-8") as fh:
        data = json.load(fh)
    prices = {s["ticker"]: s.get("price") for s in data.get("stocks", []) if s.get("price") is not None}
    return prices, files[-1]


def days_between(earlier, later):
    """Whole days from an earlier YYYY-MM-DD date string to a later one."""
    return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).days


def realised_return_pct(entry_price, current_price):
    """Simple price return from the recorded price to the current one.
    None if either price is missing -- never silently divide by a gap."""
    if entry_price is None or current_price is None or entry_price <= 0:
        return None
    return (current_price / entry_price - 1) * 100


def build_report(entries, prices, today=None):
    """Pure formatting: entries and prices in, printable lines out -- kept
    separate from file/network access so it's testable without a snapshot."""
    today = today or date.today().isoformat()
    by_ticker = {}
    for e in entries:
        by_ticker.setdefault(e["ticker"], []).append(e)
    lines = []
    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        current = prices.get(ticker)
        header = f"{ticker}"
        header += f"  (current {current:.2f})" if current is not None else "  (no current price on file)"
        lines.append(header)
        for e in rows:
            held = days_between(e["date"], today)
            ret = realised_return_pct(e["price"], current)
            ret_str = f"{ret:+.1f}%" if ret is not None else "n/a"
            lines.append(f"  {e['date']}  {e['rating']:<4}  @ {e['price']:.2f}  -> {ret_str} over {held}d")
            lines.append(f"    thesis: {e['thesis']}")
        lines.append("")
    return lines


def cmd_record(args):
    entry = append_entry(args.ticker, args.rating, args.price, args.thesis, args.asof)
    print(f"Recorded: {entry['ticker']} {entry['rating']} @ {entry['price']:.2f} on {entry['date']}")


def cmd_report(args):
    prices, snapshot_file = latest_snapshot_prices()
    if not snapshot_file:
        sys.exit("No snapshot found -- run fetch_fundamentals.py first so today's prices exist.")
    entries = load_ledger()
    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        entries = [e for e in entries if e["ticker"] in wanted]
    if not entries:
        print("No ledger entries yet -- nothing recorded. The ledger only starts counting from "
              "the first `record` call onward; it cannot retroactively score ratings written "
              "before it existed.")
        return
    print(f"Ratings ledger -- scored against {os.path.basename(snapshot_file)}\n")
    for line in build_report(entries, prices):
        print(line)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append one rating to the ledger")
    rec.add_argument("ticker")
    rec.add_argument("rating")
    rec.add_argument("price", type=float)
    rec.add_argument("thesis")
    rec.add_argument("--date", dest="asof")
    rec.set_defaults(func=cmd_record)

    rep = sub.add_parser("report", help="score the ledger against today's snapshot prices")
    rep.add_argument("tickers", nargs="*")
    rep.set_defaults(func=cmd_report)

    args = p.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
