#!/usr/bin/env python3
"""What the funds cost: value-weighted expense ratio and its rupee drag, the
gap to an index fund on the same benchmark, the exit load on units still
inside their load period, and how many years a cheaper fund needs to repay
the cost of switching into it.
"""
import datetime as dt
import math


def weighted_er(holdings, meta):
    known = [(h, meta.get(h["isin"], {}).get("expense_ratio_pct")) for h in holdings]
    missing = sorted({h["isin"] for h, er in known if er is None})
    rows = [(h, float(er)) for h, er in known if er is not None]
    value = sum(float(h["value"]) for h, _ in rows)
    cost = sum(float(h["value"]) * er / 100 for h, er in rows)
    by = [{"isin": h["isin"], "er_pct": er, "annual_cost_inr": round(float(h["value"]) * er / 100, 2),
           "share_of_cost_pct": round(100 * float(h["value"]) * er / 100 / cost, 1) if cost else 0.0}
          for h, er in rows]
    bases = {meta[h["isin"]].get("er_basis") for h, _ in rows if meta[h["isin"]].get("er_basis")}
    return {"weighted_er_pct": round(100 * cost / value, 4) if value else None,
            "annual_cost_inr": round(cost, 2), "by_fund": sorted(by, key=lambda r: -r["annual_cost_inr"]),
            "missing_er": missing, "mixed_basis": len(bases) > 1}


def vs_index(er_pct, proxy_er_pct):
    if er_pct is None or proxy_er_pct is None:
        return None
    return round(er_pct - proxy_er_pct, 4)


def switch_breakeven(value, exit_load_inr, tax_inr, r_pct, er_old_pct, er_new_pct):
    """Years until a cheaper fund has earned back exit load + tax paid to move:
    n = ln(V/(V-C)) / ln((1+r-e_new)/(1+r-e_old)). None if the new fund is not cheaper."""
    if exit_load_inr is None or tax_inr is None:
        return None
    c = exit_load_inr + tax_inr
    if c <= 0:
        return 0
    if er_new_pct >= er_old_pct or c >= value:
        return None
    r, eo, en = r_pct / 100, er_old_pct / 100, er_new_pct / 100
    return math.log(value / (value - c)) / math.log((1 + r - en) / (1 + r - eo))


def exit_load_inr(lots, as_of, exit_load_pct, exit_load_days, nav):
    """Rupees of exit load on units still inside the load period; None when
    the load or its period is not recorded (unknown, not zero)."""
    if exit_load_pct is None:
        return None
    if not exit_load_pct:
        return 0
    if not exit_load_days:
        return None
    cutoff = dt.date.fromisoformat(as_of) - dt.timedelta(days=int(exit_load_days))
    units = sum(l["units"] for l in lots if dt.date.fromisoformat(l["date"]) > cutoff)
    return round(units * nav * exit_load_pct / 100, 2)
