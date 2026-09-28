#!/usr/bin/env python3
"""Turns each researched holding's next-results window and technical re-look
levels into a plain markdown file -- data/skill-data/calendar.md -- so a
calendar-integration step (a connected Google Calendar, or a separate Claude
session with a calendar-writing tool) has a portable, deterministic list of
dates and levels to turn into reminders. This script never calls a calendar
API itself; it only computes the dates and levels, which is the part that
has one correct answer given the inputs.

    python3 scripts/calendar_notes.py [TICKER ...]

With no tickers, covers every holding in the newest snapshot. Two kinds of
rows, both computed from data the skill already fetched in Step 1 -- no
re-fetch, no network call of its own:

  - Next results window: the next quarter's end (last reported quarter end
    plus 3 months) plus 45-75 days, the typical reporting lag for a listed
    Indian company. Always an estimate, never a confirmed filing date --
    confirming the actual date is a news/WebSearch job, not this script's.
  - Price re-look levels: the 200 DMA (or 50 DMA, where 200 is unreliable)
    and the 60-day low from `technicals`, flagged DUE NOW when today's price
    is within ~3% of the level, otherwise listed as a standing watch level.
"""
import argparse
import calendar as _cal
import glob
import json
import os
from datetime import date, timedelta

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")
CALENDAR_PATH = os.path.join(DATA_DIR, "calendar.md")

RESULTS_LAG_MIN_DAYS = 45
RESULTS_LAG_MAX_DAYS = 75
NEAR_LEVEL_PCT = 3.0


def newest_snapshot(data_dir=None):
    data_dir = data_dir or DATA_DIR
    files = sorted(glob.glob(os.path.join(data_dir, "snapshot-*.json")))
    if not files:
        return None, None
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh), files[-1]


def next_results_window(latest_quarter_end):
    """(start, end) dates for the next results window, from the last quarter
    end plus the typical reporting lag. `latest_quarter_end` is 'YYYY-MM-DD'
    for the quarter just reported; the next quarter ends 3 months later, and
    that quarter's results follow it by RESULTS_LAG_MIN..MAX_DAYS days."""
    y, m, d = (int(x) for x in latest_quarter_end.split("-"))
    next_month = m + 3
    next_year = y + (next_month - 1) // 12
    next_month = ((next_month - 1) % 12) + 1
    # Clamp the day for a target month shorter than the source day (e.g. Dec
    # 31 + 3mo lands in Mar, which has 31, but Jun 30 + 3mo lands in Sep,
    # which only has 30).
    last_day_of_month = _cal.monthrange(next_year, next_month)[1]
    next_quarter_end = date(next_year, next_month, min(d, last_day_of_month))
    return (next_quarter_end + timedelta(days=RESULTS_LAG_MIN_DAYS),
            next_quarter_end + timedelta(days=RESULTS_LAG_MAX_DAYS))


def near_level(current_price, level, pct_threshold=NEAR_LEVEL_PCT):
    if current_price is None or level is None or level <= 0:
        return False
    return abs(current_price - level) / level * 100 <= pct_threshold


def price_level_rows(ticker, price, technicals):
    rows = []
    if technicals.get("dma200_reliable", True) and technicals.get("dma200"):
        rows.append(("200 DMA", technicals["dma200"]))
    elif technicals.get("dma50"):
        rows.append(("50 DMA", technicals["dma50"]))
    if technicals.get("range_60d_low"):
        rows.append(("60-day low", technicals["range_60d_low"]))
    out = []
    for label, level in rows:
        due_now = near_level(price, level)
        detail = f"{label} at {level:.2f}"
        if price is not None:
            detail += f" (current {price:.2f})"
        if due_now:
            detail = "DUE NOW -- " + detail
        out.append({"ticker": ticker, "kind": "price-level", "detail": detail, "due_now": due_now})
    return out


def build_rows(stocks, tickers=None):
    wanted = {t.upper() for t in tickers} if tickers else None
    rows = []
    for s in stocks:
        ticker = s.get("ticker")
        if not ticker or (wanted and ticker.upper() not in wanted):
            continue
        price = s.get("price")
        lqe = s.get("latest_quarter_end")
        if lqe:
            start, end = next_results_window(lqe)
            rows.append({
                "ticker": ticker, "kind": "results-estimate",
                "detail": (f"Next results likely due {start.isoformat()} to {end.isoformat()} "
                           f"(estimate, {RESULTS_LAG_MIN_DAYS}-{RESULTS_LAG_MAX_DAYS}d after the "
                           f"{lqe} quarter end) -- confirm the date before relying on it."),
                "due_now": False,
            })
        rows.extend(price_level_rows(ticker, price, s.get("technicals") or {}))
    return rows


def write_calendar_md(rows, path=None):
    path = path or CALENDAR_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "# Calendar candidates",
        "",
        "Generated by `calendar_notes.py`. A portable, plain-text input for a calendar "
        "integration step (a connected Google Calendar, or a session with a calendar-writing "
        "tool) -- this skill does not write calendar events itself.",
        "",
        "| Ticker | Type | Detail |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['ticker']} | {r['kind']} | {r['detail']} |")
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*")
    args = p.parse_args()
    data, snapshot_file = newest_snapshot()
    if not data:
        raise SystemExit("No snapshot found -- run fetch_fundamentals.py first.")
    rows = build_rows(data.get("stocks", []), args.tickers or None)
    path = write_calendar_md(rows)
    due_now = sum(1 for r in rows if r.get("due_now"))
    print(f"Wrote {len(rows)} calendar candidate(s) ({due_now} due now) to {path}, "
          f"from {os.path.basename(snapshot_file)}.")


if __name__ == "__main__":
    main()
