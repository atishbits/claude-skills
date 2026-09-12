#!/usr/bin/env python3
"""
Compute the advance tax due for a given installment date.

Estimated annual tax on "other sources" income is built from four buckets:
  - FD interest:   fdr_total          x fd_interest_rate  x fd_tax_pct
  - Savings interest: savings_balance x savings_interest_rate x other_tax_pct
  - Dividends:     dividends_total    x other_tax_pct                      (direct - already income, not principal)
  - House rent:    house_rent_total x (1 - house_rent_standard_deduction_pct) x other_tax_pct

The result is grossed up by surcharge and cess multipliers, then the
cumulative % due for the installment (15/45/75/100) is applied. Amount
already paid this FY (TDS credits + prior advance tax installments) is
netted off to give the amount due now, per Sec 208/211 (renumbered
424/425 under the Income Tax Act 2025):

    Advance tax due now = cum_pct x estimated annual tax - tax already paid this FY

Run `python3 compute_advance_tax.py --help` for all options.
"""
import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def resolve_cum_pct(config, installment=None, cum_pct=None):
    if cum_pct is not None:
        return cum_pct, installment or f"{int(cum_pct * 100)}%"
    if installment is None:
        raise SystemExit("Provide --installment Q1..Q4 or --cum-pct directly.")
    installment = installment.upper()
    for row in config["due_dates"]["schedule"]:
        if row["label"] == installment:
            return row["cum_pct"], f"{row['label']} (due {row['due']})"
    raise SystemExit(f"Unknown installment {installment!r}; expected one of Q1, Q2, Q3, Q4.")


def compute(person_cfg, fdr_total, savings_balance, dividends_total, house_rent_total):
    fd_tax = fdr_total * person_cfg["fd_interest_rate"] * person_cfg["fd_tax_pct"]
    savings_tax = savings_balance * person_cfg["savings_interest_rate"] * person_cfg["other_tax_pct"]
    dividend_tax = dividends_total * person_cfg["other_tax_pct"]
    house_rent_taxable = house_rent_total * (1 - person_cfg["house_rent_standard_deduction_pct"])
    house_rent_tax = house_rent_taxable * person_cfg["other_tax_pct"]

    pre_surcharge = fd_tax + savings_tax + dividend_tax + house_rent_tax
    annual_tax = pre_surcharge * person_cfg["surcharge_multiplier"] * person_cfg["cess_multiplier"]

    return {
        "fd_tax": fd_tax,
        "savings_tax": savings_tax,
        "dividend_tax": dividend_tax,
        "house_rent_taxable": house_rent_taxable,
        "house_rent_tax": house_rent_tax,
        "pre_surcharge_tax": pre_surcharge,
        "estimated_annual_tax": annual_tax,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--person", required=True, help="Key under 'people' in config.json, e.g. self or spouse")
    p.add_argument("--installment", help="Q1, Q2, Q3 or Q4 (maps to 15/45/75/100pct per config.json)")
    p.add_argument("--cum-pct", type=float, help="Override cumulative %% directly (e.g. 0.45), instead of --installment")
    p.add_argument("--fdr-total", type=float, required=True, help="Total FD principal (Rs)")
    p.add_argument("--savings-balance", type=float, required=True, help="Total savings account balance (Rs)")
    p.add_argument("--dividends-total", type=float, required=True, help="Estimated total dividend income for the FY (Rs)")
    p.add_argument("--house-rent-total", type=float, default=0.0, help="Estimated total house rent income for the FY (Rs)")
    p.add_argument("--already-paid", type=float, default=0.0, help="Tax already paid this FY: TDS credits + prior advance tax installments (Rs)")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a report")
    args = p.parse_args()

    config = load_config()
    if args.person not in config["people"]:
        raise SystemExit(f"Unknown person {args.person!r}; known: {list(config['people'])}")
    person_cfg = config["people"][args.person]

    cum_pct, cum_label = resolve_cum_pct(config, args.installment, args.cum_pct)

    breakdown = compute(
        person_cfg,
        args.fdr_total,
        args.savings_balance,
        args.dividends_total,
        args.house_rent_total,
    )
    cumulative_required = breakdown["estimated_annual_tax"] * cum_pct
    due_now = max(0.0, cumulative_required - args.already_paid)

    result = {
        "person": args.person,
        "installment": cum_label,
        "cum_pct": cum_pct,
        **breakdown,
        "cumulative_required": cumulative_required,
        "already_paid": args.already_paid,
        "due_now": due_now,
    }

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
        return

    print(f"Advance tax for {args.person} - installment {cum_label}")
    print(f"  FD interest tax:       Rs {breakdown['fd_tax']:>12,.0f}")
    print(f"  Savings interest tax:  Rs {breakdown['savings_tax']:>12,.0f}")
    print(f"  Dividend tax:          Rs {breakdown['dividend_tax']:>12,.0f}")
    print(f"  House rent tax:        Rs {breakdown['house_rent_tax']:>12,.0f}  (on Rs {breakdown['house_rent_taxable']:,.0f} taxable, after standard deduction)")
    print(f"  ---------------------------------------")
    print(f"  Estimated annual tax:  Rs {breakdown['estimated_annual_tax']:>12,.0f}  (incl. surcharge + cess)")
    print(f"  Cumulative required ({cum_pct:.0%}): Rs {cumulative_required:>12,.0f}")
    print(f"  Already paid this FY:  Rs {args.already_paid:>12,.0f}")
    print(f"  ---------------------------------------")
    print(f"  DUE NOW:               Rs {due_now:>12,.0f}")


if __name__ == "__main__":
    main()
