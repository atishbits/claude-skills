#!/usr/bin/env python3
"""Per-lot LT/ST status and unrealized gain, from today's snapshot -- so a
SELL/trim note can name which lots and flag a short-term lot that's weeks
from turning long-term, without doing date arithmetic by hand.

    python3 scripts/tax_lots.py TICKER [--near-lt-days N]
    python3 scripts/tax_lots.py --harvest

Reads data/skill-data/snapshot-<today>.json (run fetch_fundamentals.py
first). LTCG/STCG rates for listed equity (12.5% above a Rs 1.25L/FY
exemption, 20% flat) are current as of the FY24 Budget change -- these are
published law, not personal, but verify against the current Finance Act
before relying on them.

--harvest reads the snapshot's tax_position block (parsed from the Console
export's own "Tax position" section, if the input is a lot-level .md rather
than a plain CSV) for this FY's realised gains and Console's own
loss-harvesting estimate, and lists every holding's LT-gain lots (candidates
for tax-free gain booking against the Rs 1.25L exemption) and loss lots
(candidates for harvesting) across the whole portfolio, not one ticker at a
time. Without a tax_position block (CSV-only input, or an older Console
export), it says so and falls back to per-lot figures alone, without a
realised-gains baseline to size a harvest against."""
import argparse
import calendar
import glob
import json
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
SKILL_DATA_DIR = os.path.join(ROOT, "data", "skill-data")

LTCG_RATE_PCT = 12.5
STCG_RATE_PCT = 20.0
LTCG_EXEMPTION_PER_FY = 125_000


