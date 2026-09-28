#!/usr/bin/env python3
"""Per-lot LT/ST status and unrealized gain, from today's snapshot -- so a
SELL/trim note can name which lots and flag a short-term lot that's weeks
from turning long-term, without doing date arithmetic by hand.

    python3 scripts/tax_lots.py TICKER [--near-lt-days N]

Reads data/skill-data/snapshot-<today>.json (run fetch_fundamentals.py
first). LTCG/STCG rates for listed equity (12.5% above a Rs 1.25L/FY
exemption, 20% flat) are current as of the FY24 Budget change -- these are
published law, not personal, but verify against the current Finance Act
before relying on them. This script only sees unrealized positions: it has
no visibility into realized gains elsewhere this FY, so it cannot say how
much of the Rs 1.25L exemption is already used. Check the user's own
records (broker Console > Reports) for that before sizing a harvest."""
import argparse
import glob
import json
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
SKILL_DATA_DIR = os.path.join(ROOT, "data", "skill-data")

LT_THRESHOLD_DAYS = 365
LTCG_RATE_PCT = 12.5
STCG_RATE_PCT = 20.0
LTCG_EXEMPTION_PER_FY = 125_000


def lot_status(lot, price, today, near_lt_days=60):
    """Pure per-lot computation: LT/ST status, days held, days to LT
    conversion, unrealized gain. Returns None if the lot's date can't be
    parsed (a corporate-action lot the caller should report separately, not
    silently drop). `cost` being non-numeric (an unreconciled corporate
    action) is valid and yields gain=None, not an error."""
    d = lot.get("date")
    qty = lot.get("qty")
    cost = lot.get("cost")
    try:
        buy_date = date.fromisoformat(d)
    except (TypeError, ValueError):
        return None
    held_days = (today - buy_date).days
    is_lt = held_days >= LT_THRESHOLD_DAYS
    days_to_lt = max(0, LT_THRESHOLD_DAYS - held_days)
    gain = (price - cost) * qty if isinstance(cost, (int, float)) and qty else None
    return {
        "date": d, "qty": qty, "cost": cost, "held_days": held_days,
        "is_lt": is_lt, "days_to_lt": days_to_lt, "gain": gain,
        "near_lt": (not is_lt) and days_to_lt <= near_lt_days,
    }


def latest_snapshot():
    files = sorted(glob.glob(os.path.join(SKILL_DATA_DIR, "snapshot-*.json")))
    if not files:
        sys.exit(f"No snapshot under {SKILL_DATA_DIR}. Run fetch_fundamentals.py first.")
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh), files[-1]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker")
    p.add_argument("--near-lt-days", type=int, default=60,
                    help="flag a short-term lot within this many days of turning long-term")
    args = p.parse_args()
    ticker = args.ticker.upper()

    snap, path = latest_snapshot()
    stock = next((s for s in snap["stocks"] if s["ticker"] == ticker), None)
    if not stock:
        sys.exit(f"{ticker} not in {os.path.basename(path)}.")
    price = stock.get("price")
    lots = stock.get("lots") or []
    if not lots:
        print(f"{ticker}: no per-lot data on file (holdings CSV without a lot-level "
              f"Console export, or this ticker has none in the tradebook).")
        return
    if price is None:
        sys.exit(f"{ticker}: no current price in the snapshot.")

    today = date.today()
    print(f"{ticker} -- {len(lots)} lot(s), price {price:.2f}, "
          f"as of {snap.get('generated_at', 'unknown')}\n")

    total_lt_gain = total_st_gain = 0.0
    near_lt = []
    for lot in lots:
        status = lot_status(lot, price, today, args.near_lt_days)
        if status is None:
            print(f"  {lot.get('date')}  qty {lot.get('qty')}  cost {lot.get('cost')}  -- "
                  f"non-numeric lot (corporate action), date/qty usable for LTCG purposes but "
                  f"no cost to compute gain")
            continue
        if status["gain"] is not None:
            if status["is_lt"]:
                total_lt_gain += status["gain"]
            else:
                total_st_gain += status["gain"]
        tag = "LT" if status["is_lt"] else "ST"
        near = f"  <-- turns LT in {status['days_to_lt']}d" if status["near_lt"] else ""
        if status["near_lt"]:
            near_lt.append((status["date"], status["days_to_lt"]))
        gain_str = f"gain {status['gain']:+,.0f}" if status["gain"] is not None else "cost unknown"
        print(f"  {status['date']}  qty {status['qty']:g}  {tag} (held {status['held_days']}d)  "
              f"{gain_str}{near}")

    print(f"\nUnrealized: LT {total_lt_gain:+,.0f}, ST {total_st_gain:+,.0f}")
    if near_lt:
        print(f"{len(near_lt)} short-term lot(s) within {args.near_lt_days}d of turning long-term "
              f"({STCG_RATE_PCT:.1f}% -> {LTCG_RATE_PCT:.1f}% and exemption-eligible) -- "
              f"selling now vs. waiting is a real choice worth naming.")
    print(f"\nLTCG {LTCG_RATE_PCT:.1f}% above a Rs {LTCG_EXEMPTION_PER_FY:,}/FY exemption, "
          f"STCG {STCG_RATE_PCT:.1f}% flat (verify against the current Finance Act). "
          f"This script cannot see realized gains elsewhere this FY -- check the user's own "
          f"broker Console/Reports for exemption headroom before sizing a harvest or a "
          f"tax-free gain-booking sale.")


if __name__ == "__main__":
    main()
