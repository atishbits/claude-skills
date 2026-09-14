#!/usr/bin/env python3
"""SBI TT buying rate conversion helper for ITR-2 foreign income and assets.

Two jobs, in this order:

1. Work out *which date's* rate the law asks for. This is the part that gets
   wrong silently -- Rule 115, Rule 128 and Schedule FA each want a different
   date, and none of them is the transaction date.
2. Convert, once someone supplies that rate.

It will never guess a rate. Run it without --rate and it tells you the date to
look up; then pass --rate, or keep the rates you have already looked up in a
JSON file in your own working folder and pass --rates.

    python3 fx.py --amount 1200 --currency USD --date 2025-11-14 --basis rule115
    python3 fx.py --amount 1200 --currency USD --date 2025-11-14 --basis rule115 \
        --rate 84.1234
    python3 fx.py --amount 5000 --currency USD --date 2025-12-31 --basis fa-closing \
        --rates ~/itr/AY2026-27/sbi-tt-rates.json

Rates file format (your folder, never the skills repo):

    {"USD": {"2025-10-31": 84.1234, "2025-12-31": 85.0100}}

Not tax advice. Confirm every rate against a published SBI TT buying rate card.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

BASES = {
    "rule115": (
        "Rule 115 - foreign income (dividend, interest, salary, capital gains)",
        "last day of the month IMMEDIATELY PRECEDING the month in which the "
        "income accrued or arose",
    ),
    "rule128": (
        "Rule 128 - foreign tax credit",
        "last day of the month IMMEDIATELY PRECEDING the month in which the "
        "foreign tax was paid or deducted",
    ),
    "fa-closing": (
        "Schedule FA - closing value",
        "31 December of the reporting calendar year",
    ),
    "fa-peak": (
        "Schedule FA - peak value",
        "the date of the peak (or 31 December, if you are applying the "
        "31-Dec rate throughout -- state the convention in the conclusions file)",
    ),
    "fa-initial": (
        "Schedule FA - initial value of investment",
        "the date the interest was acquired",
    ),
}


def _last_day_of_previous_month(d: dt.date) -> dt.date:
    return d.replace(day=1) - dt.timedelta(days=1)


def rate_date(basis: str, date: dt.date) -> dt.date:
    if basis in ("rule115", "rule128"):
        return _last_day_of_previous_month(date)
    if basis == "fa-closing":
        return dt.date(date.year, 12, 31)
    # fa-peak / fa-initial: the event's own date.
    return date


def load_rate(path: str, currency: str, on: dt.date) -> float | None:
    with open(os.path.expanduser(path)) as fh:
        table = json.load(fh)
    return table.get(currency.upper(), {}).get(on.isoformat())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Convert a foreign-currency amount at the correct "
                    "statutory SBI TT buying rate date.")
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--currency", default="USD")
    p.add_argument("--date", required=True,
                   help="the transaction/event date, YYYY-MM-DD")
    p.add_argument("--basis", required=True, choices=sorted(BASES),
                   help="which rule governs this conversion")
    p.add_argument("--rate", type=float, default=None,
                   help="SBI TT buying rate for the required date")
    p.add_argument("--rates", default=None,
                   help="JSON file of rates you have already looked up")
    args = p.parse_args(argv)

    try:
        event = dt.date.fromisoformat(args.date)
    except ValueError:
        print(f"--date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 2

    label, rule = BASES[args.basis]
    needed = rate_date(args.basis, event)

    print()
    print(f"  {label}")
    print(f"  Rule: {rule}.")
    print(f"  Event date              : {event.isoformat()}")
    print(f"  Rate date to look up    : {needed.isoformat()}")
    print(f"  Amount                  : {args.currency.upper()} {args.amount:,.2f}")

    rate = args.rate
    source = "supplied on the command line"
    if rate is None and args.rates:
        rate = load_rate(args.rates, args.currency, needed)
        source = f"read from {args.rates}"

    if rate is None:
        print()
        print(f"  No rate supplied. Look up the SBI TT BUYING rate for "
              f"{args.currency.upper()} on {needed.isoformat()},")
        print("  confirm it with the user, then re-run with --rate, or add it "
              "to your rates file:")
        print(f'      {{"{args.currency.upper()}": '
              f'{{"{needed.isoformat()}": <rate>}}}}')
        print()
        print("  No rate is guessed here, on purpose. A made-up rate is a "
              "made-up figure in the return.")
        print()
        return 1

    inr = args.amount * rate
    print(f"  SBI TT buying rate      : {rate:,.4f}  ({source})")
    print(f"  Converted               : Rs {inr:,.2f}")
    print()
    print(f"  Record in the conclusions file: {args.currency.upper()} "
          f"{args.amount:,.2f} x {rate:,.4f} (SBI TT buying, "
          f"{needed.isoformat()}) = Rs {inr:,.2f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
