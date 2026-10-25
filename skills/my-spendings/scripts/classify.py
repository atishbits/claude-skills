#!/usr/bin/env python3
"""Give every ledger transaction a category, from the user's own rules first,
then the account patterns in accounts.json, then generic keyword rules.

    python3 scripts/classify.py uncategorised [--top 20] [--root R]
    python3 scripts/classify.py add-rule --pattern REGEX --category C [--direction out|in|any] [--root R]
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

import common

FLOW = ["income", "interest", "refund", "own_transfer", "card_payment", "family_transfer", "tax",
        "investment:fd", "investment:stocks", "investment:mf", "investment:bonds",
        "investment:gold", "investment:other"]
SPEND = ["fuel", "groceries", "food_delivery", "dining", "shopping", "utilities", "housing",
         "travel", "transport", "health", "education", "insurance", "subscriptions",
         "entertainment", "fees_charges", "cash", "personal_care", "gifts_donations", "loan_emi",
         "other_spend", "uncategorised", "card_spend_unexpanded"]
CATEGORIES = FLOW + SPEND
CARD_PAYMENT_CREDIT = re.compile(r"PAYMENT RECEIVED|THANK YOU|PAYMENT\s*-|AUTO ?PAY|BBPS|BILL ?PAY", re.I)
DEFAULT_RULES = os.path.join(common.SKILL_DIR, "references", "default_rules.json")

Rule = collections.namedtuple("Rule", "pattern category direction")


def _check(rule):
    re.compile(rule.pattern)
    if rule.category not in CATEGORIES:
        raise ValueError(f"unknown category {rule.category!r}")
    if rule.direction not in ("out", "in", "any"):
        raise ValueError(f"direction must be out, in or any, not {rule.direction!r}")
    return rule


def load_rules(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [_check(Rule(r["pattern"], r["category"], (r.get("direction") or "any").strip()))
                for r in csv.DictReader(f) if r.get("pattern")]


def load_default_rules():
    return [_check(Rule(*r)) for r in common.load_json(DEFAULT_RULES)["rules"]]


def _hit(rule, desc, amount):
    if rule.direction == "out" and amount >= 0:
        return False
    if rule.direction == "in" and amount <= 0:
        return False
    return re.search(rule.pattern, desc, re.I) is not None


def classify(txn, user_rules, default_rules, accounts):
    desc = txn.get("description", "")
    amount = float(txn["amount"])
    for r in user_rules:
        if _hit(r, desc, amount):
            return r.category
    accts = {a["alias"]: a for a in (accounts or {}).get("accounts", [])}
    me = accts.get(txn.get("account"), {})
    if me.get("type") == "card" and amount > 0:
        return "card_payment" if CARD_PAYMENT_CREDIT.search(desc) else "refund"
    for a in accts.values():
        if a.get("type") == "card" and a.get("bill_payment_pattern") and amount < 0 \
                and re.search(a["bill_payment_pattern"], desc, re.I):
            return "card_payment"
    for p in (accounts or {}).get("self_patterns", []):
        if re.search(p, desc, re.I):
            return "own_transfer"
    for p in (accounts or {}).get("family_patterns", []):
        if re.search(p, desc, re.I):
            return "family_transfer"
    for r in default_rules:
        if _hit(r, desc, amount):
            return r.category
    return "uncategorised"


def classify_all(txns, user_rules, default_rules, accounts):
    return [dict(t, category=classify(t, user_rules, default_rules, accounts),
                 payee=common.payee_key(t.get("description", ""))) for t in txns]


def classify_root(root):
    """Ledger rows of a working root, each with category and payee."""
    import ingest
    p = common.paths(root)
    return classify_all(ingest.load_ledger(p["ledger"]), load_rules(p["rules"]),
                        load_default_rules(), common.load_json(p["accounts"], {}))


def uncategorised(txns, top=20):
    agg = {}
    for t in txns:
        if t["category"] != "uncategorised":
            continue
        a = agg.setdefault(t["payee"], {"payee": t["payee"], "count": 0, "total": 0.0})
        a["count"] += 1
        a["total"] = round(a["total"] + float(t["amount"]), 2)
    return sorted(agg.values(), key=lambda a: -abs(a["total"]))[:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("uncategorised")
    u.add_argument("--top", type=int, default=20)
    r = sub.add_parser("add-rule")
    r.add_argument("--pattern", required=True)
    r.add_argument("--category", required=True)
    r.add_argument("--direction", default="any")
    a = ap.parse_args()
    root = common.resolve_root(a.root)
    if a.cmd == "uncategorised":
        print(json.dumps(uncategorised(classify_root(root), a.top), indent=1))
        return
    try:
        rule = _check(Rule(a.pattern, a.category, a.direction))
    except (re.error, ValueError) as e:
        sys.exit(f"Rule not added: {e}")
    path = common.paths(root)["rules"]
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["pattern", "category", "direction"])
        w.writerow(list(rule))
    print(f"added: {rule.pattern} -> {rule.category} ({rule.direction})")


if __name__ == "__main__":
    main()
