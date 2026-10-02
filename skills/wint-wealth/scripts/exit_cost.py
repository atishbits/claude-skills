#!/usr/bin/env python3
"""What selling a holding now would return, against holding it to maturity.

    python3 scripts/exit_cost.py ISIN [--root PATH]

The figure is an ESTIMATE and is CONDITIONAL: it assumes a buyer is found, and
it takes the portal's early-exit deduction (config.json) as a percentage of
the current value, because the portal does not state the base. Always read the
portal's own sell quote for the bond before an EXIT verdict.

Tax on the gain depends on whether the bond is listed, which the Master Report
does not say. Both cases are shown; if bond-facts.json records `listed`, the
output says which applies. Each purchase lot still held is taxed on its own
holding period (units already sold come off the earliest lots first): a lot of
a listed bond held longer than the config's holding period at the long-term
rate, everything else at the profile's tax rate (effective_tax_rate_pct if
set, else the slab). With no purchase date on record the long-term rate cannot
be shown, so the slab rate is used."""
import argparse
import json
import sys

import bond_facts
import common


def _remaining_lots(holding, purchases):
    """Purchase lots still held, oldest first. If more units were bought than
    are held now, the units sold come off the earliest lots (first in, first
    out). A lot with no unit count is given one unit, so lots weigh equally."""
    lots = sorted(({"date": p["date"], "units": p.get("units") or 1.0} for p in purchases
                   if p["isin"] == holding["isin"] and p["date"]), key=lambda lot: lot["date"])
    excess = sum(lot["units"] for lot in lots) - (holding.get("units") or 0)
    if holding.get("units") and excess > 0:
        for lot in lots:
            taken = min(lot["units"], excess)
            lot["units"] -= taken
            excess -= taken
        lots = [lot for lot in lots if lot["units"] > 0]
    return lots


def estimate(holding, purchases, fact, config, profile, as_of):
    value = holding["current_value"] or 0
    pct = config["portal"]["early_exit_deduction_pct"]["value"]
    deduction = round(value * pct / 100, 2)
    proceeds = round(value - deduction, 2)
    cost = round((holding["invested"] or 0) - (holding["principal_repaid"] or 0), 2)
    gain = round(proceeds - cost, 2)
    lots = _remaining_lots(holding, purchases)
    months_held = (common.months_between(lots[0]["date"], as_of) if lots else None)
    long_term = config["tax"]["listed_ltcg"]
    slab = common.tax_rate(profile)
    multiplier = profile.get("tax_multiplier", 1)  # surcharge and cess on the long-term rate
    units = sum(lot["units"] for lot in lots)
    for lot in lots:
        lot["months_held"] = common.months_between(lot["date"], as_of)
        lot["long_term_if_listed"] = lot["months_held"] > long_term["min_holding_months"]

    def tax(listed):
        if gain <= 0:
            return 0.0
        if not lots:  # no purchase date on record: the long-term rate cannot be shown
            return round(gain * slab / 100, 2)
        return round(sum(
            gain * lot["units"] / units
            * (long_term["rate_pct"] * multiplier
               if listed and lot["long_term_if_listed"] else slab) / 100
            for lot in lots), 2)

    listed_tax, unlisted_tax = tax(True), tax(False)
    return {
        "issuer": holding["issuer"], "isin": holding["isin"],
        "conditional": "Estimate only, and only if a buyer is found. Check the portal's sell "
                       "quote for this bond before deciding.",
        "current_value": value, "deduction": deduction, "proceeds_estimate": proceeds,
        "cost_remaining": cost, "gain": gain, "months_held": months_held, "lots": lots,
        "tax_basis": "The gain is spread across the lots still held in proportion to their "
                     "units, and each lot is taxed on its own holding period.",
        "listed": (fact or {}).get("listed"),
        "tax_if_listed": listed_tax, "tax_if_unlisted": unlisted_tax,
        "net_if_listed": round(proceeds - listed_tax, 2),
        "net_if_unlisted": round(proceeds - unlisted_tax, 2),
        "hold_to_maturity": {"maturity_date": holding["maturity_date"],
                             "upcoming_interest": holding["upcoming_interest"],
                             "upcoming_principal": holding["upcoming_principal"]},
        "config_warnings": common.stale_config_warnings(config, as_of),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("isin")
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    snapshots = common.dated_files(common.skill_data_dir(root), "snapshot-")
    if not snapshots:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    snapshot = common.load_json(snapshots[-1])
    holding = next((h for h in snapshot["holdings"] if h["isin"] == args.isin), None)
    if holding is None:
        print(f"{args.isin} is not in the newest snapshot's holdings.", file=sys.stderr)
        return 1
    try:
        profile = common.load_profile(root)
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        return 1
    fact = bond_facts.lookup(bond_facts.load(bond_facts.facts_path(root)), isin=args.isin)
    print(json.dumps(estimate(holding, snapshot["purchases"], fact, common.load_config(), profile,
                              snapshot["as_of"]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
