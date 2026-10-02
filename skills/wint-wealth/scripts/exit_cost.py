#!/usr/bin/env python3
"""What selling a holding now would return, against holding it to maturity.

    python3 scripts/exit_cost.py ISIN [--root PATH]

The figure is an ESTIMATE and is CONDITIONAL: it assumes a buyer is found, and
it takes the portal's early-exit deduction (config.json) as a percentage of
the current value, because the portal does not state the base. Always read the
portal's own sell quote for the bond before an EXIT verdict.

Tax on the gain depends on whether the bond is listed, which the Master Report
does not say. Both cases are shown; if bond-facts.json records `listed`, the
output says which applies. A listed bond held longer than the config's holding
period is taxed at the long-term rate; everything else at the profile's slab.
With no purchase date on record the long-term rate cannot be shown, so the
slab rate is used."""
import argparse
import json
import sys

import bond_facts
import common


def estimate(holding, purchases, fact, config, profile, as_of):
    value = holding["current_value"] or 0
    pct = config["portal"]["early_exit_deduction_pct"]["value"]
    deduction = round(value * pct / 100, 2)
    proceeds = round(value - deduction, 2)
    cost = round((holding["invested"] or 0) - (holding["principal_repaid"] or 0), 2)
    gain = round(proceeds - cost, 2)
    dates = [p["date"] for p in purchases if p["isin"] == holding["isin"] and p["date"]]
    months_held = common.months_between(min(dates), as_of) if dates else None
    long_term = config["tax"]["listed_ltcg"]

    def tax(listed):
        if gain <= 0:
            return 0.0
        is_long = (listed and months_held is not None
                   and months_held > long_term["min_holding_months"])
        rate = long_term["rate_pct"] if is_long else profile["tax_slab_pct"]
        return round(gain * rate / 100, 2)

    listed_tax, unlisted_tax = tax(True), tax(False)
    return {
        "issuer": holding["issuer"], "isin": holding["isin"],
        "conditional": "Estimate only, and only if a buyer is found. Check the portal's sell "
                       "quote for this bond before deciding.",
        "current_value": value, "deduction": deduction, "proceeds_estimate": proceeds,
        "cost_remaining": cost, "gain": gain, "months_held": months_held,
        "listed": (fact or {}).get("listed"),
        "tax_if_listed": listed_tax, "tax_if_unlisted": unlisted_tax,
        "net_if_listed": round(proceeds - listed_tax, 2),
        "net_if_unlisted": round(proceeds - unlisted_tax, 2),
        "hold_to_maturity": {"maturity_date": holding["maturity_date"],
                             "upcoming_interest": holding["upcoming_interest"],
                             "upcoming_principal": holding["upcoming_principal"]},
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
