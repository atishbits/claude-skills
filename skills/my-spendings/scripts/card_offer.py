#!/usr/bin/env python3
"""What a credit card would be worth in a year at the user's own spending:
rewards (capped per month), fuel surcharge waived, and fees. Reads the
trailing-12-month spend from the latest analysis.

    python3 scripts/card_offer.py [--offer FILE ...] [--scale CAT=F ...] [--root R] [--json]

--scale fuel=0.85 values the cards as if fuel spending were 85% of what the
statements show (say, the same litres after a price drop); each fill-up is
scaled, so per-fill bands and monthly caps apply to the new amounts.

With no --offer, every data/offers/*.json and data/cards/*.json (current cards,
for comparison) is valued. Offer fields are documented in README.md.
"""
import argparse
import glob
import json
import os

import common

DEFAULTS = {"joining_fee": 0, "annual_fee": 0, "fee_waiver_spend": None, "gst_on_fees_pct": 18,
            "rates": {}, "reward_cap_month": {}, "point_value_inr": 1.0, "fuel_surcharge_pct": 1.0,
            "surcharge_waiver_pct": 0, "surcharge_txn_min": 0, "surcharge_txn_max": None,
            "surcharge_waiver_cap_month": None, "use_for": None}


# Spending that can usually go on a credit card. Rent, EMIs, cash, fees, tax,
# school fees and unknown or not-broken-down spend are left out unless an
# offer's use_for names them.
CARDABLE = ["fuel", "groceries", "food_delivery", "dining", "shopping", "utilities", "travel",
            "transport", "health", "insurance", "subscriptions", "entertainment", "personal_care"]


def _r(x):
    return round(x, 2)


def _by_month(txns, pred=lambda t: True):
    m = {}
    for t in txns:
        if pred(t):
            m.setdefault(t["date"][:7], []).append(t["amount"])
    return m


def _month_factors(txns, default):
    """Each month's scale-to-a-year factor: the amount-weighted factor of its
    transactions (each carries its account's factor), else the default."""
    out = {}
    for mo in _by_month(txns):
        ts = [t for t in txns if t["date"][:7] == mo]
        tot = sum(t["amount"] for t in ts)
        out[mo] = (sum(t["amount"] * t.get("factor", default) for t in ts) / tot) if tot else default
    return out


def value(offer, spend_12m):
    o = dict(DEFAULTS, **offer)
    factor = spend_12m.get("factor") or 1.0
    cats = o["use_for"] or [c for c in CARDABLE if c in spend_12m["by_category"]]
    left = sorted(c for c in spend_12m["by_category"] if c not in cats and spend_12m["by_category"][c] > 0)
    pv = o["point_value_inr"]
    rewards = 0.0
    notes = []
    for c in cats:
        rate = o["rates"].get(c, o["rates"].get("default", 0.0))
        cap = o["reward_cap_month"].get(c)
        if c == "fuel" and spend_12m.get("fuel_txns"):
            mf = _month_factors(spend_12m["fuel_txns"], factor)
            for mo, amounts in _by_month(spend_12m["fuel_txns"]).items():
                r = sum(amounts) * rate * pv
                rewards += (min(r, cap) if cap is not None else r) * mf[mo]
        else:
            monthly = spend_12m["by_category"].get(c, 0.0) / 12
            r = monthly * rate * pv
            rewards += 12 * (min(r, cap) if cap is not None else r)
    saved = 0.0
    if o["surcharge_waiver_pct"]:
        hi = o["surcharge_txn_max"] if o["surcharge_txn_max"] is not None else float("inf")
        band = lambda t: o["surcharge_txn_min"] <= t["amount"] <= hi
        mf = _month_factors(spend_12m.get("fuel_txns", []), factor)
        for mo, amounts in _by_month(spend_12m.get("fuel_txns", []), band).items():
            s = sum(amounts) * o["fuel_surcharge_pct"] / 100 * o["surcharge_waiver_pct"] / 100
            cap = o["surcharge_waiver_cap_month"]
            saved += (min(s, cap) if cap is not None else s) * mf[mo]
    on_card = sum(spend_12m["by_category"].get(c, 0.0) for c in cats)
    gst = 1 + o["gst_on_fees_pct"] / 100
    waived = o["fee_waiver_spend"] is not None and on_card >= o["fee_waiver_spend"]
    fees = 0.0 if waived else o["annual_fee"] * gst
    if waived and o["annual_fee"]:
        notes.append(f"annual fee waived: {on_card:,.0f} a year on the card passes {o['fee_waiver_spend']:,.0f}")
    if spend_12m.get("annualised"):
        mba = spend_12m.get("months_by_account")
        if mba:
            notes.append("spend annualised from months of statements per account: "
                         + ", ".join(f"{a} {m:g}" for a, m in sorted(mba.items())))
        else:
            notes.append(f"spend annualised from {spend_12m.get('months_covered')} months of statements")
    notes.append("assumes all of " + ", ".join(cats) + " spending moves to this card")
    if left:
        notes.append("left out (usually not payable by card): " + ", ".join(left))
    return {"name": o.get("name", "?"), "rewards": _r(rewards), "surcharge_saved": _r(saved),
            "fees": _r(fees), "first_year_extra": _r(o["joining_fee"] * gst),
            "net": _r(rewards + saved - fees), "spend_on_card": _r(on_card), "notes": notes,
            "source": o.get("source"), "as_of": o.get("as_of")}


