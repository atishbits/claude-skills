#!/usr/bin/env python3
"""Per-bond credit facts the Master Report and the listings page do not carry:
rating and agency, rating action and outlook, secured or not, seniority,
collateral, issuer type, listed or not. Each entry records where it came from
and when, so a verdict can be traced back to a source.

    python3 scripts/bond_facts.py set --isin ISIN [--bond-id ID] --source URL
        [--issuer NAME] [--rating R] [--agency A] [--rating-action X] [--outlook X]
        [--secured yes|no] [--seniority senior|subordinated] [--collateral TEXT]
        [--issuer-type TEXT] [--listed yes|no] [--as-of YYYY-MM-DD] [--root PATH]
    python3 scripts/bond_facts.py get (--isin ISIN | --bond-id ID) [--root PATH]

This script is the only writer of data/skill-data/bond-facts.json."""
import argparse
import datetime as dt
import json
import os
import sys

import common

FIELDS = ["issuer", "rating", "agency", "rating_action", "outlook", "secured", "seniority",
          "collateral", "issuer_type", "listed", "source", "as_of"]


def facts_path(root):
    return os.path.join(common.skill_data_dir(root), "bond-facts.json")


def load(path):
    return common.load_json(path)["facts"] if os.path.exists(path) else []


def save(path, facts):
    common.write_json(path, {"facts": facts})


def lookup(facts, isin=None, bond_id=None):
    for entry in facts:
        if isin and entry.get("isin") == isin:
            return entry
        if bond_id and entry.get("wint_bond_id") == str(bond_id):
            return entry
    return None


def upsert(facts, isin=None, bond_id=None, **fields):
    if not isin and not bond_id:
        raise ValueError("a fact needs an ISIN or a Wint bond id")
    unknown = [k for k in fields if k not in FIELDS]
    if unknown:
        raise ValueError(f"unknown fact field(s): {unknown}")
    if not fields.get("source") or not fields.get("as_of"):
        raise ValueError("a fact needs a source and an as_of date")
    if fields.get("seniority") not in (None, "senior", "subordinated"):
        raise ValueError("seniority must be 'senior' or 'subordinated'")
    for flag in ("secured", "listed"):
        if fields.get(flag) is not None and not isinstance(fields[flag], bool):
            raise ValueError(f"{flag} must be true or false")
    entry = lookup(facts, isin=isin, bond_id=bond_id)
    if entry is None:
        entry = {"isin": None, "wint_bond_id": None, **{k: None for k in FIELDS}}
        facts.append(entry)
    if isin:
        entry["isin"] = isin
    if bond_id:
        entry["wint_bond_id"] = str(bond_id)
    entry.update({k: v for k, v in fields.items() if v is not None})
    return entry


def _yes_no(text):
    return None if text is None else text == "yes"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    setter = sub.add_parser("set")
    getter = sub.add_parser("get")
    for p in (setter, getter):
        p.add_argument("--isin")
        p.add_argument("--bond-id")
        p.add_argument("--root")
    for name in ("issuer", "rating", "agency", "rating-action", "outlook",
                 "collateral", "issuer-type", "source", "as-of"):
        setter.add_argument(f"--{name}")
    setter.add_argument("--seniority", choices=["senior", "subordinated"])
    setter.add_argument("--secured", choices=["yes", "no"])
    setter.add_argument("--listed", choices=["yes", "no"])
    args = parser.parse_args(argv)
    path = facts_path(common.resolve_root(args.root))
    facts = load(path)
    if args.command == "get":
        print(json.dumps(lookup(facts, isin=args.isin, bond_id=args.bond_id), indent=2))
        return 0
    try:
        entry = upsert(
            facts, isin=args.isin, bond_id=args.bond_id, issuer=args.issuer, rating=args.rating,
            agency=args.agency, rating_action=args.rating_action, outlook=args.outlook,
            secured=_yes_no(args.secured), seniority=args.seniority, collateral=args.collateral,
            issuer_type=args.issuer_type, listed=_yes_no(args.listed), source=args.source,
            as_of=args.as_of or dt.date.today().isoformat())
    except ValueError as err:
        print(f"bond_facts: {err}", file=sys.stderr)
        return 1
    save(path, facts)
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
