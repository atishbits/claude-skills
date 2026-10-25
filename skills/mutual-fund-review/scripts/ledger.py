#!/usr/bin/env python3
"""The normalised transaction ledger every ingest script writes to and every
analysis script reads: one CSV of transactions, plus dated holdings snapshots
with a unit reconciliation (do the transactions add up to what the source says
is held?).

A row's identity is its `row_id`, built by the ingest script from the raw row
text and its position among identical raw rows. Two genuinely identical
purchases on one day therefore stay two rows, and re-ingesting the same file
adds nothing.
"""
import csv
import hashlib
import os
from collections import defaultdict

import common

TX_FIELDS = ["date", "source", "owner", "folio_ref", "isin", "amfi_code", "scheme", "plan",
             "option", "type", "amount", "units", "nav", "row_id"]
TX_TYPES = {"buy", "sip", "sell", "switch_in", "switch_out", "dividend_payout",
            "dividend_reinvest", "stamp", "stt"}
UNITS_IN = {"buy", "sip", "switch_in", "dividend_reinvest"}
UNITS_OUT = {"sell", "switch_out"}
UNIT_TOLERANCE = 0.001
NUMERIC = ("amount", "units", "nav")


def make_row_id(source, raw, ordinal):
    digest = hashlib.sha256(f"{raw}#{ordinal}".encode()).hexdigest()[:16]
    return f"{source}:{digest}"


def _clean(row):
    if row.get("type") not in TX_TYPES:
        raise ValueError(f"unknown transaction type {row.get('type')!r}")
    out = {k: row.get(k, "") for k in TX_FIELDS}
    for k in NUMERIC:
        v = out[k]
        out[k] = float(v) if v not in ("", None) else ""
    if not out["row_id"]:
        raise ValueError("row without row_id")
    return out


def read_transactions(path):
    try:
        with open(path, newline="") as f:
            return [_clean(r) for r in csv.DictReader(f)]
    except FileNotFoundError:
        return []


def write_transactions(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TX_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TX_FIELDS})
    os.replace(tmp, path)


def merge(existing, new):
    seen = {r["row_id"] for r in existing}
    out = [_clean(r) for r in existing]
    added = skipped = 0
    for r in new:
        r = _clean(r)
        if r["row_id"] in seen:
            skipped += 1
            continue
        seen.add(r["row_id"])
        out.append(r)
        added += 1
    out.sort(key=lambda r: (r["date"], r["source"], r["isin"]))
    return out, {"added": added, "skipped": skipped}


def units_by_holding(rows):
    held = defaultdict(float)
    for r in rows:
        key = (r["source"], r["folio_ref"] or None, r["isin"])
        if r["type"] in UNITS_IN:
            held[key] += float(r["units"] or 0)
        elif r["type"] in UNITS_OUT:
            held[key] -= abs(float(r["units"] or 0))
    return dict(held)


def _net_amount(rows):
    amt = defaultdict(float)
    for r in rows:
        key = (r["source"], r["folio_ref"] or None, r["isin"])
        if r["type"] in {"buy", "sip", "switch_in"}:
            amt[key] += float(r["amount"] or 0)
        elif r["type"] in UNITS_OUT:
            amt[key] -= abs(float(r["amount"] or 0))
    return amt


def reconcile(rows, holdings):
    """One line per holding. A holding with no folio_ref matches transactions
    of that source and ISIN in any folio."""
    units = units_by_holding(rows)
    amounts = _net_amount(rows)

    def total(table, h):
        if h.get("folio_ref"):
            return table.get((h["source"], h["folio_ref"], h["isin"]), 0.0)
        return sum(v for (s, _f, i), v in table.items() if s == h["source"] and i == h["isin"])

    out = []
    for h in holdings:
        tx_units = round(total(units, h), 6)
        held = float(h["units"])
        inv = h.get("invested")
        out.append({
            "source": h["source"], "folio_ref": h.get("folio_ref"), "isin": h["isin"],
            "scheme": h.get("scheme", ""), "tx_units": tx_units, "held_units": held,
            "units_ok": abs(tx_units - held) <= UNIT_TOLERANCE,
            "amount_gap_inr": (round(float(inv) - total(amounts, h), 2)
                               if inv not in (None, "") else None),
        })
    return out


def write_snapshot(root, date, holdings, recon, sources, force=False):
    bad = [r for r in recon if not r["units_ok"]]
    if bad and not force:
        raise ValueError(f"{len(bad)} holding(s) do not reconcile with their transactions: "
                         + ", ".join(r.get("scheme") or r["isin"] for r in bad))
    path = os.path.join(common.paths(root)["skill_data"], f"snapshot-{date}.json")
    common.write_json(path, {"date": date, "sources": sources, "holdings": holdings,
                             "reconciliation": recon})
    return path


def latest_snapshot(root):
    sd = common.paths(root)["skill_data"]
    try:
        names = sorted(n for n in os.listdir(sd) if n.startswith("snapshot-") and n.endswith(".json"))
    except FileNotFoundError:
        return None
    return os.path.join(sd, names[-1]) if names else None


def ingest(root, source, holdings, tx, date, transactions_complete, force=False,
           supersede=False):
    """Merge one source's rows into the ledger and write a new snapshot that
    keeps every other source's newest holdings. Nothing is written when the
    source's holdings do not reconcile, unless force. With supersede (a
    statement that carries full history), another source's holding of the same
    folio and ISIN is dropped from the snapshot; its transactions stay in the
    ledger but no holding refers to them, so analysis ignores them."""
    p = common.paths(root)
    existing = read_transactions(p["transactions"])
    merged, stats = merge(existing, tx)
    recon = reconcile([r for r in merged if r["source"] == source], holdings)
    if not force and not all(r["units_ok"] for r in recon):
        bad = [r.get("scheme") or r["isin"] for r in recon if not r["units_ok"]]
        raise ValueError(f"{source}: holdings do not reconcile with transactions: {bad}. "
                         "Re-capture, or pass --force to record them flagged.")
    prev_path = latest_snapshot(root)
    prev = {"holdings": [], "sources": {}, "reconciliation": []}
    if prev_path:
        import json
        with open(prev_path) as f:
            prev = json.load(f)
    def same(a, b):
        if a.get("isin") != b.get("isin"):
            return False
        return not (a.get("folio_ref") and b.get("folio_ref")) or a["folio_ref"] == b["folio_ref"]

    def kept(row):
        if row["source"] == source:
            return False
        return not (supersede and any(same(row, h) for h in holdings))

    keep = [h for h in prev.get("holdings", []) if kept(h)]
    keep_recon = [r for r in prev.get("reconciliation", []) if kept(r)]
    sources = {k: v for k, v in prev.get("sources", {}).items() if k != source}
    sources[source] = {"holdings_as_of": date, "transactions_complete": bool(transactions_complete)}
    write_transactions(p["transactions"], merged)
    snap = write_snapshot(root, date, keep + holdings, keep_recon + recon, sources, force=True)
    return {**stats, "reconciliation": recon, "snapshot": snap}
