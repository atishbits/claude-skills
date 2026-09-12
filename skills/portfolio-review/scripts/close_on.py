#!/usr/bin/env python3
"""Closing price on a given date, from the chart series fetch_fundamentals.py
already cached. Used to find the close an analyst target was written against:
aggregators' "price at report" columns can't be trusted (Trendlyne's shows
today's price on every row).

    python3 scripts/close_on.py TICKER YYYY-MM-DD [YYYY-MM-DD ...]

Prints the last close on or before each date, plus today's close and the gap,
so the ~15% staleness rule can be applied directly. Reads the newest cached
chart for the ticker; run fetch_fundamentals.py (or --screen) first if none."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", ".cache")


def closes(ticker):
    files = sorted(glob.glob(os.path.join(CACHE_DIR, f"{ticker}-chart-*.json")))
    if not files:
        sys.exit(f"No cached chart for {ticker}. Run: python3 scripts/fetch_fundamentals.py "
                 f"{ticker}  (or --screen {ticker} if you don't hold it)")
    with open(files[-1], encoding="utf-8") as fh:
        data = json.load(fh)
    for ds in data.get("datasets", []):
        if ds.get("metric") == "Price":
            return [(d, float(v)) for d, v in ds["values"]]
    sys.exit(f"Cached chart for {ticker} has no price series.")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ticker, dates = sys.argv[1].upper(), sys.argv[2:]
    series = closes(ticker)
    last_day, last = series[-1]
    print(f"{ticker} latest close {last:,.2f} ({last_day})")
    for q in dates:
        prior = [c for c in series if c[0] <= q]
        if not prior:
            print(f"  {q}: before the cached series starts ({series[0][0]})")
            continue
        d, v = prior[-1]
        gap = (v - last) / last * 100
        stale = "  STALE (>15% from today)" if abs(gap) > 15 else ""
        print(f"  {q}: close {v:,.2f} on {d}, {gap:+.1f}% vs today{stale}")


if __name__ == "__main__":
    main()
