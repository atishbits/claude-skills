#!/usr/bin/env python3
"""Tax arithmetic for mutual funds: the user's rates (from the advance-tax
skill's profile, never typed in), the after-tax FD hurdle, first-in-first-out
tax lots, and the tax sitting in unsold units.

    python3 scripts/tax.py import --tax-profile PATH --person NAME [--cess 1.04] [--root R] [--write]
    python3 scripts/tax.py hurdle [--root R] [--years N]

Rates and holding periods come from references/cg-rates.json. Equity: short
term up to 12 months (20%), long term after (12.5%, first ₹1.25L a year
exempt, shared with direct-stock gains). Hybrid 35-65% equity, gold and
international funds: long term after 24 months (12.5%, no exemption), else
slab. Debt funds bought from April 2023: slab whatever the holding period.
Surcharge on capital gains is capped at 15%.
"""
import argparse
import datetime as dt
import json
import sys
from collections import defaultdict

import common

UNITS_IN = {"buy", "sip", "switch_in", "dividend_reinvest"}
UNITS_OUT = {"sell", "switch_out"}


def import_tax_profile(path, person, cess=1.04):
    with open(path) as f:
        doc = json.load(f)
    people = doc.get("people", doc)
    if person not in people:
        raise ValueError(f"person {person!r} not in the tax profile")
    p = people[person]
    slab = p.get("other_tax_pct", p.get("fd_tax_pct"))
    if slab is None or "surcharge_multiplier" not in p:
        raise ValueError("tax profile entry needs other_tax_pct (or fd_tax_pct) and surcharge_multiplier")
    sur = float(p["surcharge_multiplier"])
    cap = common.load_tax_rules().get("ltcg_surcharge_cap_multiplier", 1.15)
    return {"slab_pct": round(float(slab) * 100, 2), "surcharge_multiplier": sur, "cess": cess,
            "effective_slab_pct": round(float(slab) * 100 * sur * cess, 2),
            "ltcg_multiplier": round(min(sur, cap) * cess, 4),
            "fd_rate_pct_in_profile": (round(p["fd_interest_rate"] * 100, 2)
                                       if p.get("fd_interest_rate") else None)}


def fd_hurdle(fd_rate_pct, effective_slab_pct):
    return fd_rate_pct * (1 - effective_slab_pct / 100)


def _exit_tax_rate(tax_class, years, rules, person):
    """Fraction of a gain lost to tax when sold after `years`."""
    months = years * 12
    if tax_class == "specified_debt":
        return person["effective_slab_pct"] / 100
    if tax_class == "equity":
        e = rules["equity"]
        pct = e["ltcg_pct"] if months > e["lt_months"] else e["stcg_pct"]
        return pct / 100 * person["ltcg_multiplier"]
    h = rules["hybrid_gold_intl"]
    if months > h["lt_months"]:
        return h["ltcg_pct"] / 100 * person["ltcg_multiplier"]
    return person["effective_slab_pct"] / 100


def required_pretax(post_tax_target_pct, years, tax_class, rules, person):
    """Pre-tax CAGR (%) whose value after exit tax, over `years`, matches money
    compounding at post_tax_target_pct. Ignores the LTCG exemption, so it errs
    on the demanding side."""
    growth = (1 + post_tax_target_pct / 100) ** years
    t = _exit_tax_rate(tax_class, years, rules, person)
    return ((1 + (growth - 1) / (1 - t)) ** (1 / years) - 1) * 100


def lots(rows):
    """Open FIFO lots per (source, folio_ref, isin): [{date, units, cost_per_unit}]."""
    out = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["date"]):
        key = (r["source"], r.get("folio_ref") or None, r["isin"])
        units = abs(float(r["units"] or 0))
        if r["type"] in UNITS_IN and units:
            out[key].append({"date": r["date"], "units": units,
                             "cost_per_unit": abs(float(r["amount"] or 0)) / units})
        elif r["type"] in UNITS_OUT:
            left = units
            q = out[key]
            while left > 1e-9:
                if not q:
                    raise ValueError(f"{key[2]}: sale on {r['date']} exceeds units held")
                take = min(left, q[0]["units"])
                q[0]["units"] -= take
                left -= take
                if q[0]["units"] <= 1e-9:
                    q.pop(0)
    return dict(out)


def _add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return dt.date(y, m, day)
        except ValueError:
            continue


def is_long_term(buy_date, as_of, tax_class, rules):
    if tax_class == "specified_debt":
        return False
    months = rules["equity"]["lt_months"] if tax_class == "equity" else rules["hybrid_gold_intl"]["lt_months"]
    return dt.date.fromisoformat(as_of) > _add_months(dt.date.fromisoformat(buy_date), months)


