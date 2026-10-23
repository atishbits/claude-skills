#!/usr/bin/env python3
"""Append-only log of equity sales the user reports, with FY realised-gain totals.

    python3 scripts/gains_log.py record TICKER QTY PRICE --date YYYY-MM-DD --account NAME [--charges N]
    python3 scripts/gains_log.py report [--fy 2026-27]
    python3 scripts/gains_log.py export [--fy 2026-27]
    python3 scripts/gains_log.py reconcile PATH

Each sale is matched FIFO against the newest snapshot's lots in that demat
account (tax_lots.py), after skipping units already logged as sold since that
account's own export date (the snapshot's `exports` block; older snapshots
without it fall back to the single holdings_date). A sale on or before that
date is refused: the export already reflects it. A sale is "in the broker
baseline" only when its account's export carries a tax position for that FY
and the sale is dated on or before that export. Account labels are compared
stripped and lower-cased. The log is a folder of per-writer-per-day files
(logdir.py). A later `kind: "confirm"` record (ref = a sale id) is folded over
the sale by `fold`. `export` writes a hand-off file other sessions can read.
`--charges` is the deductible sale expenses (brokerage, exchange charges, GST on
them; exclude STT). They reduce the gain, split pro rata by quantity across the
matched taxable lots before the short/long-term split.
The skill only records sales the user reports or the broker report contains.
"""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone

import logdir
import tax_lots

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
SKILL_DATA_DIR = os.path.join(ROOT, "data", "skill-data")
LOG_DIR = os.path.join(SKILL_DATA_DIR, "realised-gains")

# A broker gain may differ from the logged one by this much before it is a mismatch.
GAIN_TOLERANCE_PCT = 1.0
GAIN_TOLERANCE_ABS = 10.0

BASELINE_NOTE = "broker FY total to as_of; includes mutual funds where the broker reports them"


def fy_of(d):
    """Indian financial year of a date, e.g. date(2027, 3, 31) -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _norm_fy(label):
    label = (label or "").strip()
    return label[3:].strip() if label.upper().startswith("FY ") else label


def norm_account(label):
    return (label or "").strip().lower()


def read_entries(log_dir=None):
    return logdir.read(log_dir or LOG_DIR)


def _skill_data_dir(log_dir=None):
    return os.path.dirname(log_dir) if log_dir else SKILL_DATA_DIR


def fold(entries):
    """Sales with any confirm records applied (later records win), in log order."""
    sales, order = {}, []
    for e in entries:
        if e.get("kind") == "sale":
            if e["id"] not in sales:
                order.append(e["id"])
            sales[e["id"]] = dict(e)
    for e in entries:
        if e.get("kind") == "confirm" and e.get("ref") in sales:
            patch = {k: v for k, v in e.items() if k not in ("kind", "ref", "recorded_at")}
            patch.setdefault("status", "confirmed")
            sales[e["ref"]].update(patch)
    return [sales[i] for i in order]


def _snapshot(log_dir=None):
    try:
        return tax_lots.latest_snapshot(_skill_data_dir(log_dir) if log_dir else None)[0]
    except SystemExit:
        return None


def export_date(snapshot, account):
    """The ISO date of `account`'s own export; the snapshot-wide holdings_date
    for an older snapshot without `exports` or an account it does not list."""
    info = ((snapshot or {}).get("exports") or {}).get(norm_account(account))
    return (info or {}).get("date") or (snapshot or {}).get("holdings_date")


def baselines(snapshot, fy):
    """account -> {as_of, stcg, ltcg} for every export with a tax position for
    `fy`. An older snapshot without `exports` gives one baseline under "*"
    that covers every account."""
    snapshot = snapshot or {}
    out = {}
    exports = snapshot.get("exports")
    if exports is None:
        tp = snapshot.get("tax_position")
        if tp and _norm_fy(tp.get("fy")) == fy:
            out["*"] = {"as_of": snapshot["holdings_date"], "stcg": tp.get("realised_stcg") or 0.0,
                        "ltcg": tp.get("realised_ltcg") or 0.0}
        return out
    for account, info in exports.items():
        tp = (info or {}).get("tax_position")
        if tp and _norm_fy(tp.get("fy")) == fy:
            out[norm_account(account)] = {"as_of": info["date"],
                                          "stcg": tp.get("realised_stcg") or 0.0,
                                          "ltcg": tp.get("realised_ltcg") or 0.0}
    return out


def in_baseline(sale, base):
    """True when `sale` is already inside its account's broker baseline."""
    b = base.get(norm_account(sale.get("account"))) or base.get("*")
    return bool(b) and sale["sell_date"] <= b["as_of"]


