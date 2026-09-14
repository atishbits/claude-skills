# Phase 2 — Schedule S (Salary)

## 1. Mapping

| ITR line | Source | Notes |
|----------|--------|-------|
| 1 Gross salary | Form 16 Part B | Split into 1a / 1b / 1c below |
| 1a Salary u/s 17(1) | Form 16 | Basic + allowances |
| 1b Perquisites u/s 17(2) | Form 16 + Form 12BA | **RSU/ESOP perquisite lands here** |
| 1c Profits in lieu u/s 17(3) | Form 16 | Severance etc. |
| 2 Total gross salary | sum | Must match AIS "TDS-Annexure II (SAL)" and 26AS |
| 3 Allowances exempt u/s 10 | Form 16 | HRA/LTA = 0 under the new regime |
| 3a Relief u/s 89A | Form 10EE | Foreign retirement accounts only |
| 4 Net salary | 2 − 3 | |
| 5 Deduction u/s 16 | | 16(ia) standard deduction: **₹75,000 new regime / ₹50,000 old** (AY 2026-27). 16(ii) entertainment and 16(iii) professional tax: **old regime only** |
| 6 Income chargeable under Salaries | 4 − 5 | Must tie to Form 16 line 6 |

## 2. Procedure

1. Read **Form 16 Part B line by line**. Do not trust prefill.
2. **Confirm the regime from Form 16**: look for *"Whether opting out of section 115BAC(1A)?"* —
   "No" means the new regime.
3. **Known prefill bug — always check.** The portal sometimes shows deduction u/s 16 as ₹50,000 even
   when the new regime is selected. Correcting it to ₹75,000 is a real ₹25,000 × marginal-rate
   saving. Verify this line every time.
4. **Reverse-engineer Form 16's own tax computation** (tax + surcharge + cess should equal the TDS)
   to independently confirm the regime and the surcharge band. Route the arithmetic through
   `scripts/tax_calc.py`.
5. **Multiple employers** → add all Form 16s together. The standard deduction is claimed **once**,
   not per employer. Watch for each employer having given the full standard deduction and basic
   exemption separately — that under-deducts TDS and leaves tax payable at filing.
6. **Cross-check gross salary** against AIS (TDS-Annexure II) and 26AS section 192. A mismatch is a
   flag to investigate, never something to average.

## 3. Things that commonly go wrong

- The RSU/ESOP perquisite is already inside gross salary via Form 12BA. **Do not report it again**
  under Other Sources or anywhere else.
- Exempt allowances (HRA, LTA) claimed under the new regime — they are not available.
- Professional tax deducted and shown on the payslip, then claimed under the new regime — 16(iii) is
  old-regime only.
- Employer NPS contribution u/s 80CCD(2) *is* available in the new regime; employee 80CCD(1B) is
  not.

## 4. Questions to ask

1. How many employers this FY? Any change of job?
2. Does Form 12BA show a perquisite? What is it — RSU/ESOP, car, accommodation, something else?
3. Any arrears or advance salary this year (Sec 89 relief / Form 10E)?
4. Any exempt allowances claimed (only relevant if old regime)?
5. Any employer NPS contribution u/s 80CCD(2)?

## 5. Output

`ITR2_Schedule_Salary_conclusions.md`, in the structure required by `10_output_templates.md`.
