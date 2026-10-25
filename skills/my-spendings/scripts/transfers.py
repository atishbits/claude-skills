#!/usr/bin/env python3
"""Decide which bucket each classified transaction belongs to, so nothing is
counted twice: a card bill paid from a bank account drops out when that card's
own statement (and so its purchases) is in the ledger, and is counted once as
"card spend (not broken down)" when it is not. Transfers between your own
tracked accounts drop out; money moved to an untracked account of your own is
shown separately, never as spending.

Buckets: spend, income, invest, tax, family, own_moved_out, other_in (money in
that is not labelled as income or a refund), excluded.
"""
import datetime as dt
import re

BILL_CYCLE_DAYS = 35
CARD_MATCH_DAYS = 7
OWN_MATCH_DAYS = 3


def _d(s):
    return dt.date.fromisoformat(s)


def _bucket_for(category):
    if category in ("income", "interest"):
        return "income"
    if category.startswith("investment:"):
        return "invest"
    return {"tax": "tax", "family_transfer": "family"}.get(category, "spend")


def _covered(spans, date):
    d = _d(date)
    return any(_d(a) <= d and _d(b) >= d - dt.timedelta(days=BILL_CYCLE_DAYS) for a, b in spans)


def resolve(txns, accounts, coverage):
    """(txns each with a bucket, warnings)."""
    accts = {a["alias"]: a for a in (accounts or {}).get("accounts", [])}
    cards = [a for a in accts.values() if a.get("type") == "card"]
    out = [dict(t) for t in txns]
    warnings = []
    used = set()

    for i, t in enumerate(out):
        cat = t["category"]
        amt = float(t["amount"])
        acct = accts.get(t["account"], {})
        if cat == "card_payment":
            if acct.get("type") == "card":
                t["bucket"] = "excluded"   # the payment arriving on the card
                continue
            card = next((c for c in cards if c.get("bill_payment_pattern") and
                         re.search(c["bill_payment_pattern"], t.get("description", ""), re.I)), None)
            if card and _covered(coverage.get(card["alias"], []), t["date"]):
                t["bucket"] = "excluded"
                match = next((j for j, u in enumerate(out) if j not in used
                              and u["account"] == card["alias"] and u["category"] == "card_payment"
                              and abs(float(u["amount"]) + amt) <= 1
                              and abs((_d(u["date"]) - _d(t["date"])).days) <= CARD_MATCH_DAYS), None)
                if match is None:
                    warnings.append({"kind": "card_payment_unmatched", "date": t["date"],
                                     "amount": amt, "detail": f"no matching payment on {card['alias']}"})
                else:
                    used.add(match)
            else:
                t["bucket"] = "spend"
                t["category"] = "card_spend_unexpanded"
            continue
        if cat == "own_transfer":
            if i in used:
                t["bucket"] = "excluded"
                continue
            pair = next((j for j, u in enumerate(out) if j != i and j not in used
                         and u["category"] == "own_transfer" and u["account"] != t["account"]
                         and u["account"] in accts
                         and abs(float(u["amount"]) + amt) <= 1
                         and abs((_d(u["date"]) - _d(t["date"])).days) <= OWN_MATCH_DAYS), None)
            if pair is not None:
                used.update({i, pair})
                t["bucket"] = "excluded"
            else:
                t["bucket"] = "own_moved_out" if amt < 0 else "excluded"
            continue
        t["bucket"] = _bucket_for(cat)
        if t["bucket"] == "spend" and amt > 0 and cat != "refund":
            t["bucket"] = "other_in"   # unlabelled money in: neither income nor less spending
    for j in used:
        if out[j].get("bucket") is None or out[j]["category"] == "own_transfer":
            out[j]["bucket"] = "excluded"
    return out, warnings