def logged_since_export(ticker, account, snapshot=None, entries=None, log_dir=None):
    """Quantity of `ticker` logged as sold from `account` after that account's
    export date: units the export still shows but that are already gone."""
    snapshot = snapshot if snapshot is not None else _snapshot(log_dir)
    entries = entries if entries is not None else read_entries(log_dir)
    since = export_date(snapshot, account) or ""
    ticker, account = ticker.strip().upper(), norm_account(account)
    return sum(e.get("qty") or 0 for e in fold(entries)
               if e.get("ticker") == ticker and norm_account(e.get("account")) == account
               and e.get("sell_date", "") > since)


def _new_id(sell_date, ticker, entries, root):
    prefix = f"{sell_date}-{ticker}-{logdir.writer_id(root)}-"
    n = sum(1 for e in entries if e.get("kind") == "sale" and str(e.get("id", "")).startswith(prefix))
    return f"{prefix}{n + 1}"


def record(ticker, qty, price, sell_date, account, charges=0.0, snapshot=None, entries=None,
           log_dir=None):
    ticker = ticker.strip().upper()
    account = norm_account(account)
    qty, price = float(qty), float(price)
    if qty <= 0 or price <= 0:
        raise ValueError("qty and price must be positive")
    date.fromisoformat(sell_date)
    snapshot = snapshot if snapshot is not None else _snapshot(log_dir)
    if snapshot is None:
        raise ValueError("no snapshot on file; run fetch_fundamentals.py first")
    stock = next((s for s in snapshot["stocks"] if s["ticker"] == ticker), None)
    if stock is None:
        raise ValueError(f"{ticker} not in the snapshot")
    entries = entries if entries is not None else read_entries(log_dir)
    since = export_date(snapshot, account)
    already = logged_since_export(ticker, account, snapshot, entries)
    matched = tax_lots.fifo_match(stock.get("lots") or [], qty, account, already_sold=already,
                                  fallback_cost=stock.get("avg_cost"))
    sd = date.fromisoformat(sell_date)
    if sd <= date.fromisoformat(since):
        raise ValueError(f"{sell_date} is on or before the broker export ({since}): that sale is "
                         "already in the export; reconcile imports those")
    t = tax_lots.sale_tax(matched, price, sd)
    taxable = [m for m in matched if m.get("taxable") and m.get("cost") is not None
               and tax_lots._parse_date(m.get("date"))]
    tq = sum(m["qty"] for m in taxable)
    if charges and tq:
        for m in taxable:
            share = float(charges) * m["qty"] / tq
            if tax_lots.is_long_term(tax_lots._parse_date(m["date"]), sd):
                t["ltcg"] -= share
            else:
                t["stcg"] -= share
        t["est_tax"] = (tax_lots.LTCG_RATE_PCT / 100 * max(0.0, t["ltcg"])
                        + tax_lots.STCG_RATE_PCT / 100 * max(0.0, t["stcg"]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec = {"kind": "sale", "id": _new_id(sell_date, ticker, entries, ROOT), "ticker": ticker,
           "account": account, "sell_date": sell_date, "qty": qty, "price": price,
           "charges": float(charges), "lots": matched, "stcg": t["stcg"], "ltcg": t["ltcg"],
           "untaxed_qty": t["untaxed_qty"], "est_tax": t["est_tax"], "status": "unconfirmed",
           "source": "user", "recorded_at": now}
    logdir.append(log_dir or LOG_DIR, rec, ROOT, sell_date)
    return rec


def fy_running(fy, entries=None, snapshot=None, log_dir=None):
    """FY totals: the sum of every account's broker baseline for `fy`, plus each
    logged sale not already inside its own account's baseline. `baseline` is
    None when no account has one; otherwise {as_of (the oldest), stcg, ltcg,
    accounts: {account: {as_of, stcg, ltcg}}}."""
    entries = entries if entries is not None else read_entries(log_dir)
    snapshot = snapshot if snapshot is not None else _snapshot(log_dir)
    base = baselines(snapshot, fy)
    baseline = None
    if base:
        baseline = {"as_of": min(b["as_of"] for b in base.values()),
                    "stcg": sum(b["stcg"] for b in base.values()),
                    "ltcg": sum(b["ltcg"] for b in base.values()),
                    "accounts": base}
    stcg = baseline["stcg"] if baseline else 0.0
    ltcg = baseline["ltcg"] if baseline else 0.0
    unconfirmed = 0
    for s in fold(entries):
        if fy_of(date.fromisoformat(s["sell_date"])) != fy:
            continue
        if in_baseline(s, base):
            continue
        stcg += s["stcg"]
        ltcg += s["ltcg"]
        unconfirmed += s.get("status") == "unconfirmed"
    return {"baseline": baseline, "stcg": stcg, "ltcg": ltcg,
            "fy_tax": tax_lots.fy_tax(stcg, ltcg), "unconfirmed": unconfirmed}


def export(fy, log_dir=None):
    entries, snapshot = read_entries(log_dir), _snapshot(log_dir)
    run = fy_running(fy, entries, snapshot)
    baseline = dict(run["baseline"], note=BASELINE_NOTE) if run["baseline"] else None
    base = run["baseline"]["accounts"] if run["baseline"] else {}
    sales = [{"date": s["sell_date"], "ticker": s["ticker"], "account": s["account"],
              "qty": s["qty"], "stcg": s["stcg"], "ltcg": s["ltcg"], "status": s.get("status"),
              "in_baseline": in_baseline(s, base)}
             for s in fold(entries) if fy_of(date.fromisoformat(s["sell_date"])) == fy]
    doc = {"fy": fy, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "baseline": baseline, "sales": sales, "totals": run["fy_tax"]}
    out_dir = _skill_data_dir(log_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"realised-gains-FY{fy}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    return path


def read_broker_csv(path):
    """Broker tax P&L rows (realised-gains-template.md) grouped into sales by
    (account, symbol, sell_date): summed qty, stcg (term ST), ltcg (term LT), charges."""
    sales = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["account"].strip(), row["symbol"].strip().upper(), row["sell_date"].strip())
            date.fromisoformat(key[2])
            sale = sales.setdefault(key, {"account": key[0], "ticker": key[1], "sell_date": key[2],
                                          "qty": 0.0, "stcg": 0.0, "ltcg": 0.0, "charges": 0.0,
                                          "_value": 0.0})
            q = float(row["qty"])
            sale["qty"] += q
            sale["_value"] += q * float(row["sell_price"])
            term = row["term"].strip().upper()
            if term not in ("ST", "LT"):
                raise ValueError(f"term must be ST or LT, got {row['term']!r}")
            sale["stcg" if term == "ST" else "ltcg"] += float(row["gain"])
            sale["charges"] += float(row.get("charges") or 0)
    out = []
    for sale in sales.values():
        sale["price"] = sale.pop("_value") / sale["qty"] if sale["qty"] else 0.0
        out.append(sale)
    return out


def reconcile(path, entries=None, log_dir=None):
    """Confirm logged sales against a broker report, import the ones not logged.
    Broker figures win. Idempotent: confirmed or already imported sales are skipped."""
    log_dir = log_dir or LOG_DIR
    entries = list(entries if entries is not None else read_entries(log_dir))
    result = {"confirmed": [], "imported": [], "mismatched": []}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for b in read_broker_csv(path):
        key = (b["account"], b["ticker"], b["sell_date"])
        same = [s for s in fold(entries)
                if (s["account"], s["ticker"], s["sell_date"]) == key]
        if any(s.get("status") == "confirmed" or s.get("source") == "broker" for s in same):
            continue
        if not same:
            rec = {"kind": "sale", "id": _new_id(b["sell_date"], b["ticker"], entries, ROOT),
                   "ticker": b["ticker"], "account": b["account"], "sell_date": b["sell_date"],
                   "qty": b["qty"], "price": b["price"], "charges": b["charges"], "lots": [],
                   "stcg": b["stcg"], "ltcg": b["ltcg"], "untaxed_qty": 0.0,
                   "est_tax": tax_lots.LTCG_RATE_PCT / 100 * max(0.0, b["ltcg"])
                   + tax_lots.STCG_RATE_PCT / 100 * max(0.0, b["stcg"]),
                   "status": "confirmed", "source": "broker", "recorded_at": now}
            logdir.append(log_dir, rec, ROOT, b["sell_date"])
            entries.append(rec)
            result["imported"].append(rec["id"])
            continue
        match = next((s for s in same if abs(s["qty"] - b["qty"]) < 1e-9), None)
        if match is None:
            result["mismatched"].append({"id": same[0]["id"], "field": "qty",
                                         "logged": same[0]["qty"], "broker": b["qty"]})
            continue
        logged, broker = match["stcg"] + match["ltcg"], b["stcg"] + b["ltcg"]
        if abs(logged - broker) > GAIN_TOLERANCE_PCT / 100 * abs(broker) + GAIN_TOLERANCE_ABS:
            result["mismatched"].append({"id": match["id"], "field": "gain",
                                         "logged": logged, "broker": broker})
            continue
        rec = {"kind": "confirm", "ref": match["id"], "stcg": b["stcg"], "ltcg": b["ltcg"],
               "charges": b["charges"], "status": "confirmed", "recorded_at": now}
        logdir.append(log_dir, rec, ROOT, b["sell_date"])
        entries.append(rec)
        result["confirmed"].append(match["id"])
    return result


def _report(fy, log_dir=None):
    run = fy_running(fy, log_dir=log_dir)
    b = run["baseline"]
    base = b["accounts"] if b else {}
    print(f"Realised gains FY {fy}")
    if b:
        for account, ab in sorted(base.items()):
            who = "" if account == "*" else f" ({account})"
            print(f"  baseline{who} to {ab['as_of']}: STCG {ab['stcg']:,.0f}, LTCG {ab['ltcg']:,.0f}")
    for s in fold(read_entries(log_dir)):
        if fy_of(date.fromisoformat(s["sell_date"])) == fy:
            inb = " (in broker baseline, not added)" if in_baseline(s, base) else ""
            print(f"  {s['sell_date']} {s['ticker']} ({s['account']}) {s['qty']:g} @ {s['price']:g}: "
                  f"STCG {s['stcg']:,.0f}, LTCG {s['ltcg']:,.0f} [{s.get('status')}]{inb}")
            if s.get("untaxed_qty"):
                print(f"    {s['untaxed_qty']:g} share(s): tax not estimated, excluded from totals")
    t = run["fy_tax"]
    print(f"  total STCG {run['stcg']:,.0f}, LTCG {run['ltcg']:,.0f}; exemption left {t['exempt_left']:,.0f}; "
          f"est. tax {t['tax']:,.0f}; unconfirmed sales {run['unconfirmed']}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("ticker")
    r.add_argument("qty", type=float)
    r.add_argument("price", type=float)
    r.add_argument("--date", required=True)
    r.add_argument("--account", required=True)
    r.add_argument("--charges", type=float, default=0.0,
                   help="deductible sale expenses such as brokerage; exclude STT")
    rc = sub.add_parser("reconcile")
    rc.add_argument("path")
    for name in ("report", "export"):
        s = sub.add_parser(name)
        s.add_argument("--fy", default=None)
    a = p.parse_args()
    try:
        if a.cmd == "record":
            rec = record(a.ticker, a.qty, a.price, a.date, a.account, a.charges)
            print(f"Recorded {rec['id']}: STCG {rec['stcg']:,.0f}, LTCG {rec['ltcg']:,.0f}, "
                  f"est. tax {rec['est_tax']:,.0f}")
        elif a.cmd == "reconcile":
            res = reconcile(a.path)
            print(f"confirmed {len(res['confirmed'])}, imported {len(res['imported'])}, "
                  f"mismatched {len(res['mismatched'])}")
            for m in res["mismatched"]:
                print(f"  {m['id']}: {m['field']} logged {m['logged']:g} vs broker {m['broker']:g}")
        else:
            fy = a.fy or fy_of(date.today())
            if a.cmd == "report":
                _report(fy)
            else:
                print(export(fy))
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
