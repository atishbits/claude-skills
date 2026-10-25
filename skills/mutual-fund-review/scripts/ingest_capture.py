#!/usr/bin/env python3
"""Bring a portal capture (the JSON capture/capture.js saves) or a hand-made
CSV into the ledger.

    python3 scripts/ingest_capture.py --capture FILE [--root R] [--date YYYY-MM-DD] [--force]
    python3 scripts/ingest_capture.py --csv FILE --source NAME [--root R] [--date ...] [--force]

Capture JSON: {"source", "captured_at", "transactions_complete": bool,
  "holdings": [{"scheme","isin","folio"?,"plan"?,"option"?,"units","invested","current_value","nav"?}],
  "transactions": [{"scheme","isin","folio"?,"date","type"?,"amount","units","nav"?,"raw"}]}

CSV columns: kind (holding|tx), date, folio, isin, scheme, plan, option, type,
amount, units, nav, invested, current_value.

Folio numbers are replaced by folio_ref before anything is written. Prints
JSON: rows added and skipped, the reconciliation, and the snapshot path.
"""
import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter

import common
import ledger

TYPE_WORDS = {"purchase": "buy", "buy": "buy", "lumpsum": "buy", "sip": "sip",
              "redemption": "sell", "sell": "sell", "switch_in": "switch_in",
              "switch_out": "switch_out"}


def _type(word):
    w = (word or "buy").strip().lower().replace(" ", "_").replace("-", "_")
    t = TYPE_WORDS.get(w, w)
    if t not in ledger.TX_TYPES:
        raise ValueError(f"unknown transaction type {word!r}")
    return t


def _need_isin(row, what):
    isin = (row.get("isin") or "").strip().upper()
    if not isin:
        raise ValueError(f"{what} {row.get('scheme')!r} has no ISIN; the adapter or CSV must supply it")
    return isin


def _holding(row, source, date, owner):
    return {"source": source, "owner": owner, "folio_ref": common.folio_ref(row.get("folio")),
            "isin": _need_isin(row, "holding"), "scheme": row.get("scheme", ""),
            "plan": (row.get("plan") or "direct").lower(),
            "option": (row.get("option") or "growth").lower(),
            "units": common.parse_num(row.get("units")),
            "invested": common.parse_num(row.get("invested")),
            "current_value": common.parse_num(row.get("current_value")),
            "nav": common.parse_num(row.get("nav")), "as_of": date}


def _tx(row, source, owner, raw, ordinal):
    amount, units = common.parse_num(row.get("amount")), common.parse_num(row.get("units"))
    return {"date": common.parse_date(row.get("date")), "source": source, "owner": owner,
            "folio_ref": common.folio_ref(row.get("folio")),
            "isin": _need_isin(row, "transaction"), "amfi_code": "",
            "scheme": row.get("scheme", ""), "plan": (row.get("plan") or "direct").lower(),
            "option": (row.get("option") or "growth").lower(), "type": _type(row.get("type")),
            "amount": abs(amount) if amount is not None else "",
            "units": abs(units) if units is not None else "",
            "nav": common.parse_num(row.get("nav")) or "",
            "row_id": ledger.make_row_id(source, raw, ordinal)}


def _with_ordinals(raws):
    seen = Counter()
    for raw in raws:
        yield raw, seen[raw]
        seen[raw] += 1


def parse_capture(doc, owner="self", date=None):
    source = doc["source"]
    date = date or (doc.get("captured_at") or "")[:10] or dt.date.today().isoformat()
    holdings = [_holding(h, source, date, owner) for h in doc.get("holdings", [])]
    rows = doc.get("transactions", [])
    raws = [f"{r.get('isin')}|{r.get('raw') or json.dumps(r, sort_keys=True)}" for r in rows]
    tx = [_tx(r, source, owner, raw, n) for r, (raw, n) in zip(rows, _with_ordinals(raws))]
    return holdings, tx


def parse_manual_csv(path, source, owner="self", date=None):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    holdings, txrows = [], []
    for r in rows:
        kind = (r.get("kind") or "").strip().lower()
        if kind == "holding":
            holdings.append(_holding(r, source, common.parse_date(r.get("date")) or date, owner))
        elif kind == "tx":
            txrows.append(r)
        else:
            raise ValueError(f"row kind must be holding or tx, got {kind!r}")
    raws = ["|".join(r.get(k, "") for k in ("date", "folio", "isin", "type", "amount", "units"))
            for r in txrows]
    tx = [_tx(r, source, owner, raw, n) for r, (raw, n) in zip(txrows, _with_ordinals(raws))]
    return holdings, tx


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--capture")
    g.add_argument("--csv")
    ap.add_argument("--source")
    ap.add_argument("--root")
    ap.add_argument("--date")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    owner = common.load_profile(root).get("owner", "self")
    if a.capture:
        with open(a.capture) as f:
            doc = json.load(f)
        holdings, tx = parse_capture(doc, owner, a.date)
        source, complete = doc["source"], doc.get("transactions_complete", False)
    else:
        if not a.source:
            ap.error("--csv needs --source")
        holdings, tx = parse_manual_csv(a.csv, a.source, owner, a.date)
        source, complete = a.source, True
    date = a.date or dt.date.today().isoformat()
    for h in holdings:
        h["as_of"] = date
    out = ledger.ingest(root, source, holdings, tx, date, complete, force=a.force)
    if argv is None:
        print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
