#!/usr/bin/env python3
"""Every figure the report quotes: monthly spend by category, income vs
spending vs investing, recurring payments, fees, unusual transactions, the
investment mix and trailing-12-month spend for card decisions.

    python3 scripts/analyse.py [--as-of YYYY-MM-DD] [--from D --to D] [--root R]

Writes data/skill-data/analysis-<as-of>.json and prints its path.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import statistics

import classify
import common
import transfers

MANDATE = re.compile(r"\bNACH\b|\bECS\b|\bACH ?D|E-?MANDATE|AUTO ?PAY|AUTO ?DEBIT|\bSI-|STANDING INSTRUCTION", re.I)
FOREIGN = re.compile(r"\b(USD|EUR|GBP|AED|SGD|INTL|INTERNATIONAL|FOREIGN|CROSS ?BORDER|DCC)\b", re.I)
CADENCES = [("weekly", 6, 8, 52), ("monthly", 25, 35, 12), ("quarterly", 85, 95, 4),
            ("yearly", 350, 380, 1)]
PERIOD_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365, "mandate": 30}


def _a(t):
    return float(t["amount"])


def _d(s):
    return dt.date.fromisoformat(s)


def _r(x):
    return round(x, 2)


def monthly(txns):
    out = {}
    for t in txns:
        if t["bucket"] != "spend":
            continue
        m = out.setdefault(t["date"][:7], {})
        m[t["category"]] = _r(m.get(t["category"], 0.0) - _a(t))
    return dict(sorted(out.items()))


def rates(txns):
    s = {}
    for t in txns:
        s[t["bucket"]] = s.get(t["bucket"], 0.0) + _a(t)
    income = _r(s.get("income", 0.0))
    r = {"income": income, "spend": _r(-s.get("spend", 0.0)), "invest_net": _r(-s.get("invest", 0.0)),
         "tax": _r(-s.get("tax", 0.0)), "family": _r(-s.get("family", 0.0)),
         "own_moved_out": _r(-s.get("own_moved_out", 0.0)), "other_in": _r(s.get("other_in", 0.0))}
    r["savings_rate"] = (round((income - r["spend"] - r["tax"] - r["family"]) / income, 4)
                         if income > 0 else None)
    r["investing_rate"] = round(r["invest_net"] / income, 4) if income > 0 else None
    return r


def recurring(txns, as_of, tolerance=0.15):
    by = {}
    for t in txns:
        if _a(t) < 0 and (t["bucket"] == "spend" or MANDATE.search(t.get("description", ""))):
            by.setdefault(t["payee"], []).append(t)
    out = []
    for payee, rows in by.items():
        rows.sort(key=lambda t: t["date"])
        amts = [-_a(t) for t in rows]
        med = statistics.median(amts)
        keep = [t for t in rows if abs(-_a(t) - med) <= tolerance * med]
        cadence, per_year = None, None
        if len(keep) >= 2:
            gaps = [(_d(b["date"]) - _d(a["date"])).days for a, b in zip(keep, keep[1:])]
            g = statistics.median(gaps)
            for name, lo, hi, n in CADENCES:
                need = 2 if name == "yearly" else 3
                if lo <= g <= hi and len(keep) >= need:
                    cadence, per_year = name, n
                    break
        mandate = any(MANDATE.search(t.get("description", "")) for t in rows)
        if not cadence and not mandate:
            continue
        if not cadence:
            cadence, keep = "mandate", rows
        typical = _r(statistics.median([-_a(t) for t in keep]))
        last = keep[-1]["date"]
        out.append({"payee": payee, "category": keep[-1]["category"], "cadence": cadence,
                    "typical": typical, "yearly_cost": _r(typical * per_year) if per_year else None,
                    "first": keep[0]["date"], "last": last, "count": len(keep),
                    "active": (_d(as_of) - _d(last)).days <= 1.5 * PERIOD_DAYS[cadence],
                    "mandate": mandate, "account": keep[-1]["account"]})
    return sorted(out, key=lambda r: -(r["yearly_cost"] or r["typical"]))


def fees(txns):
    items = [{"date": t["date"], "account": t["account"], "description": t["description"],
              "amount": _r(-_a(t))} for t in txns if t["category"] == "fees_charges"]
    return {"total": _r(sum(i["amount"] for i in items)), "items": items}


def _spend(t):
    """Real spending: not investments, tax or transfers, and not a card bill
    whose purchases are unknown (its size says nothing about a single charge)."""
    return t["bucket"] == "spend" and t["category"] != "card_spend_unexpanded"


def anomalies(txns, profile, history=None):
    history = sorted(history if history is not None else txns, key=lambda t: t["date"])
    out = []
    groups = {}
    for t in txns:
        if _a(t) < 0 and _spend(t):
            groups.setdefault((t["account"], t["payee"], t["amount"], t["date"]), []).append(t)
    for (acct, payee, amt, date), g in groups.items():
        if len(g) >= 2:
            out.append({"kind": "duplicate", "payee": payee, "date": date, "account": acct,
                        "amount": _r(float(amt)), "count": len(g)})
    first_seen = {}
    for t in history:
        first_seen.setdefault(t["payee"], t)
    for t in txns:
        a = _a(t)
        base = {"payee": t["payee"], "date": t["date"], "account": t["account"], "amount": _r(a),
                "description": t["description"]}
        if a < 0 and -a <= profile["tiny_debit_max"] and t["category"] != "fees_charges":
            out.append(dict(base, kind="tiny_debit"))
        if (a < 0 and -a >= profile["new_payee_min"] and _spend(t)
                and first_seen.get(t["payee"]) is t):
            out.append(dict(base, kind="new_payee_large"))
        if a < 0 and _spend(t):
            prior = [-_a(h) for h in history if h["payee"] == t["payee"] and _a(h) < 0
                     and h["date"] < t["date"]]
            if len(prior) >= 3 and -a >= profile["outlier_multiple"] * statistics.median(prior):
                out.append(dict(base, kind="outlier", usual=_r(statistics.median(prior))))
        if FOREIGN.search(t.get("description", "")):
            out.append(dict(base, kind="foreign"))
    return out


def mix(holdings, flows, profile):
    flows_by_type = {}
    for t in flows:
        if t["bucket"] == "invest":
            k = t["category"].split(":", 1)[1]
            flows_by_type[k] = _r(flows_by_type.get(k, 0.0) - _a(t))
    if not holdings:
        return {"holdings_missing": True, "flows_by_type": flows_by_type, "by_type": {}, "flags": []}
    total = sum(float(h["value_inr"]) for h in holdings)
    by_type, flags = {}, []
    for h in holdings:
        b = by_type.setdefault(h["asset_type"], {"value": 0.0})
        b["value"] += float(h["value_inr"])
    for k, b in by_type.items():
        b["value"] = _r(b["value"])
        b["share_pct"] = round(100 * b["value"] / total, 1)
        if b["share_pct"] > profile["max_asset_type_share_pct"]:
            flags.append({"kind": "type_over_cap", "name": k, "share_pct": b["share_pct"]})
    for h in holdings:
        sh = round(100 * float(h["value_inr"]) / total, 1)
        if sh > profile["max_single_holding_share_pct"]:
            flags.append({"kind": "holding_over_cap", "name": h["name"], "share_pct": sh})
    return {"holdings_missing": False, "total": _r(total), "by_type": by_type, "flags": flags,
            "flows_by_type": flows_by_type,
            "as_of": max((h.get("as_of") or "" for h in holdings), default="")}


def spend_12m(txns, as_of):
    end = _d(as_of)
    start = end - dt.timedelta(days=365)
    rows = [t for t in txns if t["bucket"] == "spend" and start < _d(t["date"]) <= end]
    if rows:
        first = min(_d(t["date"]) for t in rows)
        months = min(12, (end.year - first.year) * 12 + end.month - first.month + 1)
    else:
        months = 0
    factor = round(12 / months, 4) if months else 0.0
    out = {"months_covered": months, "annualised": 0 < months < 12, "factor": factor,
           "by_category": {}, "by_account": {}, "by_holder": {}, "fuel_txns": []}
    for t in rows:
        v = -_a(t) * factor
        for key, k in (("by_category", t["category"]), ("by_account", t["account"]),
                       ("by_holder", t.get("holder") or "self")):
            out[key][k] = _r(out[key].get(k, 0.0) + v)
        if t["category"] == "fuel":
            out["fuel_txns"].append({"date": t["date"], "amount": _r(-_a(t)), "account": t["account"]})
    return out


def addon_spend(txns):
    out = {}
    for t in txns:
        if t["bucket"] == "spend" and t.get("holder"):
            m = out.setdefault(t["holder"], {})
            m[t["date"][:7]] = _r(m.get(t["date"][:7], 0.0) - _a(t))
    return out


def _top_payees(txns, n=15):
    agg = {}
    for t in txns:
        if t["bucket"] == "spend":
            a = agg.setdefault(t["payee"], {"payee": t["payee"], "category": t["category"],
                                            "count": 0, "total": 0.0})
            a["count"] += 1
            a["total"] = _r(a["total"] - _a(t))
    return sorted(agg.values(), key=lambda a: -a["total"])[:n]


def _holdings(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("value_inr")]


def run(root, as_of=None, frm=None, to=None):
    p = common.paths(root)
    profile = dict(common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json")))
    profile.update(common.load_json(p["profile"], {}))
    coverage = common.load_json(p["coverage"], {})
    accounts = common.load_json(p["accounts"], {})
    rows = classify.classify_root(root)
    resolved, warnings = transfers.resolve(rows, accounts, coverage)
    as_of = as_of or max((t["date"] for t in resolved), default=dt.date.today().isoformat())
    frm = frm or min((t["date"] for t in resolved), default=as_of)
    to = to or as_of
    period = [t for t in resolved if frm <= t["date"] <= to]
    hist = [t for t in resolved if t["date"] <= to]
    a = {"as_of": as_of, "from": frm, "to": to, "rows": len(period),
         "accounts": sorted({t["account"] for t in period}), "coverage": coverage,
         "monthly": monthly(period), "rates": rates(period),
         "recurring": recurring(hist, to, profile["recurring_amount_tolerance"]),
         "fees": fees(period), "anomalies": anomalies(period, profile, hist),
         "mix": mix(_holdings(p["holdings"]), period, profile),
         "spend_12m": spend_12m(hist, to), "addon_spend": addon_spend(period),
         "warnings": [w for w in warnings if frm <= w["date"] <= to],
         "uncategorised": classify.uncategorised(period), "top_payees": _top_payees(period)}
    os.makedirs(p["skill_data"], exist_ok=True)
    out = os.path.join(p["skill_data"], f"analysis-{as_of}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(a, f, indent=1, ensure_ascii=False)
    a["_path"] = out
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to")
    ap.add_argument("--root")
    a = ap.parse_args()
    res = run(common.resolve_root(a.root), a.as_of, a.frm, a.to)
    print(res["_path"])


if __name__ == "__main__":
    main()
