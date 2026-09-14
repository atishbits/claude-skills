#!/usr/bin/env python3
"""Deterministic Indian income tax calculator for ITR-2 preparation.

Single file, no dependencies. Rate tables are keyed by assessment year so a new
year is one edit -- keep them in step with references/08_rates_and_thresholds.md.

The skill routes *all* money arithmetic through this script. Nothing here is
personal: statutory rates and thresholds only.

    python3 tax_calc.py --regime new --ay 2026-27 --normal-income 1234567
    python3 tax_calc.py --compare --ay 2026-27 --normal-income 1234567 \
        --normal-income-old 1180000
    python3 tax_calc.py --selftest

Not tax advice. Verify against the Finance Act for the year being filed.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

INF = math.inf

# --------------------------------------------------------------------------
# Rate tables. One block per assessment year.
# --------------------------------------------------------------------------
#   slabs:     list of (upper limit of the band, rate). Last band is INF.
#   surcharge: list of (upper limit of total income, rate). Last band is INF.
#
# Capital gains rates are set by the section, not by the regime, so they sit
# outside the per-regime block.

RATES = {
    "2026-27": {
        "cess": 0.04,
        "special": {
            "stcg_111a": 0.20,          # listed equity/equity MF, STT paid
            "ltcg_112a": 0.125,         # above the annual exemption below
            "ltcg_112a_exemption": 125000,
            "ltcg_other": 0.125,        # sec 112, without indexation
            "winnings_115bb": 0.30,     # no rebate, no basic exemption relief
        },
        # Surcharge on tax attributable to 111A / 112 / 112A / dividend is
        # capped at this rate whatever the band says.
        "surcharge_cap_special": 0.15,
        "new": {
            "slabs": [
                (400000, 0.00),
                (800000, 0.05),
                (1200000, 0.10),
                (1600000, 0.15),
                (2000000, 0.20),
                (2400000, 0.25),
                (INF, 0.30),
            ],
            "basic_exemption": 400000,
            "std_deduction_salary": 75000,
            "rebate_87a": {"income_limit": 1200000, "max": 60000,
                           "marginal_relief": True},
            "surcharge": [
                (5000000, 0.00),
                (10000000, 0.10),
                (20000000, 0.15),
                (50000000, 0.25),
                (INF, 0.25),            # capped at 25% in the new regime
            ],
        },
        "old": {
            # Basic exemption varies with age; slabs are built in _old_slabs().
            "basic_exemption": {"default": 250000, "senior": 300000,
                                "super_senior": 500000},
            "std_deduction_salary": 50000,
            "rebate_87a": {"income_limit": 500000, "max": 12500,
                           "marginal_relief": False},
            "surcharge": [
                (5000000, 0.00),
                (10000000, 0.10),
                (20000000, 0.15),
                (50000000, 0.25),
                (INF, 0.37),
            ],
        },
    },
}

# Sec 234C: (label, cumulative % due, cumulative % that avoids interest,
#            months of interest)
ADVANCE_TAX_SCHEDULE = [
    ("15 Jun", 0.15, 0.12, 3),
    ("15 Sep", 0.45, 0.36, 3),
    ("15 Dec", 0.75, 0.75, 3),
    ("15 Mar", 1.00, 1.00, 1),
]


def _old_slabs(ay: str, age: int) -> list[tuple[float, float]]:
    """Old-regime slabs, shifted by the age-dependent basic exemption."""
    be = _old_basic_exemption(ay, age)
    slabs = [(be, 0.00)]
    if be < 500000:
        slabs.append((500000, 0.05))
    if be < 1000000:
        slabs.append((1000000, 0.20))
    slabs.append((INF, 0.30))
    return slabs


def _old_basic_exemption(ay: str, age: int) -> int:
    be = RATES[ay]["old"]["basic_exemption"]
    if age >= 80:
        return be["super_senior"]
    if age >= 60:
        return be["senior"]
    return be["default"]


def _slab_tax(income: float, slabs: list[tuple[float, float]]) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        if income <= lower:
            break
        tax += (min(income, upper) - lower) * rate
        lower = upper
    return tax


# --------------------------------------------------------------------------
# Inputs and result
# --------------------------------------------------------------------------

@dataclass
class Inputs:
    """All amounts in rupees, already net of the deductions that apply."""
    regime: str = "new"
    ay: str = "2026-27"
    age: int = 35
    normal_income: float = 0.0        # everything taxed at slab rates
    dividend_income: float = 0.0      # the dividend *portion of* normal_income
    ltcg_112a: float = 0.0            # before the annual exemption
    stcg_111a: float = 0.0
    ltcg_other: float = 0.0           # sec 112, without indexation
    special_rate_income: float = 0.0  # 115BB winnings etc.
    tds: float = 0.0
    advance_tax: float = 0.0
    tcs: float = 0.0
    self_assessment_tax: float = 0.0
    months_234b: int = 0
    paid_by_quarter: list[float] = field(default_factory=list)

    @property
    def total_income(self) -> float:
        return (self.normal_income + self.ltcg_112a + self.stcg_111a
                + self.ltcg_other + self.special_rate_income)

    @property
    def taxes_paid(self) -> float:
        return self.tds + self.advance_tax + self.tcs + self.self_assessment_tax


@dataclass
class Result:
    inputs: Inputs
    total_income: float = 0.0
    slab_tax: float = 0.0
    special_tax: dict = field(default_factory=dict)
    basic_exemption_adjusted: float = 0.0
    tax_before_rebate: float = 0.0
    rebate: float = 0.0
    rebate_marginal_relief: float = 0.0
    surcharge_rate: float = 0.0
    surcharge: float = 0.0
    surcharge_marginal_relief: float = 0.0
    cess: float = 0.0
    total_liability: float = 0.0
    net_payable: float = 0.0
    interest_234b: float = 0.0
    interest_234c: float = 0.0
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Core computation
# --------------------------------------------------------------------------

def _apply_basic_exemption(inp: Inputs, basic_exemption: float):
    """A resident may set unused basic exemption against 111A/112/112A gains.

    Applied to the highest-taxed component first, which is the assessee's
    choice and the one that minimises tax. Sec 115BB winnings get no such
    relief.
    """
    unused = max(0.0, basic_exemption - inp.normal_income)
    adjusted, remaining = {}, unused
    for key, amount in (("stcg_111a", inp.stcg_111a),
                        ("ltcg_other", inp.ltcg_other),
                        ("ltcg_112a", inp.ltcg_112a)):
        take = min(remaining, amount)
        adjusted[key] = amount - take
        remaining -= take
    return adjusted, unused - remaining


def _compute_core(inp: Inputs, normal_income: float, components: dict,
                  rates: dict) -> tuple[float, dict]:
    """Tax before surcharge: slab tax plus each special-rate component."""
    sp = rates["special"]
    if inp.regime == "new":
        slabs = rates["new"]["slabs"]
    else:
        slabs = _old_slabs(inp.ay, inp.age)

    slab_tax = _slab_tax(normal_income, slabs)

    taxable_112a = max(0.0, components["ltcg_112a"] - sp["ltcg_112a_exemption"])
    special_tax = {
        "stcg_111a": components["stcg_111a"] * sp["stcg_111a"],
        "ltcg_112a": taxable_112a * sp["ltcg_112a"],
        "ltcg_other": components["ltcg_other"] * sp["ltcg_other"],
        "winnings_115bb": inp.special_rate_income * sp["winnings_115bb"],
    }
    return slab_tax, special_tax


def _rebate(inp: Inputs, total_income: float, slab_tax: float,
            rates: dict) -> tuple[float, float, list[str]]:
    """Sec 87A rebate and its marginal relief.

    The rebate runs against tax on income taxed at slab rates only -- never
    against 111A / 112A / 115BB tax.
    """
    cfg = rates[inp.regime]["rebate_87a"]
    notes: list[str] = []
    if total_income <= cfg["income_limit"]:
        rebate = min(cfg["max"], slab_tax)
        return rebate, 0.0, notes

    if not cfg["marginal_relief"]:
        return 0.0, 0.0, notes

    # Just above the threshold: tax on the slab-rate income may not exceed the
    # amount by which total income crosses the limit.
    excess = total_income - cfg["income_limit"]
    if slab_tax > excess:
        relief = slab_tax - excess
        notes.append(
            f"87A marginal relief applied: total income exceeds "
            f"{_r(cfg['income_limit'])} by {_r(excess)}, so tax at slab rates "
            f"is held down to that excess.")
        return 0.0, relief, notes
    return 0.0, 0.0, notes


def _surcharge_rate(total_income: float, bands: list[tuple[float, float]]) -> float:
    for upper, rate in bands:
        if total_income <= upper:
            return rate
    return bands[-1][1]


def _surcharge_threshold(total_income: float,
                         bands: list[tuple[float, float]]) -> float | None:
    """The band floor the income has just crossed, for marginal relief."""
    crossed = None
    for upper, _rate in bands:
        if total_income > upper:
            crossed = upper
    return crossed


def _tax_pre_surcharge_at(inp: Inputs, target_income: float,
                          rates: dict) -> float:
    """Tax before surcharge on a hypothetical total income of `target_income`.

    Used only for surcharge marginal relief. The shortfall is shaved off the
    slab-rate income first, then off the special-rate components, which keeps
    the composition as close to the real return as the model allows.
    """
    shave = inp.total_income - target_income
    normal = max(0.0, inp.normal_income - shave)
    shave -= inp.normal_income - normal
    comps = {"stcg_111a": inp.stcg_111a, "ltcg_other": inp.ltcg_other,
             "ltcg_112a": inp.ltcg_112a}
    for key in ("ltcg_112a", "ltcg_other", "stcg_111a"):
        take = min(shave, comps[key])
        comps[key] -= take
        shave -= take

    hypo = Inputs(regime=inp.regime, ay=inp.ay, age=inp.age,
                  normal_income=normal,
                  special_rate_income=max(0.0, inp.special_rate_income - shave))
    basic_exemption = (rates["new"]["basic_exemption"] if inp.regime == "new"
                       else _old_basic_exemption(inp.ay, inp.age))
    unused = max(0.0, basic_exemption - normal)
    for key in ("stcg_111a", "ltcg_other", "ltcg_112a"):
        take = min(unused, comps[key])
        comps[key] -= take
        unused -= take

    slab_tax, special_tax = _compute_core(hypo, normal, comps, rates)
    rebate, relief, _ = _rebate(hypo, target_income, slab_tax, rates)
    return slab_tax + sum(special_tax.values()) - rebate - relief


def compute(inp: Inputs) -> Result:
    if inp.ay not in RATES:
        raise SystemExit(
            f"No rate table for AY {inp.ay}. Add one to RATES (and to "
            f"references/08_rates_and_thresholds.md) after checking the "
            f"Finance Act -- do not compute from a neighbouring year.")
    if inp.regime not in ("new", "old"):
        raise SystemExit("--regime must be 'new' or 'old'")
    if inp.dividend_income > inp.normal_income:
        raise SystemExit(
            "--dividend-income is the dividend portion *of* --normal-income; "
            "it cannot exceed it.")

    rates = RATES[inp.ay]
    res = Result(inputs=inp)
    res.total_income = inp.total_income

    basic_exemption = (rates["new"]["basic_exemption"] if inp.regime == "new"
                       else _old_basic_exemption(inp.ay, inp.age))
    components, adjusted = _apply_basic_exemption(inp, basic_exemption)
    res.basic_exemption_adjusted = adjusted
    if adjusted:
        res.notes.append(
            f"{_r(adjusted)} of unused basic exemption set against special-rate "
            f"capital gains (resident individual).")

    res.slab_tax, res.special_tax = _compute_core(
        inp, inp.normal_income, components, rates)
    res.tax_before_rebate = res.slab_tax + sum(res.special_tax.values())

    res.rebate, res.rebate_marginal_relief, notes = _rebate(
        inp, res.total_income, res.slab_tax, rates)
    res.notes.extend(notes)
    tax_after_rebate = (res.tax_before_rebate - res.rebate
                        - res.rebate_marginal_relief)

    # --- surcharge, with the 15% cap on 111A / 112 / 112A / dividend ---
    bands = rates[inp.regime]["surcharge"]
    res.surcharge_rate = _surcharge_rate(res.total_income, bands)
    if res.surcharge_rate > 0:
        cap = rates["surcharge_cap_special"]
        capped_rate = min(res.surcharge_rate, cap)

        dividend_tax = 0.0
        if inp.dividend_income and inp.normal_income:
            # Proportionate share of the slab tax. The utility slices dividend
            # at the top of the stack; where the cap materially binds, check
            # this figure against the utility's own computation.
            dividend_tax = res.slab_tax * (inp.dividend_income
                                           / inp.normal_income)
            res.notes.append(
                "Surcharge cap on dividend uses the average-rate (proportionate) "
                "share of slab tax -- cross-check against the utility if the cap "
                "materially binds.")
        capped_base = (res.special_tax["stcg_111a"] + res.special_tax["ltcg_112a"]
                       + res.special_tax["ltcg_other"] + dividend_tax)
        uncapped_base = tax_after_rebate - capped_base
        res.surcharge = max(0.0, uncapped_base) * res.surcharge_rate \
            + capped_base * capped_rate
        if capped_rate < res.surcharge_rate and capped_base:
            res.notes.append(
                f"Surcharge on 111A/112/112A/dividend tax capped at "
                f"{cap:.0%} against a band rate of {res.surcharge_rate:.0%}.")

        threshold = _surcharge_threshold(res.total_income, bands)
        if threshold is not None:
            ceiling = (_tax_pre_surcharge_at(inp, threshold, rates)
                       + (res.total_income - threshold))
            if tax_after_rebate + res.surcharge > ceiling:
                res.surcharge_marginal_relief = (
                    tax_after_rebate + res.surcharge - ceiling)
                res.surcharge -= res.surcharge_marginal_relief
                res.notes.append(
                    f"Surcharge marginal relief of "
                    f"{_r(res.surcharge_marginal_relief)} applied at the "
                    f"{_r(threshold)} threshold.")

    res.cess = (tax_after_rebate + res.surcharge) * rates["cess"]
    res.total_liability = tax_after_rebate + res.surcharge + res.cess

    # --- interest ---
    assessed = max(0.0, res.total_liability - inp.tds - inp.tcs)
    if inp.months_234b and inp.advance_tax < 0.9 * assessed:
        shortfall = max(0.0, assessed - inp.advance_tax)
        res.interest_234b = shortfall * 0.01 * inp.months_234b
    if inp.paid_by_quarter:
        res.interest_234c = _interest_234c(assessed, inp.paid_by_quarter)

    res.net_payable = (res.total_liability + res.interest_234b
                       + res.interest_234c - inp.taxes_paid)
    return res


def _interest_234c(assessed: float, paid: list[float]) -> float:
    """paid[] is cumulative advance tax paid by each due date."""
    total = 0.0
    for i, (_label, due_pct, safe_pct, months) in enumerate(ADVANCE_TAX_SCHEDULE):
        cum = paid[i] if i < len(paid) else 0.0
        if cum < safe_pct * assessed:
            shortfall = max(0.0, due_pct * assessed - cum)
            total += shortfall * 0.01 * months
    return total


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _r(x: float) -> str:
    """Indian-format rupees, no decimals."""
    neg = x < 0
    s = f"{abs(x):.0f}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "Rs " + s


def _row(label: str, value: str, width: int = 52) -> str:
    return f"  {label:<{width}}{value:>16}"


def render(res: Result) -> str:
    inp = res.inputs
    rates = RATES[inp.ay]
    out = []
    out.append("")
    out.append(f"  ITR tax computation - AY {inp.ay}, {inp.regime} regime, age {inp.age}")
    out.append("  " + "-" * 68)

    out.append("  INCOME")
    out.append(_row("Income taxed at slab rates", _r(inp.normal_income)))
    if inp.dividend_income:
        out.append(_row("  of which dividend", _r(inp.dividend_income)))
    for label, amount in (("STCG u/s 111A", inp.stcg_111a),
                          ("LTCG u/s 112A", inp.ltcg_112a),
                          ("LTCG u/s 112 (other)", inp.ltcg_other),
                          ("Income at special rates (115BB etc.)",
                           inp.special_rate_income)):
        if amount:
            out.append(_row(label, _r(amount)))
    out.append(_row("Total income", _r(res.total_income)))
    if res.basic_exemption_adjusted:
        out.append(_row("Unused basic exemption set against CG",
                        _r(res.basic_exemption_adjusted)))

    out.append("")
    out.append("  TAX")
    slabs = (rates["new"]["slabs"] if inp.regime == "new"
             else _old_slabs(inp.ay, inp.age))
    lower = 0.0
    for upper, rate in slabs:
        if inp.normal_income <= lower:
            break
        band = min(inp.normal_income, upper) - lower
        span = (f"above {_r(lower)}" if upper == INF
                else f"{_r(lower)} to {_r(upper)}")
        out.append(_row(f"  slab {rate:>5.1%} ({span})", _r(band * rate)))
        lower = upper
    out.append(_row("Tax at slab rates", _r(res.slab_tax)))
    sp = rates["special"]
    labels = {
        "stcg_111a": f"STCG 111A @ {sp['stcg_111a']:.1%}",
        "ltcg_112a": (f"LTCG 112A @ {sp['ltcg_112a']:.1%} "
                      f"(after {_r(sp['ltcg_112a_exemption'])} exemption)"),
        "ltcg_other": f"LTCG 112 @ {sp['ltcg_other']:.1%}",
        "winnings_115bb": f"115BB @ {sp['winnings_115bb']:.0%}",
    }
    for key, amount in res.special_tax.items():
        if amount:
            out.append(_row("  " + labels[key], _r(amount)))
    out.append(_row("Tax before rebate", _r(res.tax_before_rebate)))
    if res.rebate:
        out.append(_row("Less: rebate u/s 87A", "-" + _r(res.rebate)[3:]))
    if res.rebate_marginal_relief:
        out.append(_row("Less: 87A marginal relief",
                        "-" + _r(res.rebate_marginal_relief)[3:]))
    if res.surcharge or res.surcharge_rate:
        out.append(_row(f"Surcharge @ {res.surcharge_rate:.0%} (band)",
                        _r(res.surcharge)))
    out.append(_row(f"Health & education cess @ {rates['cess']:.0%}", _r(res.cess)))
    out.append(_row("TOTAL TAX LIABILITY", _r(res.total_liability)))

    out.append("")
    if inp.months_234b or inp.paid_by_quarter:
        out.append("  INTEREST (estimate)")
        if inp.months_234b:
            out.append(_row(f"234B ({inp.months_234b} months)",
                            _r(res.interest_234b)))
        if inp.paid_by_quarter:
            out.append(_row("234C (deferment of instalments)",
                            _r(res.interest_234c)))
        if not (res.interest_234b or res.interest_234c):
            out.append("    (nil: TDS/TCS already covers the assessed tax)")
    else:
        out.append("  Interest not computed: pass --months-234b and/or "
                   "--paid-q1..--paid-q4.")

    out.append("")
    out.append("  TAXES PAID")
    for label, amount in (("TDS", inp.tds), ("Advance tax", inp.advance_tax),
                          ("TCS", inp.tcs),
                          ("Self-assessment tax", inp.self_assessment_tax)):
        out.append(_row(label, _r(amount)))
    out.append(_row("Total taxes paid", _r(inp.taxes_paid)))

    out.append("")
    rounded = math.copysign(round(abs(res.net_payable) / 10) * 10,
                            res.net_payable)
    verdict = "PAYABLE" if rounded > 0 else "REFUNDABLE"
    out.append(_row(f"NET {verdict} (rounded, sec 288B)", _r(abs(rounded))))

    if res.notes:
        out.append("")
        out.append("  NOTES")
        for n in res.notes:
            out.append(f"    - {n}")

    out.append("")
    out.append("  General help, not formal tax advice - CA review advised "
               "before filing.")
    out.append("")
    return "\n".join(out)


def render_comparison(new_res: Result, old_res: Result) -> str:
    out = [render(new_res), render(old_res), ""]
    out.append("  " + "-" * 68)
    delta = old_res.total_liability - new_res.total_liability
    better = "new" if delta > 0 else "old"
    out.append(_row("Total liability - new regime", _r(new_res.total_liability)))
    out.append(_row("Total liability - old regime", _r(old_res.total_liability)))
    out.append(_row(f"Difference ({better} regime is cheaper)", _r(abs(delta))))
    out.append("")
    out.append("  The two regimes take different deductions, so this comparison "
               "is only")
    out.append("  as good as the income figures fed in. Pass --normal-income-old "
               "with the")
    out.append("  old-regime figure (Chapter VI-A, HRA, 50,000 standard "
               "deduction) if it")
    out.append("  differs from --normal-income.")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Self-tests
# --------------------------------------------------------------------------

def _selftest() -> int:
    failures = []

    def check(name, got, want, tol=1.0):
        if abs(got - want) > tol:
            failures.append(f"{name}: got {got:.2f}, want {want:.2f}")

    # 1. Below the rebate threshold: liability nil.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=700000))
    check("below-rebate slab tax", r.slab_tax, 15000)
    check("below-rebate rebate", r.rebate, 15000)
    check("below-rebate liability", r.total_liability, 0)

    # 2. Just above the threshold: marginal relief, not a cliff.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=1210000))
    check("just-above slab tax", r.slab_tax, 61500)
    check("just-above marginal relief", r.rebate_marginal_relief, 51500)
    check("just-above liability", r.total_liability, 10400)

    # ... and the cliff it prevents: 10 more rupees of income must not cost
    # more than 10 rupees of tax.
    r2 = compute(Inputs(regime="new", ay="2026-27", normal_income=1210010))
    if r2.total_liability - r.total_liability > 11:
        failures.append("marginal relief leaves a cliff at the 87A threshold")

    # 3. Surcharge band boundaries: at the floor, no surcharge; one rupee over,
    #    marginal relief holds tax+surcharge to the ceiling.
    at = compute(Inputs(regime="new", ay="2026-27", normal_income=5000000))
    check("50L slab tax", at.slab_tax, 1080000)
    check("50L surcharge", at.surcharge, 0)
    check("50L liability", at.total_liability, 1123200)

    for floor in (5000000, 10000000, 20000000, 50000000):
        base = compute(Inputs(regime="new", ay="2026-27", normal_income=floor))
        over = compute(Inputs(regime="new", ay="2026-27",
                              normal_income=floor + 100))
        step = over.total_liability - base.total_liability
        if step > 110:
            failures.append(
                f"surcharge marginal relief missing at {floor}: "
                f"100 rupees more income costs {step:.0f} in tax")

    # 4. 112A-heavy case where the 15% surcharge cap binds.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=5000000,
                       ltcg_112a=20000000))
    check("cap case slab tax", r.slab_tax, 1080000)
    check("cap case 112A tax", r.special_tax["ltcg_112a"], 2484375)
    check("cap case surcharge rate", r.surcharge_rate, 0.25, tol=1e-9)
    check("cap case surcharge", r.surcharge, 1080000 * 0.25 + 2484375 * 0.15)

    # 5. Unused basic exemption set against capital gains.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=100000,
                       stcg_111a=500000))
    check("BE adjusted", r.basic_exemption_adjusted, 300000)
    check("BE adjusted 111A tax", r.special_tax["stcg_111a"], 200000 * 0.20)

    # 6. 87A never runs against special-rate tax.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=400000,
                       ltcg_112a=500000))
    check("rebate vs 112A", r.rebate, 0)
    check("112A tax stands", r.special_tax["ltcg_112a"],
          (500000 - 125000 - 0) * 0.125, tol=1.0)

    # 7. Old regime, senior citizen exemption.
    r = compute(Inputs(regime="old", ay="2026-27", age=65,
                       normal_income=1000000))
    check("old senior slab tax", r.slab_tax, (500000 - 300000) * 0.05
          + (1000000 - 500000) * 0.20)

    # 8. Sec 234C on a fully deferred payment.
    r = compute(Inputs(regime="new", ay="2026-27", normal_income=2000000,
                       paid_by_quarter=[0, 0, 0, 0]))
    assessed = r.total_liability
    want = (0.15 * assessed * 0.03 + 0.45 * assessed * 0.03
            + 0.75 * assessed * 0.03 + 1.00 * assessed * 0.01)
    check("234C fully deferred", r.interest_234c, want)

    if failures:
        print("SELFTEST FAILED")
        for f in failures:
            print("  x " + f)
        return 1
    print("selftest: all checks passed")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Indian income tax computation for ITR-2 preparation.")
    p.add_argument("--selftest", action="store_true",
                   help="run the built-in unit tests and exit")
    p.add_argument("--regime", default="new", choices=["new", "old"])
    p.add_argument("--compare", action="store_true",
                   help="compute both regimes and print the delta")
    p.add_argument("--ay", default="2026-27", help="assessment year, e.g. 2026-27")
    p.add_argument("--age", type=int, default=35)
    p.add_argument("--normal-income", type=float, default=0.0,
                   help="income taxed at slab rates, net of deductions")
    p.add_argument("--normal-income-old", type=float, default=None,
                   help="the same figure on old-regime deductions, for --compare")
    p.add_argument("--dividend-income", type=float, default=0.0,
                   help="dividend portion OF --normal-income (surcharge cap only)")
    p.add_argument("--ltcg-112a", type=float, default=0.0,
                   help="gross, before the annual exemption")
    p.add_argument("--stcg-111a", type=float, default=0.0)
    p.add_argument("--ltcg-other", type=float, default=0.0,
                   help="sec 112 LTCG, without indexation")
    p.add_argument("--special-rate-income", type=float, default=0.0,
                   help="115BB winnings etc.")
    p.add_argument("--tds", type=float, default=0.0)
    p.add_argument("--advance-tax", type=float, default=0.0)
    p.add_argument("--tcs", type=float, default=0.0)
    p.add_argument("--self-assessment-tax", type=float, default=0.0)
    p.add_argument("--months-234b", type=int, default=0,
                   help="months from 1 April of the AY to payment")
    for q in range(1, 5):
        p.add_argument(f"--paid-q{q}", type=float, default=None,
                       help=f"cumulative advance tax paid by due date {q}")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    quarters = [getattr(args, f"paid_q{q}") for q in range(1, 5)]
    quarters = [0.0 if v is None else v for v in quarters] \
        if any(v is not None for v in quarters) else []

    def build(regime, normal):
        return Inputs(
            regime=regime, ay=args.ay, age=args.age, normal_income=normal,
            dividend_income=args.dividend_income, ltcg_112a=args.ltcg_112a,
            stcg_111a=args.stcg_111a, ltcg_other=args.ltcg_other,
            special_rate_income=args.special_rate_income, tds=args.tds,
            advance_tax=args.advance_tax, tcs=args.tcs,
            self_assessment_tax=args.self_assessment_tax,
            months_234b=args.months_234b, paid_by_quarter=quarters)

    if args.compare:
        old_income = (args.normal_income_old if args.normal_income_old is not None
                      else args.normal_income)
        print(render_comparison(compute(build("new", args.normal_income)),
                                compute(build("old", old_income))))
    else:
        print(render(compute(build(args.regime, args.normal_income))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
