#!/usr/bin/env python3
"""Append-only log of equity sales the user reports, with FY realised-gain totals.

    python3 scripts/gains_log.py record TICKER QTY PRICE --date YYYY-MM-DD --account NAME [--charges N]
    python3 scripts/gains_log.py report [--fy 2026-27]
    python3 scripts/gains_log.py export [--fy 2026-27]

Each sale is matched FIFO against the newest snapshot's lots in that demat
account (tax_lots.py), after skipping units already logged as sold since the
snapshot's holdings date. The log is a folder of per-writer-per-day files
(logdir.py). A later `kind: "confirm"` record (ref = a sale id) is folded over
the sale by `fold`. `export` writes a hand-off file other sessions can read.
The skill only records sales the user reports or the broker report contains.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

import logdir
import tax_lots

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
SKILL_DATA_DIR = os.path.join(ROOT, "data", "skill-data")
LOG_DIR = os.path.join(SKILL_DATA_DIR, "realised-gains")

BASELINE_NOTE = "broker FY total to as_of; includes mutual funds where the broker reports them"


def fy_of(d):
    """Indian financial year of a date, e.g. date(2027, 3, 31) -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _norm_fy(label):
    label = (label or "").strip()
    return label[3:].strip() if label.upper().startswith("FY ") else label


def read_entries(log_dir=None):
    return logdir.read(log_dir or LOG_DIR)


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


def _snapshot():
    try:
        return tax_lots.latest_snapshot()[0]
    except SystemExit:
        return None


def _new_id(sell_date, ticker, entries, root):
    prefix = f"{sell_date}-{ticker}-{logdir.writer_id(root)}-"
    n = sum(1 for e in entries if e.get("kind") == "sale" and str(e.get("id", "")).startswith(prefix))
    return f"{prefix}{n + 1}"


def record(ticker, qty, price, sell_date, account, charges=0.0, snapshot=None, entries=None):
    ticker = ticker.strip().upper()
    qty, price = float(qty), float(price)
    if qty <= 0 or price <= 0:
        raise ValueError("qty and price must be positive")
    date.fromisoformat(sell_date)
    snapshot = snapshot if snapshot is not None else _snapshot()
    if snapshot is None:
        raise ValueError("no snapshot on file; run fetch_fundamentals.py first")
    stock = next((s for s in snapshot["stocks"] if s["ticker"] == ticker), None)
    if stock is None:
        raise ValueError(f"{ticker} not in the snapshot")
    entries = entries if entries is not None else read_entries()
    since = snapshot["holdings_date"]
    already = sum(e["qty"] for e in fold(entries)
                  if e["ticker"] == ticker and e["account"] == account and e["sell_date"] > since)
    matched = tax_lots.fifo_match(stock.get("lots") or [], qty, account, already_sold=already,
                                  fallback_cost=stock.get("avg_cost"))
    t = tax_lots.sale_tax(matched, price, date.fromisoformat(sell_date))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec = {"kind": "sale", "id": _new_id(sell_date, ticker, entries, ROOT), "ticker": ticker,
           "account": account, "sell_date": sell_date, "qty": qty, "price": price,
           "charges": float(charges), "lots": matched, "stcg": t["stcg"], "ltcg": t["ltcg"],
           "untaxed_qty": t["untaxed_qty"], "est_tax": t["est_tax"], "status": "unconfirmed",
           "source": "user", "recorded_at": now}
    logdir.append(LOG_DIR, rec, ROOT, sell_date)
    return rec


def fy_running(fy, entries=None, snapshot=None):
    entries = entries if entries is not None else read_entries()
    snapshot = snapshot if snapshot is not None else _snapshot()
    baseline = None
    tp = (snapshot or {}).get("tax_position")
    if tp and _norm_fy(tp.get("fy")) == fy:
        baseline = {"as_of": snapshot["holdings_date"], "stcg": tp.get("realised_stcg") or 0.0,
                    "ltcg": tp.get("realised_ltcg") or 0.0}
    stcg = baseline["stcg"] if baseline else 0.0
    ltcg = baseline["ltcg"] if baseline else 0.0
    unconfirmed = 0
    for s in fold(entries):
        if fy_of(date.fromisoformat(s["sell_date"])) != fy:
            continue
        if baseline and s["sell_date"] <= baseline["as_of"]:
            continue
        stcg += s["stcg"]
        ltcg += s["ltcg"]
        unconfirmed += s.get("status") == "unconfirmed"
    return {"baseline": baseline, "stcg": stcg, "ltcg": ltcg,
            "fy_tax": tax_lots.fy_tax(stcg, ltcg), "unconfirmed": unconfirmed}


def export(fy):
    entries, snapshot = read_entries(), _snapshot()
    run = fy_running(fy, entries, snapshot)
    baseline = dict(run["baseline"], note=BASELINE_NOTE) if run["baseline"] else None
    sales = [{"date": s["sell_date"], "ticker": s["ticker"], "account": s["account"],
              "qty": s["qty"], "stcg": s["stcg"], "ltcg": s["ltcg"], "status": s.get("status")}
             for s in fold(entries) if fy_of(date.fromisoformat(s["sell_date"])) == fy]
    doc = {"fy": fy, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "baseline": baseline, "sales": sales, "totals": run["fy_tax"]}
    os.makedirs(SKILL_DATA_DIR, exist_ok=True)
    path = os.path.join(SKILL_DATA_DIR, f"realised-gains-FY{fy}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    return path


def _report(fy):
    run = fy_running(fy)
    b = run["baseline"]
    print(f"Realised gains FY {fy}")
    if b:
        print(f"  baseline to {b['as_of']}: STCG {b['stcg']:,.0f}, LTCG {b['ltcg']:,.0f}")
    for s in fold(read_entries()):
        if fy_of(date.fromisoformat(s["sell_date"])) == fy:
            print(f"  {s['sell_date']} {s['ticker']} ({s['account']}) {s['qty']:g} @ {s['price']:g}: "
                  f"STCG {s['stcg']:,.0f}, LTCG {s['ltcg']:,.0f} [{s.get('status')}]")
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
    r.add_argument("--charges", type=float, default=0.0)
    for name in ("report", "export"):
        s = sub.add_parser(name)
        s.add_argument("--fy", default=None)
    a = p.parse_args()
    try:
        if a.cmd == "record":
            rec = record(a.ticker, a.qty, a.price, a.date, a.account, a.charges)
            print(f"Recorded {rec['id']}: STCG {rec['stcg']:,.0f}, LTCG {rec['ltcg']:,.0f}, "
                  f"est. tax {rec['est_tax']:,.0f}")
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
