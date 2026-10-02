#!/usr/bin/env python3
"""Take the tax rates the advance-tax skill already keeps for a person and put
them in this skill's profile, so both skills tax the same income the same way.

    python3 scripts/tax_profile.py --tax-profile /path/to/tax-profile.json --person NAME
        [--cess 1.04] [--root PATH] [--write]

Reads `other_tax_pct` (the slab on other-sources income, which is what bond
interest is) and `surcharge_multiplier` for that person, and the cess
multiplier from the advance-tax skill's own config.json beside this skill
(or --cess). It prints:

    tax_slab_pct            slab, as a percentage
    effective_tax_rate_pct  slab x surcharge x cess: the rate bond interest and
                            slab-taxed gains actually bear
    tax_multiplier          surcharge x cess, applied to the long-term
                            capital-gains rate in exit_cost.py

With --write it sets those three in data/profile.json, records where they came
from, and leaves every other key alone. Without it nothing is written. The
tax profile itself is personal and is only ever read, from wherever the user
keeps it."""
import argparse
import datetime as dt
import json
import os
import sys

import common

ADVANCE_TAX_CONFIG = os.path.join(os.path.dirname(common.SKILL_DIR), "advance-tax", "config.json")


def effective_rates(person, cess_multiplier):
    missing = [k for k in ("other_tax_pct", "surcharge_multiplier") if k not in person]
    if missing:
        raise ValueError(f"the tax profile entry is missing {missing}")
    multiplier = person["surcharge_multiplier"] * cess_multiplier
    return {"tax_slab_pct": round(person["other_tax_pct"] * 100, 2),
            "effective_tax_rate_pct": round(person["other_tax_pct"] * 100 * multiplier, 2),
            "tax_multiplier": round(multiplier, 4)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tax-profile", required=True)
    parser.add_argument("--person", required=True)
    parser.add_argument("--cess", type=float)
    parser.add_argument("--root")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        people = common.load_json(args.tax_profile)["people"]
        if args.person not in people:
            raise ValueError(f"no {args.person!r} in the tax profile; it has {sorted(people)}")
        cess = args.cess
        if cess is None:
            cess = common.load_json(ADVANCE_TAX_CONFIG)["statutory"]["cess_multiplier"]
        rates = effective_rates(people[args.person], cess)
    except (OSError, KeyError, ValueError) as err:
        print(f"tax_profile: {err}", file=sys.stderr)
        return 1
    print(json.dumps(rates, indent=2))
    if args.write:
        root = common.resolve_root(args.root)
        path = os.path.join(root, "data", "profile.json")
        profile = common.load_json(path)
        profile.update(rates)
        profile["tax_rates_from"] = (f"advance-tax profile, person {args.person!r}, cess {cess}, "
                                     f"read {dt.date.today().isoformat()}")
        common.validate_profile(profile)
        common.write_json(path, profile)
        print(f"written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
