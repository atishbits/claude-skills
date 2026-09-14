# Phase 5 — Schedule OS (Income from Other Sources)

Runs **after** Capital Gains, because the CG output determines what must be excluded from here.

## 1. Reconciliation principle

The source of truth for domestic passive income is the **TIS "Processed by System" column** — it is
already deduplicated across SFT and TDS reporting, and it is what drives portal prefill.

- Use **AIS line items** to build the breakup.
- Use **TIS** for the totals.
- Use **26AS** for the TDS credits.

## 2. Section 1 mapping

| Line | Field | Build from |
|------|-------|-----------|
| 1a | Dividends, gross | TIS dividend total; AIS SFT-015 + TDS 194 line items for the company-wise breakup |
| 1b | Interest, gross | sum of b(i) + b(ii) + b(iii) |
| 1b(i) | Savings bank interest | Per-bank savings interest certificates |
| 1b(ii) | Interest on deposits (bank / PO / co-op) | FD interest + **taxable EPF interest** (§4) |
| 1b(iii) | Interest — others | Interest on securities/NCDs u/s 193, income tax refund interest u/s 244A, P2P/bond interest, **foreign interest** |
| 1c | Rental from machinery / plant / building | Rare |
| 1d | Income u/s 56(2)(x) | Gifts > ₹50,000 from non-relatives; property below stamp value |
| 1e | Any other income | Securitisation trust income (194LBC); family pension (with the 1/3 or ₹25,000 deduction — ₹25,000 in the new regime); etc. |

**Foreign dividends** go under 1a and **foreign interest** under 1b(iii) — taxable for a resident at
slab rates whether or not repatriated. They also need Schedule FSI (and TR + Form 67 if foreign tax
was paid). See `05_foreign_assets_and_income.md`.

## 3. Sections 2–10

- **2 — income at special rates.** Winnings/lottery u/s 115BB (30% flat), unexplained income u/s
  115BBE. **Capital gains never go here** — they go to Schedule CG.
- **3 — deductions u/s 57.** Interest on money borrowed to earn the income; 50% of family pension
  (capped). **80TTA / 80TTB are Chapter VI-A, not Sec 57** — never put them here, and they are
  unavailable in the new regime.
- **8 — income from owning race horses.** Separate, with its own loss rules.
- **10 — quarterly breakup.** Required for dividend, and for any income where 234C relief is claimed.
  Populate from dated entries in 26AS / the demat statement.
  - **Known prefill bug:** the portal often dumps the entire annual dividend into the "Upto 15/6"
    bucket. Fix it.
  - Where exact dates are unavailable, note that the AIS *"reported on"* date is the **reporting**
    date, not the receipt date. Make a documented best-guess split that **ties exactly to line 1a**,
    and say in the conclusions file that it is a best guess and why.

## 4. Taxable EPF interest — recurring, easily missed

- Since FY 2021-22, interest on the **employee's own** EPF contribution exceeding **₹2,50,000** in a
  year is taxable (₹5,00,000 threshold where the employer makes no contribution).
- EPFO usually deducts TDS u/s 194A (10%) on the taxable portion and reports it in AIS/26AS.
- Report the **EPFO-certified taxable interest figure exactly**, under 1b(ii). It must match the
  amount against which the 194A TDS credit appears in 26AS. **Do not recompute it downward.**
- TDS is a prepayment, not final tax — the balance is taxed at the assessee's marginal rate.
- Employer-contribution interest and the non-excess portion are exempt and are not reported.

## 5. Do-not-misplace list — copy this into every OS conclusions file

- Salary → the Salary head, not OS.
- Sale of shares / MF units → Schedule CG, not OS.
- REIT / InvIT pass-through (194LBA) → its own component-wise treatment, not a lump into OS.
- SFT-006 credit card spend, SFT-005 time-deposit purchase, SFT-004/012 property purchase →
  **informational entries in AIS, not income.** Never report them as income.
- TCS on LRS (206CQ) → a **tax credit**, not income.

## 6. Questions to ask

1. List every bank where you held a savings account or an FD this FY.
2. Do you have an EPF account with employee contribution above ₹2.5L this year?
3. Any bonds, NCDs, P2P lending, or securitisation trust income?
4. Any gift above ₹50,000 from a non-relative?
5. Any income tax refund received last year? *(Interest u/s 244A on it is taxable.)*
6. Do you have a demat dividend statement with payout dates, for the quarterly split?

## 7. Output

`ITR2_Schedule_OS_conclusions.md`, in the structure required by `10_output_templates.md`.