def unrealised(lot_map, nav_by_isin, as_of, rules, tax_class_by_isin, person, gf_nav_by_isin=None):
    gf_nav_by_isin = gf_nav_by_isin or {}
    gf_date = rules["grandfather_date"]
    by, buckets = {}, defaultdict(float)
    for key, q in lot_map.items():
        isin = key[2]
        nav = nav_by_isin.get(isin)
        if nav is None:
            continue
        cls = tax_class_by_isin.get(isin, "equity")
        st = lt = cost = 0.0
        units = 0.0
        for lot in q:
            c = lot["cost_per_unit"]
            if cls == "equity" and lot["date"] <= gf_date and isin in gf_nav_by_isin:
                c = max(c, min(gf_nav_by_isin[isin], nav))
            gain = (nav - c) * lot["units"]
            cost += lot["cost_per_unit"] * lot["units"]
            units += lot["units"]
            if is_long_term(lot["date"], as_of, cls, rules):
                lt += gain
            else:
                st += gain
        buckets[(cls, "st")] += st
        buckets[(cls, "lt")] += lt
        by[key] = {"tax_class": cls, "units": round(units, 4), "cost": round(cost, 2),
                   "value": round(units * nav, 2), "st_gain": round(st, 2), "lt_gain": round(lt, 2)}
    eq_st, eq_lt = buckets[("equity", "st")], buckets[("equity", "lt")]
    if eq_st < 0:           # a short-term loss sets off short- then long-term gains
        eq_lt += eq_st
        eq_st = 0.0
    exemption = rules["ltcg_exemption_inr"]
    eq_lt_taxable = max(0.0, eq_lt - exemption)
    m = person["ltcg_multiplier"]
    slab = person["effective_slab_pct"] / 100
    hy_st = max(0.0, buckets[("hybrid_gold_intl", "st")])
    hy_lt = max(0.0, buckets[("hybrid_gold_intl", "lt")])
    debt = max(0.0, buckets[("specified_debt", "st")] + buckets[("specified_debt", "lt")])
    tax_total = (eq_st * rules["equity"]["stcg_pct"] / 100 * m
                 + eq_lt_taxable * rules["equity"]["ltcg_pct"] / 100 * m
                 + hy_lt * rules["hybrid_gold_intl"]["ltcg_pct"] / 100 * m
                 + (hy_st + debt) * slab)
    value = sum(h["value"] for h in by.values())
    totals = {"equity_st_net": round(eq_st, 2), "equity_lt_net": round(eq_lt, 2),
              "equity_lt_taxable_after_exemption": round(eq_lt_taxable, 2),
              "exemption_assumed_unused_inr": exemption,
              "hybrid_gold_intl_st": round(hy_st, 2), "hybrid_gold_intl_lt": round(hy_lt, 2),
              "debt_gain": round(debt, 2), "tax_if_all_sold": round(tax_total, 2),
              "value": round(value, 2), "after_tax_value": round(value - tax_total, 2)}
    return {"by_holding": by, "totals": totals}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--tax-profile", required=True)
    i.add_argument("--person", required=True)
    i.add_argument("--cess", type=float, default=1.04)
    i.add_argument("--write", action="store_true")
    h = sub.add_parser("hurdle")
    h.add_argument("--years", type=float)
    for p in (i, h):
        p.add_argument("--root")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    if a.cmd == "import":
        rates = import_tax_profile(a.tax_profile, a.person, a.cess)
        if a.write:
            path = common.paths(root)["profile"]
            try:
                with open(path) as f:
                    prof = json.load(f)
            except FileNotFoundError:
                prof = {}
            prof["tax"] = {**rates, "from": f"advance-tax profile, person {a.person!r}",
                           "read_on": dt.date.today().isoformat()}
            prof["tax_profile_path"], prof["tax_person"] = a.tax_profile, a.person
            common.write_json(path, prof)
        print(json.dumps(rates, indent=1))
        return
    prof = common.load_profile(root)
    person = prof.get("tax")
    if not person:
        sys.exit("no tax rates in data/profile.json: run `tax.py import --write` first")
    years = a.years or prof["horizon_years"]
    rules = common.load_tax_rules()
    post = fd_hurdle(prof["fd_rate_pct"], person["effective_slab_pct"])
    out = {"fd_rate_pct": prof["fd_rate_pct"], "fd_rate_as_of": prof.get("fd_rate_as_of"),
           "post_tax_pct": round(post, 2), "years": years,
           "required_pretax_pct": {c: round(required_pretax(post, years, c, rules, person), 2)
                                   for c in ("equity", "hybrid_gold_intl", "specified_debt")},
           "equity_with_premium_pct": round(required_pretax(post, years, "equity", rules, person)
                                            + prof["equity_risk_premium_pts"], 2)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