def add_months(d, months):
    """d + `months` calendar months, clamping the day when the target month
    is shorter (31 Jan + 1mo -> 28/29 Feb, not an overflow into March)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def is_long_term(buy_date, as_of):
    """India's listed-equity LTCG test is "held for more than 12 months",
    not "365 days": those two disagree whenever a leap day falls inside the
    window (12 calendar months after 29 Feb 2024 is 28 Feb 2025 -- 365 days
    away -- but 12 months after 1 Mar 2023 is 1 Mar 2024 -- 366 days away,
    because that window crosses a leap day). A fixed day-count threshold
    cannot get both right; only calendar-month arithmetic can. `as_of` must
    be strictly after the 12-month mark -- the anniversary date itself is
    still short-term, a real off-by-one an earlier version of this script
    got wrong (verified against a real Zerodha Console export, which reports
    a lot bought 2025-11-28 as turning long-term on 2026-11-29, not
    2026-11-28)."""
    return as_of > add_months(buy_date, 12)


def lot_status(lot, price, today, near_lt_days=60, fallback_cost=None):
    """Pure per-lot computation: LT/ST status, days held, days to LT
    conversion, unrealized gain. Returns None if the lot's date can't be
    parsed (a corporate-action lot the caller should report separately, not
    silently drop). `cost` being non-numeric (an unreconciled corporate
    action, e.g. a demerger) falls back to `fallback_cost` -- the holding's
    own broker-reported average cost, which already reflects the demerger's
    prescribed cost-allocation split -- and the result is labelled as an
    estimate rather than dropped from every total silently."""
    d = lot.get("date")
    qty = lot.get("qty")
    cost = lot.get("cost")
    try:
        buy_date = date.fromisoformat(d)
    except (TypeError, ValueError):
        return None
    held_days = (today - buy_date).days
    is_lt = is_long_term(buy_date, today)
    conversion = add_months(buy_date, 12)
    days_to_lt = 0 if is_lt else (conversion - today).days + 1
    cost_is_estimate = False
    if not isinstance(cost, (int, float)):
        if fallback_cost is not None:
            cost, cost_is_estimate = fallback_cost, True
        else:
            cost = None
    gain = (price - cost) * qty if cost is not None and qty else None
    return {
        "date": d, "qty": qty, "cost": cost, "cost_is_estimate": cost_is_estimate,
        "held_days": held_days, "is_lt": is_lt, "days_to_lt": days_to_lt, "gain": gain,
        "near_lt": (not is_lt) and days_to_lt <= near_lt_days,
    }


def latest_snapshot():
    files = sorted(glob.glob(os.path.join(SKILL_DATA_DIR, "snapshot-*.json")))
    if not files:
        sys.exit(f"No snapshot under {SKILL_DATA_DIR}. Run fetch_fundamentals.py first.")
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh), files[-1]


def run_single(snap, path, ticker, near_lt_days):
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
        status = lot_status(lot, price, today, near_lt_days, fallback_cost=stock.get("avg_cost"))
        if status is None:
            print(f"  {lot.get('date')}  qty {lot.get('qty')}  cost {lot.get('cost')}  -- "
                  f"unparseable date, cannot place on the LT/ST timeline")
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
        est = " (cost estimated from position avg, e.g. a demerger lot)" if status["cost_is_estimate"] else ""
        gain_str = f"gain {status['gain']:+,.0f}{est}" if status["gain"] is not None else "cost unknown"
        print(f"  {status['date']}  qty {status['qty']:g}  {tag} (held {status['held_days']}d)  "
              f"{gain_str}{near}")

    print(f"\nUnrealized: LT {total_lt_gain:+,.0f}, ST {total_st_gain:+,.0f}")
    if near_lt:
        print(f"{len(near_lt)} short-term lot(s) within {near_lt_days}d of turning long-term "
              f"({STCG_RATE_PCT:.1f}% -> {LTCG_RATE_PCT:.1f}% and exemption-eligible) -- "
              f"selling now vs. waiting is a real choice worth naming.")
    print(f"\nLTCG {LTCG_RATE_PCT:.1f}% above a Rs {LTCG_EXEMPTION_PER_FY:,}/FY exemption, "
          f"STCG {STCG_RATE_PCT:.1f}% flat (verify against the current Finance Act). "
          f"Run --harvest for the portfolio-wide exemption-headroom and loss-harvesting view.")


def run_harvest(snap):
    today = date.today()
    tax_position = snap.get("tax_position")
    lt_gain_lots, lt_loss_lots, st_loss_lots = [], [], []
    for stock in snap["stocks"]:
        price, lots = stock.get("price"), stock.get("lots") or []
        if price is None or not lots:
            continue
        for lot in lots:
            status = lot_status(lot, price, today, fallback_cost=stock.get("avg_cost"))
            if status is None or status["gain"] is None:
                continue
            row = {"ticker": stock["ticker"], **status}
            if status["is_lt"] and status["gain"] > 0:
                lt_gain_lots.append(row)
            elif status["is_lt"] and status["gain"] < 0:
                lt_loss_lots.append(row)
            elif not status["is_lt"] and status["gain"] < 0:
                st_loss_lots.append(row)

    print(f"Portfolio tax-lot harvest view, as of {snap.get('generated_at', 'unknown')}\n")

    if not tax_position:
        print("No Tax position data on file -- this needs a lot-level Zerodha Console export "
              "(see zerodha-portfolio-template.md), not a plain holdings CSV. Falling back to "
              "per-lot totals only, with no realised-gains baseline to size a harvest against.\n")
        headroom = None
    else:
        realised_ltcg = tax_position.get("realised_ltcg") or 0.0
        headroom = max(0.0, LTCG_EXEMPTION_PER_FY - realised_ltcg)
        print(f"{tax_position['fy']}: realised STCG {tax_position.get('realised_stcg', 0):,.0f}, "
              f"realised LTCG {realised_ltcg:,.0f}. LTCG exemption headroom this FY: "
              f"{headroom:,.0f} of {LTCG_EXEMPTION_PER_FY:,}.")
        if tax_position.get("console_harvest_savings") is not None:
            print(f"Console's own current-year loss-harvesting estimate (all realised gains, "
                  f"stocks + MFs): save up to {tax_position['console_harvest_savings']:,.0f} -- "
                  f"this is the authoritative figure for what harvesting a loss is worth *this "
                  f"year*; it will be small whenever realised gains are small, same as here "
                  f"({tax_position.get('realised_stcg', 0):,.0f} STCG + {realised_ltcg:,.0f} LTCG "
                  f"realised so far). STCL offsets STCG and LTCG; LTCL offsets LTCG only.")
        print()

    SHOWN = 15

    def print_lots(rows, shown_count, running_total=None, running_label=None):
        for row in rows[:shown_count]:
            est = " (cost estimated)" if row["cost_is_estimate"] else ""
            print(f"  {row['ticker']:<12} {row['date']}  qty {row['qty']:g}  "
                  f"gain {row['gain']:+,.0f}{est}")
        if len(rows) > shown_count:
            rest = rows[shown_count:]
            print(f"  ... {len(rest)} more lot(s) totaling {sum(r['gain'] for r in rest):+,.0f} "
                  f"not shown.")
        if running_total is not None:
            print(f"  {running_label}: {running_total:,.0f}")

    lt_gain_lots.sort(key=lambda r: -r["gain"])
    total_lt_gain_all = sum(r["gain"] for r in lt_gain_lots)
    print(f"LT gain lots ({len(lt_gain_lots)}, total {total_lt_gain_all:,.0f}) -- "
          f"tax-free to sell up to the exemption headroom:")
    if headroom is not None:
        if total_lt_gain_all <= headroom:
            print(f"  All {len(lt_gain_lots)} lots together ({total_lt_gain_all:,.0f}) fit under "
                  f"the {headroom:,.0f} headroom -- exemption isn't the binding constraint here; "
                  f"the largest below are the ones worth naming in a note.")
            print_lots(lt_gain_lots, SHOWN)
        else:
            running, picked = 0.0, []
            for row in lt_gain_lots:
                if running + row["gain"] > headroom and picked:
                    break
                picked.append(row)
                running += row["gain"]
            print_lots(picked, SHOWN, running,
                       f"Sum of this combination: {running:,.0f} of {headroom:,.0f} headroom "
                       f"(largest lots first -- not the only combination; pick lots that also "
                       f"match a rating that wants trimming)")
    else:
        print_lots(lt_gain_lots, SHOWN)

    for label, lots_ in (("LT loss lots", lt_loss_lots), ("ST loss lots", st_loss_lots)):
        lots_.sort(key=lambda r: r["gain"])
        total = sum(r["gain"] for r in lots_)
        print(f"\n{label} ({len(lots_)}), total {total:+,.0f}:")
        print_lots(lots_, SHOWN)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker", nargs="?", help="omit with --harvest")
    p.add_argument("--near-lt-days", type=int, default=60,
                    help="flag a short-term lot within this many days of turning long-term")
    p.add_argument("--harvest", action="store_true",
                    help="portfolio-wide exemption-headroom and loss-harvesting view")
    args = p.parse_args()

    snap, path = latest_snapshot()
    if args.harvest:
        run_harvest(snap)
        return
    if not args.ticker:
        sys.exit("Pass a ticker, or --harvest for the portfolio-wide view.")
    run_single(snap, path, args.ticker.upper(), args.near_lt_days)


if __name__ == "__main__":
    main()
