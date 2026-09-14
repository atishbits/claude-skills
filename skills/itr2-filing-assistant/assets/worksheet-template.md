# ITR-2 Final Worksheet — AY <ay> (FY <fy>)

- **Assessee:** <name>, PAN <PAN>
- **Regime:** <old / new>
- **Prepared from:** the conclusions files in this folder
- **Last updated:** <YYYY-MM-DD>

Every row below is labelled as the portal labels it. Type the value in, then tick it.

---

## Schedule S — Salary

| ✔ | ITR line | Value (₹) | Basis |
|---|----------|-----------|-------|
| ☐ | 1a Salary u/s 17(1) | | Form 16 Part B |
| ☐ | 1b Perquisites u/s 17(2) | | Form 12BA |
| ☐ | 1c Profits in lieu u/s 17(3) | | |
| ☐ | 2 Total gross salary | | |
| ☐ | 3 Allowances exempt u/s 10 | | 0 under the new regime |
| ☐ | 5 Deduction u/s 16(ia) | | ₹75,000 new / ₹50,000 old |
| ☐ | 6 Income chargeable under Salaries | | ties to Form 16 line 6 |

## Schedule HP — House Property

One block per property.

| ✔ | ITR line | Value (₹) | Basis |
|---|----------|-----------|-------|
| ☐ | Property 1 — let out / self-occupied | | |
| ☐ | a Gross rent (full property) | | |
| ☐ | c Municipal tax paid | | receipt dated |
| ☐ | Ownership % | | co-owner named with PAN |
| ☐ | g 30% deduction u/s 24(a) | | 30% of the share |
| ☐ | h Interest u/s 24(b) — own share | | |
| ☐ | Income / (loss) from house property | | |

## Schedule CG — Capital Gains

| ✔ | ITR line | Value (₹) | Basis |
|---|----------|-----------|-------|
| ☐ | STCG u/s 111A | | |
| ☐ | LTCG u/s 112A (before ₹1.25L exemption) | | |
| ☐ | 112A schedule: consolidated row entered | | ISIN INNOTREQUIRD / CONSOLIDATED |
| ☐ | LTCG — foreign shares (12.5%, no indexation) | | Rule 115 conversion |
| ☐ | STCG — other, at slab | | |
| ☐ | Quarterly breakup entered | | for 234C |
| ☐ | Losses to carry forward | | must also appear in CFL |

## Schedule OS — Other Sources

| ✔ | ITR line | Value (₹) | Basis |
|---|----------|-----------|-------|
| ☐ | 1a Dividends, gross (incl. foreign) | | TIS total |
| ☐ | 1b(i) Savings bank interest | | per-bank certificates |
| ☐ | 1b(ii) Interest on deposits (incl. taxable EPF interest) | | EPFO certificate |
| ☐ | 1b(iii) Interest — others (incl. 244A, foreign) | | |
| ☐ | 3 Deductions u/s 57 | | not 80TTA/80TTB |
| ☐ | 10 Quarterly breakup — sums exactly to 1a | | |

## Schedule FA — Foreign Assets (calendar year 1 Jan – 31 Dec <cy>)

| ✔ | Table | Row | Basis |
|---|-------|-----|-------|
| ☐ | A1 | Foreign bank accounts — peak & closing | 31-Dec statement |
| ☐ | A2 | Custodial accounts — one per broker of record | US entity name & address |
| ☐ | A3 | One row per issuer, lots aggregated | initial / peak / closing distinct |
| ☐ | B/C/D/E | Property, other assets, signing authority, trusts | |
| ☐ | | FX convention recorded | SBI TT buying rate |

## Schedules FSI / TR / Form 67

| ✔ | Item | Value | Basis |
|---|------|-------|-------|
| ☐ | FSI — country code, TIN, head, income, foreign tax, relief, DTAA article | | US = 002 |
| ☐ | TR — relief u/s 90/90A vs 91 | | |
| ☐ | **Form 67 filed** — acknowledgement no. | | hard blocker for FTC |

## Schedules CYLA / BFLA / CFL

| ✔ | Item | Value (₹) | Basis |
|---|------|-----------|-------|
| ☐ | CYLA — HP loss set off (cap ₹2,00,000) | | |
| ☐ | BFLA — brought-forward set off | | prior-year CFL |
| ☐ | CFL — losses carried forward, year-wise | | |

## Schedule AL — if total income > ₹50L

| ✔ | Item | Cost (₹) |
|---|------|----------|
| ☐ | Immovable property | |
| ☐ | Jewellery / bullion | |
| ☐ | Vehicles | |
| ☐ | Financial assets | |
| ☐ | Liabilities | |

## Taxes paid

| ✔ | Item | Value (₹) | 26AS match |
|---|------|-----------|------------|
| ☐ | TDS 1 — salary (TAN) | | ☐ |
| ☐ | TDS 2 — other than salary (TAN) | | ☐ |
| ☐ | TCS — incl. 206CQ on LRS | | ☐ |
| ☐ | Advance tax (BSR, challan, date) | | ☐ |
| ☐ | Self-assessment tax | | ☐ |

## Part B-TI / Part B-TTI

| ✔ | Item | Value (₹) | Basis |
|---|------|-----------|-------|
| ☐ | Gross total income | | sum of heads |
| ☐ | Total income | | |
| ☐ | Tax at slab / special rates | | `tax_calc.py` |
| ☐ | Rebate u/s 87A | | |
| ☐ | Surcharge (band, 15% cap on 111A/112/112A/dividend) | | |
| ☐ | Cess 4% | | |
| ☐ | Interest 234A / 234B / 234C | | |
| ☐ | **Net payable / refundable** | | |

---

## Pre-submission checklist

- ☐ Regime selected correctly in the utility
- ☐ All TDS/TCS credits claimed and matching 26AS
- ☐ Form 67 filed (if claiming FTC)
- ☐ AIS feedback submitted for any incorrect entry
- ☐ Schedule CFL shows the current year's loss
- ☐ Schedule FA complete and on the calendar-year basis
- ☐ Schedule AL filled (if income > ₹50L)
- ☐ Preview PDF reviewed line by line against the conclusions files
- ☐ Bank account pre-validated for the refund
- ☐ Self-assessment tax paid, challan entered, **and the return re-validated after payment**
- ☐ Filing on or before the due date
- ☐ **e-Verify within 30 days of filing** (Aadhaar OTP / net banking / DSC) — an unverified return is
  not a filed return

---

*General help, not formal tax advice — CA review advised before filing.*