def scale_spend(spend_12m, scales):
    """A copy of spend_12m with each category in scales (name -> factor)
    multiplied by its factor; fuel's fill-ups are scaled one by one."""
    out = dict(spend_12m, by_category=dict(spend_12m["by_category"]))
    for cat, f in scales.items():
        if cat in out["by_category"]:
            out["by_category"][cat] = out["by_category"][cat] * f
        if cat == "fuel" and spend_12m.get("fuel_txns"):
            out["fuel_txns"] = [dict(t, amount=t["amount"] * f) for t in spend_12m["fuel_txns"]]
    return out


def _parse_scales(items):
    scales = {}
    for it in items or []:
        cat, _, f = it.partition("=")
        try:
            scales[cat.strip()] = float(f)
        except ValueError:
            raise SystemExit(f"--scale wants CATEGORY=FACTOR, e.g. fuel=0.85, not {it!r}")
        if not cat.strip() or scales[cat.strip()] < 0:
            raise SystemExit(f"--scale wants CATEGORY=FACTOR, e.g. fuel=0.85, not {it!r}")
    return scales


def latest_analysis(root):
    files = sorted(glob.glob(os.path.join(common.paths(root)["skill_data"], "analysis-*.json")))
    if not files:
        raise SystemExit("No analysis yet: run analyse.py first.")
    return common.load_json(files[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offer", nargs="*")
    ap.add_argument("--scale", nargs="*", metavar="CAT=F",
                    help="what-if: scale a category's spending, e.g. fuel=0.85")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = common.resolve_root(a.root)
    p = common.paths(root)
    scales = _parse_scales(a.scale)
    spend = scale_spend(latest_analysis(root)["spend_12m"], scales)
    files = a.offer or sorted(glob.glob(os.path.join(p["offers"], "*.json")))
    current = sorted(glob.glob(os.path.join(p["cards"], "*.json")))
    rows = [dict(value(common.load_json(f), spend), kind="offer") for f in files]
    rows += [dict(value(common.load_json(f), spend), kind="current") for f in current]
    rows.sort(key=lambda r: -r["net"])
    for r in rows:
        for cat, f in scales.items():
            r["notes"].insert(0, f"what-if: {cat} spending scaled to {f:g} of the statements")
    if a.json:
        print(json.dumps(rows, indent=1))
        return
    print("| Card | Kind | Rewards | Surcharge saved | Fees | Net a year | First-year extra |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['kind']} | {r['rewards']:,.0f} | {r['surcharge_saved']:,.0f} | "
              f"{r['fees']:,.0f} | **{r['net']:,.0f}** | {r['first_year_extra']:,.0f} |")
    for r in rows:
        for n in r["notes"]:
            print(f"- {r['name']}: {n}")


if __name__ == "__main__":
    main()
