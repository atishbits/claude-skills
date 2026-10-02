#!/usr/bin/env python3
"""Append-only ledger of every verdict the skill gives, with enough recorded
to check later whether the call was good: the hash of the snapshot (and of the
listings capture) it was based on, the numbers it relied on, and its sources.

    python3 scripts/rating_ledger.py add --kind holding --issuer NAME --verdict HOLD|REVIEW|EXIT
        --reason "deciding sentence" [--isin ISIN] [--inputs JSON] [--source URL ...] [--root PATH]
    python3 scripts/rating_ledger.py add --kind listing --issuer NAME --verdict ENTER|SKIP
        --reason "deciding sentence" [--bond-id ID] [--inputs JSON] [--source URL ...] [--root PATH]
    python3 scripts/rating_ledger.py show [--issuer NAME] [--root PATH]

`add` fills the snapshot hash and listings checksum from the newest files, so
a verdict is always tied to the data that was actually on disk. ENTER and EXIT
need at least one source."""
import argparse
import datetime as dt
import json
import os
import sys

import common

VERDICTS = {"listing": {"ENTER", "SKIP"}, "holding": {"HOLD", "REVIEW", "EXIT"}}


def ledger_path(root):
    return os.path.join(common.skill_data_dir(root), "ratings-ledger.jsonl")


def make_entry(kind, issuer, verdict, reason, inputs, sources, snapshot_hash=None,
               listings_sha256=None, isin=None, bond_id=None, when=None):
    if kind not in VERDICTS:
        raise ValueError(f"kind must be one of {sorted(VERDICTS)}")
    verdict = verdict.upper()
    if verdict not in VERDICTS[kind]:
        raise ValueError(f"a {kind} verdict must be one of {sorted(VERDICTS[kind])}")
    if not (reason or "").strip():
        raise ValueError("a verdict needs its deciding reason")
    if kind == "holding" and not snapshot_hash:
        raise ValueError("a holding verdict needs the snapshot hash it was based on")
    if kind == "listing" and not listings_sha256:
        raise ValueError("a listing verdict needs the listings capture checksum")
    if verdict in ("ENTER", "EXIT") and not sources:
        raise ValueError(f"{verdict} needs at least one source")
    return {"at": when or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind, "issuer": issuer, "isin": isin, "bond_id": bond_id, "verdict": verdict,
            "reason": reason.strip(), "inputs": inputs or {}, "sources": list(sources or []),
            "snapshot_hash": snapshot_hash, "listings_sha256": listings_sha256}


def append(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--kind", required=True)
    add.add_argument("--issuer", required=True)
    add.add_argument("--verdict", required=True)
    add.add_argument("--reason", required=True)
    add.add_argument("--isin")
    add.add_argument("--bond-id")
    add.add_argument("--inputs", default="{}")
    add.add_argument("--source", action="append", default=[])
    add.add_argument("--root")
    show = sub.add_parser("show")
    show.add_argument("--issuer")
    show.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    path = ledger_path(root)
    if args.command == "show":
        for e in load(path):
            if not args.issuer or e["issuer"].casefold() == args.issuer.casefold():
                print(json.dumps(e, ensure_ascii=False))
        return 0
    data = common.skill_data_dir(root)
    snapshots = common.dated_files(data, "snapshot-")
    listings = common.dated_files(data, "listings-")
    try:
        entry = make_entry(
            args.kind, args.issuer, args.verdict, args.reason, json.loads(args.inputs), args.source,
            snapshot_hash=common.load_json(snapshots[-1])["snapshot_hash"] if snapshots else None,
            listings_sha256=common.load_json(listings[-1])["capture_sha256"] if listings else None,
            isin=args.isin, bond_id=args.bond_id)
    except ValueError as err:
        print(f"rating_ledger: {err}", file=sys.stderr)
        return 1
    append(path, entry)
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
