#!/usr/bin/env python3
"""Facts about each fund held, keyed by ISIN: AMFI code, SEBI category,
benchmark, expense ratio (dated, with the TER basis), exit load, lock-in,
plan option and tax class. Claude fills gaps from the fund house's and AMFI's
pages and records them here with a date and source; scripts only read them.

    python3 scripts/fund_meta.py set ISIN --category small_cap --benchmark_key small_cap \
        --expense_ratio_pct 0.52 --er_as_of 2026-10-25 --er_source "fund page" [--root R]
    python3 scripts/fund_meta.py show [ISIN] [--root R]
    python3 scripts/fund_meta.py missing [--root R]

Benchmark keys and their tax classes are in references/benchmarks.json. The
expense-ratio basis matters: from April 2026 SEBI splits TER into a base ratio
plus levies, so a pre-April figure is not comparable with a post-April one.
"""
import argparse
import json
import sys

import common
import ledger

TAX_CLASSES = {"equity", "specified_debt", "hybrid_gold_intl"}
NUM_FIELDS = {"expense_ratio_pct", "exit_load_pct", "exit_load_days", "lock_in_days"}
ALLOWED = {"amfi_code", "scheme", "category", "benchmark_key", "expense_ratio_pct", "er_as_of",
           "er_basis", "er_source", "exit_load_pct", "exit_load_days", "lock_in_days", "option",
           "tax_class"}
NEEDED = ("amfi_code", "category", "benchmark_key", "expense_ratio_pct")


def load(root):
    try:
        with open(common.paths(root)["fund_meta"]) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(root, meta):
    common.write_json(common.paths(root)["fund_meta"], meta)


def set_fields(meta, isin, **fields):
    bad = set(fields) - ALLOWED
    if bad:
        raise ValueError(f"unknown field(s) {sorted(bad)}")
    benches = common.load_benchmarks()
    if "benchmark_key" in fields and fields["benchmark_key"] not in benches:
        raise ValueError(f"benchmark_key {fields['benchmark_key']!r} not in references/benchmarks.json")
    if fields.get("er_basis") not in (None, "pre_2026_04", "post_2026_04"):
        raise ValueError("er_basis must be pre_2026_04 or post_2026_04")
    if fields.get("tax_class") not in (None, *TAX_CLASSES):
        raise ValueError(f"tax_class must be one of {sorted(TAX_CLASSES)}")
    if fields.get("option") not in (None, "growth", "idcw"):
        raise ValueError("option must be growth or idcw")
    row = meta.setdefault(isin, {})
    for k, v in fields.items():
        row[k] = float(v) if k in NUM_FIELDS and v is not None else v
    if "tax_class" not in fields and row.get("benchmark_key"):
        row["tax_class"] = benches[row["benchmark_key"]]["tax_class"]
    return meta


def benchmark_for(row):
    key = row.get("benchmark_key")
    if not key:
        return None
    b = dict(common.load_benchmarks()[key])
    if row.get("option") == "idcw":
        b["note"] = (b.get("note", "") + "; " if b.get("note") else "") + \
            "growth proxy used for IDCW plan: payouts count as cash returned"
    return b


def missing(root):
    snap_path = ledger.latest_snapshot(root)
    if not snap_path:
        return []
    with open(snap_path) as f:
        holdings = json.load(f).get("holdings", [])
    meta = load(root)
    out, seen = [], set()
    for h in holdings:
        if h["isin"] in seen:
            continue
        seen.add(h["isin"])
        row = meta.get(h["isin"], {})
        gaps = [k for k in NEEDED if row.get(k) in (None, "")]
        if gaps:
            out.append({"isin": h["isin"], "scheme": h.get("scheme", ""), "fields": gaps})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("isin")
    for k in sorted(ALLOWED):
        s.add_argument(f"--{k}")
    sh = sub.add_parser("show")
    sh.add_argument("isin", nargs="?")
    m = sub.add_parser("missing")
    for p in (s, sh, m):
        p.add_argument("--root")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    if a.cmd == "set":
        meta = load(root)
        fields = {k: getattr(a, k) for k in ALLOWED if getattr(a, k) is not None}
        set_fields(meta, a.isin.upper(), **fields)
        save(root, meta)
        out = meta[a.isin.upper()]
    elif a.cmd == "show":
        meta = load(root)
        out = meta.get(a.isin.upper(), {}) if a.isin else meta
    else:
        out = missing(root)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
