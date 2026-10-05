#!/usr/bin/env python3
"""Turns a BUY into an entry plan: one purchase if the stock is not falling, or
three tranches if it is -- one now, one at a named lower level (or on a
fallback date), one only after the next result. The budget is fixed before the
first purchase, so a falling price never enlarges the bet, and the last
tranche is cancelled if the result breaks the case.

    python3 scripts/entry_plan.py TICKER --budget 50000
    python3 scripts/entry_plan.py TICKER --budget 50000 --spent-so-far 20000
    python3 scripts/entry_plan.py TICKER --target-weight-pct 3
    python3 scripts/entry_plan.py TICKER            # the saved budget, and what is left of it
    python3 scripts/entry_plan.py --list            # every saved budget

Reads the newest snapshot (a holding) or, failing that, the newest screen file
(a stock not held yet); no network call of its own. `--target-weight-pct`
sizes the budget as the gap between that share of the book and what is already
held.

The budget is written to data/skill-data/entry-budgets.json the first time it
is given, with what was invested in the stock at that moment, so a later run
needs no flag: money put in since then counts against the tranches in order,
and the plan shows what is left. `--spent-so-far` says part of a budget being
recorded now has already been bought. The fallback date counts from the day
the budget was recorded, so re-running does not push it out. Nobody can see the low in advance, so this does not try to: it spreads
the money across price levels and across the one event that carries new
information, the next result.

"Falling" has one definition here: the price is below its 200 DMA (50 DMA
where the 200 is unreliable) and at least FALLING_OFF_HIGH_PCT off its 60-day
high. The share counts for later tranches are estimates at the trigger level;
the rupee amount per tranche is what is fixed."""
import argparse
import glob
import json
import os
from datetime import date, timedelta

from calendar_notes import next_results_window

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")

BUDGETS_PATH = os.path.join(DATA_DIR, "entry-budgets.json")

FALLING_OFF_HIGH_PCT = 8.0
# A lower level is only worth waiting for if it is a real step down.
LEVEL_MIN_GAP_PCT = 3.0
FALLBACK_DAYS = 14
TRANCHES = 3


def newest(pattern, data_dir=None):
    files = sorted(glob.glob(os.path.join(data_dir or DATA_DIR, pattern)))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh)


def find_stock(ticker, snapshot, screen):
    """(record, held) for the ticker: the snapshot row if it is a holding,
    else the screen row."""
    for data, held in ((snapshot, True), (screen, False)):
        for s in (data or {}).get("stocks", []):
            if (s.get("ticker") or "").upper() == ticker.upper() and s.get("price"):
                return s, held
    return None, False


def book_value(snapshot):
    """The book at snapshot prices; the holdings file's own value where a
    price failed to load."""
    total = 0.0
    for s in (snapshot or {}).get("stocks", []):
        if s.get("qty") and s.get("price"):
            total += s["qty"] * s["price"]
        else:
            total += s.get("current_value") or 0.0
    return total


def budget_for_target(target_weight_pct, book, held_value):
    return max(0.0, book * target_weight_pct / 100.0 - held_value)


def trend(price, technicals):
    """Whether the stock is falling, and the readings that decided it."""
    t = technicals or {}
    if t.get("dma200_reliable", True) and t.get("dma200"):
        label, dma = "200 DMA", t["dma200"]
    else:
        label, dma = "50 DMA", t.get("dma50")
    high = t.get("recent_high_60d")
    below_dma = bool(dma) and price < dma
    off_high_pct = (high - price) / high * 100 if high else None
    falling = below_dma and off_high_pct is not None and off_high_pct >= FALLING_OFF_HIGH_PCT
    return {"falling": falling, "dma_label": label, "dma": dma, "below_dma": below_dma,
            "high_60d": high, "off_high_pct": off_high_pct}


def lower_level(price, technicals):
    """The nearest real level at least LEVEL_MIN_GAP_PCT below the price: the
    60-day low, else the 52-week low. None if the price is already at both."""
    t = technicals or {}
    ceiling = price * (1 - LEVEL_MIN_GAP_PCT / 100.0)
    for label, key in (("60-day low", "recent_low_60d"), ("52-week low", "close_low_1y")):
        level = t.get(key)
        if level and level <= ceiling:
            return label, level
    return None


