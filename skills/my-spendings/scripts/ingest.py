#!/usr/bin/env python3
"""Turn a statement into normalised transactions with an adapter, check it,
and merge it into the ledger without duplicates.

    python3 scripts/ingest.py --file data/raw/STATEMENT --adapter NAME [--root R] [--force]

Amounts are signed: negative is money out of the account (or spent on the card),
positive is money in. Re-ingesting a file, or one that overlaps another, adds
only the transactions not already in the ledger.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

import common
import readers

LEDGER_COLUMNS = ["txn_id", "date", "account", "amount", "description", "reference", "balance",
                  "source_file", "holder"]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _find_header(rows, wanted):
    wanted = [_norm(w) for w in wanted]
    for i, row in enumerate(rows):
        cells = [_norm(c) for c in row]
        if all(any(w == c or w in c for c in cells) for w in wanted):
            return i, cells
    raise SystemExit(f"Header row with {wanted} not found: check the adapter's header_contains.")


def _parse_table(rows, ad, addons=None):
    hi, header = _find_header(rows, ad["header_contains"])
    col = {}
    for key, name in ad["columns"].items():
        if name:
            n = _norm(name)
            matches = [i for i, c in enumerate(header) if c == n] or \
                      [i for i, c in enumerate(header) if n in c]
            if not matches:
                raise SystemExit(f"Column {name!r} not in header {header}")
            col[key] = matches[0]
    holder_re = re.compile(ad["holder_regex"]) if ad.get("holder_regex") else None
    holder, out = "", []
    for row in rows[hi + 1:]:
        get = lambda k: row[col[k]].strip() if k in col and col[k] < len(row) else ""
        try:
            date = common.parse_date(get("date"), ad.get("date_format"))
        except ValueError:
            # a row like a bare card number starts one cardholder's section
            h = holder_re.search((row[0] if row else "").strip()) if holder_re else None
            if h:
                holder = (addons or {}).get(h.groupdict().get("last4") or "", "")
            continue  # footer, blank or legend row
        if "amount" in col:
            amt = common.parse_amount(get("amount"))
            if "drcr" in col:
                flag = get("drcr").upper()
                amt = abs(amt) if flag.startswith("C") else -abs(amt)
        else:
            amt = round(common.parse_amount(get("credit")) - common.parse_amount(get("debit")), 2)
        bal = get("balance")
        out.append({"date": date, "account": ad["account"], "amount": amt,
                    "description": get("description"), "reference": get("reference"),
                    "balance": common.parse_amount(bal) if bal else None, "holder": holder})
    return out


def _parse_text(rows, ad, addons):
    line_re = re.compile(ad["line_regex"])
    holder_re = re.compile(ad["holder_regex"]) if ad.get("holder_regex") else None
    marker = ad.get("credit_marker", "Cr")
    holder, out = "", []
    for row in rows:
        line = row[0] if row else ""
        if holder_re:
            h = holder_re.search(line)
            if h:
                holder = (addons or {}).get(h.groupdict().get("last4") or "", "")
                continue
        m = line_re.search(line)
        if not m:
            continue
        try:
            date = common.parse_date(m.group("date"), ad.get("date_format"))
        except ValueError:
            continue
        v = abs(common.parse_amount(m.group("amount")))
        credit = (m.groupdict().get("drcr") or "").strip().lower() == marker.lower()
        out.append({"date": date, "account": ad["account"], "amount": v if credit else -v,
                    "description": m.group("description").strip(),
                    "reference": (m.groupdict().get("reference") or "").strip(),
                    "balance": None, "holder": holder})
    return out


def parse(rows, adapter, addons=None):
    """Normalised transactions from rows. addons maps a card's last 4 digits
    to the add-on holder's label; the primary holder's rows get ''."""
    if adapter["kind"] == "table":
        return _parse_table(rows, adapter, addons)
    if adapter["kind"] == "pdf_text":
        return _parse_text(rows, adapter, addons)
    raise SystemExit(f"Unknown adapter kind {adapter['kind']!r}")


def check_balance(txns):
    """None when opening balance + all flows = closing balance (the order of rows
    within a day does not matter); otherwise the error text."""
    if len(txns) < 2 or any(t.get("balance") is None for t in txns):
        return None
    rows = sorted(txns, key=lambda t: t["date"])   # works for newest-first statements too
    first, last = rows[0]["date"], rows[-1]["date"]
    # Rows within one day may be printed in any order, so the opening balance is
    # one of (balance - amount) on the first day and the closing one of the
    # balances on the last day.
    openings = {round(t["balance"] - t["amount"], 2) for t in rows if t["date"] == first}
    closings = {round(t["balance"], 2) for t in rows if t["date"] == last}
    flows = sum(t["amount"] for t in rows)
    if any(abs(o + flows - c) <= 0.01 for o in openings for c in closings):
        return None
    o = sorted(openings)[0]
    return (f"balance check failed: opening {o:.2f} + flows gives {o + flows:.2f}, but the "
            f"statement closes at {sorted(closings)[-1]:.2f}. A row may be missing or misread.")


def with_occurrence(txns):
    """Number identical-looking rows within one file (0, 1, ...) so two real
    identical purchases on a day stay two, and re-ingesting stays idempotent."""
    seen = {}
    out = []
    for t in txns:
        k = _key(t)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append(dict(t, _occ=n))
    return out


def _key(t):
    return "|".join([t["account"], t["date"], "%.2f" % float(t["amount"]),
                     _norm(t.get("reference")) or _norm(t.get("description"))])


def txn_id(t):
    return hashlib.sha1(f"{_key(t)}|{t.get('_occ', 0)}".encode()).hexdigest()[:16]


def load_ledger(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge(ledger_path, txns, source_file):
    rows = load_ledger(ledger_path)
    have = {r["txn_id"] for r in rows}
    added = skipped = 0
    for t in with_occurrence(txns):
        i = txn_id(t)
        if i in have:
            skipped += 1
            continue
        have.add(i)
        added += 1
        rows.append({"txn_id": i, "date": t["date"], "account": t["account"],
                     "amount": "%.2f" % float(t["amount"]), "description": t["description"],
                     "reference": t.get("reference", ""),
                     "balance": "" if t.get("balance") is None else "%.2f" % t["balance"],
                     "source_file": os.path.basename(source_file), "holder": t.get("holder", "")})
    rows.sort(key=lambda r: (r["date"], r["account"]))
    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LEDGER_COLUMNS})
    return {"added": added, "skipped": skipped}


def new_inside_coverage(ledger_path, coverage_path, txns):
    """How many of txns are new to the ledger yet dated inside dates already
    covered for their account: a sign the same account was ingested from a
    differently formatted file, which would double-count those days."""
    have = {r["txn_id"] for r in load_ledger(ledger_path)}
    cov = common.load_json(coverage_path, {})
    n = 0
    for t in with_occurrence(txns):
        if txn_id(t) in have:
            continue
        if any(a <= t["date"] <= b for a, b in cov.get(t["account"], [])):
            n += 1
    return n


def update_coverage(path, account, frm, to):
    cov = common.load_json(path, {})
    spans = sorted(cov.get(account, []) + [[frm, to]])
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    cov[account] = merged
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(cov, f, indent=1, sort_keys=True)


def _addons(accounts_path, account):
    for a in common.load_json(accounts_path, {}).get("accounts", []):
        if a.get("alias") == account:
            return {x["last4"]: x["label"] for x in a.get("addons", [])}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--adapter", required=True, help="name in data/adapters/, or a path")
    ap.add_argument("--root")
    ap.add_argument("--force", action="store_true", help="ingest even if the balance check fails")
    a = ap.parse_args()
    root = common.resolve_root(a.root)
    p = common.paths(root)
    ad_path = a.adapter if os.path.exists(a.adapter) else os.path.join(p["adapters"], a.adapter + ".json")
    adapter = common.load_json(ad_path)
    txns = parse(readers.read_rows(a.file, root), adapter, _addons(p["accounts"], adapter["account"]))
    if not txns:
        sys.exit("No transactions found: check the adapter against the file.")
    err = check_balance(txns)
    if err and not a.force:
        sys.exit(err + " Re-download the statement, or pass --force to ingest it anyway.")
    inside = new_inside_coverage(p["ledger"], p["coverage"], txns)
    res = merge(p["ledger"], txns, a.file)
    update_coverage(p["coverage"], adapter["account"], min(t["date"] for t in txns),
                    max(t["date"] for t in txns))
    res.update({"account": adapter["account"], "from": min(t["date"] for t in txns),
                "to": max(t["date"] for t in txns), "balance_check": err or "ok"})
    if inside:
        res["warning"] = (f"{inside} new rows fall on dates this account already had. If this file is "
                          "another format of a statement already ingested, they are duplicates.")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
