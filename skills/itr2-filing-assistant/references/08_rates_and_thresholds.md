# Rates & thresholds

**Figures below are for AY 2026-27 (FY 2025-26). Before using them for any other year, verify
against the current Finance Act.** Add a new dated section per AY rather than editing an existing
one in place — a filing for an earlier year must still be able to read the rates that applied then.

The same tables are encoded in `scripts/tax_calc.py`, keyed by AY string. If you change one, change
both, and run `python3 scripts/tax_calc.py --selftest`.

---

## AY 2026-27 (FY 2025-26)

### New regime slabs u/s 115BAC — the default

| Total income | Rate |
|---|---|
| Up to ₹4,00,000 | Nil |
| ₹4,00,001 – ₹8,00,000 | 5% |
| ₹8,00,001 – ₹12,00,000 | 10% |
| ₹12,00,001 – ₹16,00,000 | 15% |
| ₹16,00,001 – ₹20,00,000 | 20% |
| ₹20,00,001 – ₹24,00,000 | 25% |
| Above ₹24,00,000 | 30% |

- **Standard deduction (salary): ₹75,000.**
- **Rebate u/s 87A: up to ₹60,000**, where total income ≤ ₹12,00,000. **Not available against income
  taxed at special rates** (112A / 111A / 115BB). **Marginal relief applies** just above the
  threshold.
- **Chapter VI-A: not available**, except 80CCD(2) (employer NPS contribution) and 80CCH.
- **Family pension deduction: ₹25,000.**
- Interest on a self-occupied house property is **not** deductible.

### Old regime slabs (individual below 60)

Nil up to ₹2,50,000 · 5% to ₹5,00,000 · 20% to ₹10,00,000 · 30% above.

- Standard deduction ₹50,000; rebate u/s 87A ₹12,500 where total income ≤ ₹5,00,000; full
  Chapter VI-A available.
- Basic exemption: **₹3,00,000** for a senior citizen (60+), **₹5,00,000** for a super senior (80+).

### Surcharge on income tax

| Total income | Old regime | New regime |
|---|---|---|
| > ₹50L ≤ ₹1cr | 10% | 10% |
| > ₹1cr ≤ ₹2cr | 15% | 15% |
| > ₹2cr ≤ ₹5cr | 25% | 25% |
| > ₹5cr | 37% | **25% (capped)** |

- Surcharge on the tax attributable to **111A, 112, 112A and dividend** components is **capped at
  15%**.
- **Marginal relief applies at each threshold** — the calculator implements it; do not compute
  surcharge by hand.

### Health & education cess

**4%** on (tax + surcharge).

### Other thresholds

- 112A LTCG exemption: **₹1,25,000**
- House-property loss set-off cap: **₹2,00,000**
- Schedule AL trigger: total income above **₹50,00,000**
- Taxable EPF interest threshold: **₹2,50,000** (₹5,00,000 where the employer makes no contribution)
- Loss carry-forward: **8 years**
- Black Money Act penalty **₹10,00,000**, with a **₹20,00,000** non-immovable de-minimis from
  1-Oct-2024

### Due dates — non-audit individual

- Original return: **31 July of the AY**
- Belated / revised: **31 December of the AY**
- Updated return (ITR-U): up to **48 months** from the end of the AY, with additional tax
- **Filing after the due date forfeits carry-forward of losses** — other than house-property loss and
  unabsorbed depreciation

### Interest

- **234A** — late filing: 1% per month on unpaid tax
- **234B** — advance tax paid < 90% of assessed tax: 1% per month
- **234C** — deferment of instalments. Cumulative targets: **15 Jun 15% · 15 Sep 45% · 15 Dec 75% ·
  15 Mar 100%**

---

## Using the calculator

```
python3 scripts/tax_calc.py --regime new --ay 2026-27 \
  --normal-income 1234567 --ltcg-112a 0 --stcg-111a 0 --ltcg-other 0 \
  --dividend-income 0 --special-rate-income 0 \
  --tds 0 --advance-tax 0 --tcs 0 --age 35
```

- `--compare` runs both regimes and prints the delta. That is the Phase 8 deliverable.
- `--dividend-income` is the dividend **portion of** `--normal-income` (not additional income); it is
  needed only so the 15% surcharge cap can be applied correctly.
- `--paid-q1 … --paid-q4` enable the 234C estimate; `--months-234b` enables the 234B estimate.
- `--selftest` runs the built-in unit tests.

Never hand-compute slab tax, rebate, marginal relief, surcharge or cess. Route it through the script.