def results_window(stock, today):
    """(start, end) of the next results window, or None when it cannot be
    estimated or has already passed (the snapshot's quarter is then behind)."""
    lqe = stock.get("latest_quarter_end")
    if not lqe:
        return None
    _, start, end = next_results_window(lqe, stock.get("fiscal_year_end"))
    return (start, end) if end >= today else None


def load_budgets(path=None):
    try:
        with open(path or BUDGETS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_budget(ticker, budget, invested_now, spent_so_far, today, path=None):
    """Record the budget with the invested amount it starts from. Money in
    the stock beyond that baseline is this plan's spend."""
    path = path or BUDGETS_PATH
    budgets = load_budgets(path)
    budgets[ticker.upper()] = {"budget": budget, "set_on": today.isoformat(),
                               "baseline_invested": max(0.0, invested_now - spent_so_far)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(budgets, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return budgets[ticker.upper()]


def spent_against(record, invested_now):
    return max(0.0, invested_now - record.get("baseline_invested", 0.0))


def plan(price, budget, technicals, window, today, spent=0.0, anchor=None):
    """The entry plan as a dict: `staged`, the `trend` readings, `remaining`,
    and a list of tranches (`when`, `amount`, `shares`, `at_price`, `done`).
    `window` is the next results window or None; `spent` is what has already
    gone in against this budget, counted against the tranches in order;
    `anchor` is the day the budget was recorded (today if new)."""
    anchor = anchor or today
    tr = trend(price, technicals)
    remaining = max(0.0, budget - spent)
    out = {"trend": tr, "staged": False, "tranches": [], "note": None,
           "spent": spent, "remaining": remaining}
    if int(budget // price) < 1:
        out["note"] = f"Budget ₹{budget:,.0f} is below one share at ₹{price:,.2f}."
        return out
    if int(remaining // price) < 1:
        out["note"] = (f"Budget used: ₹{spent:,.0f} of ₹{budget:,.0f} is in, and the "
                       f"₹{remaining:,.0f} left is below one share.")
        return out

    def single(note):
        shares = int(remaining // price)
        out["tranches"].append({"when": "now", "amount": shares * price, "shares": shares,
                                "at_price": price, "done": False})
        out["note"] = note
        return out

    if not tr["falling"]:
        return single("Not falling by this script's test: what is left goes in as a single purchase.")
    n = min(TRANCHES, int(budget // price))
    if n < 2:
        return single("Falling, but the budget buys one share: too small to stage.")

    out["staged"] = True
    slice_amount = budget / n
    # Money already in fills the tranches in order; `left[i]` is what each still needs.
    left, pool = [], spent
    for _ in range(n):
        used = min(slice_amount, pool)
        pool -= used
        left.append(slice_amount - used)

    now_shares = int(left[0] // price)
    out["tranches"].append({"when": "now", "amount": now_shares * price, "shares": now_shares,
                            "at_price": price, "done": now_shares < 1})
    result_when = ("after the next result, only if it holds the case; cancel if it does not"
                   + (f" (estimated {window[0].isoformat()} to {window[1].isoformat()}, unconfirmed)"
                      if window else " (date unknown: confirm it)"))
    if n == TRANCHES:
        fallback = anchor + timedelta(days=FALLBACK_DAYS)
        if window and window[0] > anchor:
            fallback = min(fallback, window[0] - timedelta(days=1))
        due = " -- that date has passed, so it is due now" if fallback < today else ""
        level = lower_level(price, technicals)
        if level:
            label, at = level
            when = (f"at or below ₹{at:,.2f} ({label}), or on {fallback.isoformat()} "
                    f"if it has not traded there{due}")
        else:
            at = price
            when = (f"on {fallback.isoformat()} (no real level sits {LEVEL_MIN_GAP_PCT:.0f}% "
                    f"or more below today's price){due}")
        shares = int(left[1] // at)
        out["tranches"].append({"when": when, "amount": left[1] if shares else 0.0, "shares": shares,
                                "at_price": at, "done": shares < 1})
    planned = sum(t["amount"] for t in out["tranches"])
    last = remaining - planned
    out["tranches"].append({"when": result_when, "amount": last, "shares": None,
                            "at_price": None, "done": last < price})
    return out


def render(ticker, price, budget, p):
    tr = p["trend"]
    lines = [f"{ticker} entry plan -- budget ₹{budget:,.0f} at ₹{price:,.2f}"]
    if p["spent"]:
        lines.append(f"  Already in: ₹{p['spent']:,.0f}; left to place: ₹{p['remaining']:,.0f}")
    if tr["dma"] and tr["off_high_pct"] is not None:
        lines.append(
            f"  Trend: {'below' if tr['below_dma'] else 'above'} its {tr['dma_label']} "
            f"(₹{tr['dma']:,.2f}), {tr['off_high_pct']:.1f}% off its 60-day high "
            f"(₹{tr['high_60d']:,.2f}) -> {'falling' if tr['falling'] else 'not falling'}")
    else:
        lines.append("  Trend: moving average or 60-day high unavailable -> treated as not falling")
    if p["note"]:
        lines.append(f"  {p['note']}")
    for i, t in enumerate(p["tranches"], 1):
        if t["done"]:
            size = "done, covered by what is already in"
        elif t["shares"] is None:
            size = f"about ₹{t['amount']:,.0f}, share count at the price then"
        elif t["when"] == "now":
            size = f"{t['shares']} shares, ₹{t['amount']:,.0f}"
        else:
            size = f"about ₹{t['amount']:,.0f}, roughly {t['shares']} shares"
        lines.append(f"  {i}. {t['when'][0].upper() + t['when'][1:]}: {size}")
    if p["staged"]:
        lines.append("  The total is fixed: a lower price changes the share count, never the rupees. "
                     "If the case breaks at any point, the unspent tranches are cancelled.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticker", nargs="?")
    size = ap.add_mutually_exclusive_group()
    size.add_argument("--budget", type=float, help="total rupees for this entry; saved for later runs")
    size.add_argument("--target-weight-pct", type=float,
                      help="build the position to this share of the book; saved as a rupee budget")
    ap.add_argument("--spent-so-far", type=float, default=0.0,
                    help="with --budget: rupees of it already invested")
    ap.add_argument("--list", action="store_true", help="print every saved budget")
    args = ap.parse_args()

    if args.list:
        budgets = load_budgets()
        if not budgets:
            print("No entry budgets saved yet.")
        for t, r in sorted(budgets.items()):
            print(f"{t}: budget ₹{r['budget']:,.0f}, set {r['set_on']}")
        return
    if not args.ticker:
        ap.error("a ticker is required unless --list is given")
    ticker = args.ticker.upper()

    snapshot = newest("snapshot-*.json")
    stock, held = find_stock(ticker, snapshot, newest("screen-*.json"))
    if not stock:
        raise SystemExit(f"No price for {ticker} in the newest snapshot or screen file -- "
                         f"run fetch_fundamentals.py (or --screen) for it first.")
    price = stock["price"]
    invested_now = (stock.get("invested") or (stock.get("qty") or 0) * (stock.get("avg_cost") or 0)) if held else 0.0
    today = date.today()

    if args.budget is not None:
        record = save_budget(ticker, args.budget, invested_now, args.spent_so_far, today)
    elif args.target_weight_pct is not None:
        book = book_value(snapshot)
        if not book:
            raise SystemExit("No snapshot to size a target weight against -- pass --budget instead.")
        held_value = (stock.get("qty") or 0) * price if held else 0.0
        budget = budget_for_target(args.target_weight_pct, book, held_value)
        print(f"Book ₹{book:,.0f}; {args.target_weight_pct:g}% is ₹{book * args.target_weight_pct / 100:,.0f}; "
              f"held ₹{held_value:,.0f}; budget ₹{budget:,.0f}")
        if budget <= 0:
            raise SystemExit("Already at or above that weight -- nothing to buy.")
        record = save_budget(ticker, budget, invested_now, 0.0, today)
    else:
        record = load_budgets().get(ticker)
        if not record:
            raise SystemExit(f"No budget saved for {ticker} -- ask the user for one and pass --budget "
                             f"(or --target-weight-pct). Do not assume a figure.")
    budget = record["budget"]
    anchor = date.fromisoformat(record["set_on"])
    p = plan(price, budget, stock.get("technicals"), results_window(stock, today), today,
             spent=spent_against(record, invested_now), anchor=anchor)
    print(f"Budget recorded {record['set_on']} in {os.path.basename(BUDGETS_PATH)}.")
    print(render(ticker, price, budget, p))


if __name__ == "__main__":
    main()
