#!/usr/bin/env python3
"""What changed since last time, and what the listings say about issuers
already held.

    python3 scripts/diff_snapshots.py [--root PATH]

Compares the two newest listings captures (new bonds, bonds gone, rating or
YTM changes, bonds nearly sold out, rating-action tags) and the two newest
snapshots (new and closed holdings, value changes). It also checks every held
issuer against today's listings: a listing whose rating differs from the one
recorded in bond-facts.json, or that carries a rating-action tag, is a credit
signal worth a look. An issuer can have several bonds with different ratings,
so this is a prompt to check, not a conclusion."""
import argparse
import json
import sys

import bond_facts
import common


def diff_listings(prev, cur, config):
    current = {x["key"]: x for x in cur["listings"]}
    out = {"new": [], "gone": [], "changed": []}
    if prev is None:
        out["note"] = "no earlier listings capture to compare"
    else:
        previous = {x["key"]: x for x in prev["listings"]}
        out["new"] = [{"issuer": x["issuer"], "key": k, "rating": x["rating"], "ytm": x["ytm"]}
                      for k, x in current.items() if k not in previous]
        out["gone"] = [{"issuer": x["issuer"], "key": k} for k, x in previous.items()
                       if k not in current]
        for key, now in current.items():
            before = previous.get(key)
            if before is None:
                continue
            change = {f: [before[f], now[f]] for f in ("rating", "ytm") if before[f] != now[f]}
            if change:
                out["changed"].append({"issuer": now["issuer"], "key": key, **change})
    out["nearly_sold"] = [
        {"issuer": x["issuer"], "key": x["key"], "sold_pct": x["sold_pct"],
         "units_left": x["units_left"]}
        for x in cur["listings"]
        if (x["sold_pct"] is not None and x["sold_pct"] >= config["nearly_sold_pct"])
        or (x["units_left"] is not None and x["units_left"] <= config["nearly_sold_units"])]
    out["rating_actions"] = [{"issuer": x["issuer"], "key": x["key"], "action": x["rating_action"],
                              "rating": x["rating"]}
                             for x in cur["listings"] if x["rating_action"]]
    return out


def diff_holdings(prev, cur):
    out = {"new": [], "closed": [], "value_changes": []}
    if prev is None:
        out["note"] = "no earlier snapshot to compare"
        return out
    before = {h["isin"]: h for h in prev["holdings"]}
    now = {h["isin"]: h for h in cur["holdings"]}
    out["new"] = [{"issuer": h["issuer"], "isin": i} for i, h in now.items() if i not in before]
    out["closed"] = [{"issuer": h["issuer"], "isin": i} for i, h in before.items() if i not in now]
    for isin, h in now.items():
        old = before.get(isin)
        if old and old["current_value"] != h["current_value"]:
            out["value_changes"].append({"issuer": h["issuer"], "isin": isin,
                                         "from": old["current_value"], "to": h["current_value"]})
    return out


def held_issuer_signals(listings_doc, snapshot, facts):
    signals = []
    for h in snapshot["holdings"]:
        if not (h["current_value"] or 0) > 0:
            continue
        same = [x for x in listings_doc["listings"]
                if x["issuer"].casefold() == h["issuer"].casefold()]
        if not same:
            continue
        recorded = (bond_facts.lookup(facts, isin=h["isin"]) or {}).get("rating")
        ratings = sorted({x["rating"] for x in same if x["rating"]})
        actions = sorted({x["rating_action"] for x in same if x["rating_action"]})
        if actions:
            signal = "rating action on a held issuer"
        elif recorded and ratings and recorded not in ratings:
            signal = "listing rating differs from the recorded rating"
        else:
            continue
        signals.append({"issuer": h["issuer"], "isin": h["isin"], "recorded_rating": recorded,
                        "listed_ratings": ratings, "rating_actions": actions, "signal": signal})
    return signals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    data = common.skill_data_dir(root)
    listings = [common.load_json(p) for p in common.dated_files(data, "listings-")[-2:]]
    snapshots = [common.load_json(p) for p in common.dated_files(data, "snapshot-")[-2:]]
    if not snapshots:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    result = {"holdings": diff_holdings(snapshots[-2] if len(snapshots) > 1 else None,
                                        snapshots[-1])}
    if listings:
        result["listings"] = diff_listings(listings[-2] if len(listings) > 1 else None,
                                           listings[-1], common.load_config())
        result["held_issuer_signals"] = held_issuer_signals(
            listings[-1], snapshots[-1], bond_facts.load(bond_facts.facts_path(root)))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
