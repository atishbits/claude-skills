# Phase 7 — Set-off, carry-forward, Schedule AL, taxes paid

## 1. Order of operations

1. **Schedule CYLA** — current-year loss set-off across heads. House-property loss against other
   heads is capped at **₹2,00,000**; the excess carries forward. **Capital losses never set off
   against other heads.**
2. **Schedule BFLA** — brought-forward losses of earlier years set off against current-year income,
   head-wise.
3. **Schedule CFL** — losses to be carried forward, year-wise. **Verify the current year's loss
   actually lands here**, not merely in the source schedule.

## 2. Prior-year verification — mandatory step

Open the **full prior-year ITR PDF** (not the acknowledgement) and check:

- **Schedule CFL** — all zeros means no brought-forward losses; if not zero, transcribe the year-wise
  amounts.
- **Regime used** — Chapter VI-A all zero is a strong indicator of the new regime.
- **Schedule FA** — was it filed? Check continuity of accounts and opening values against this year's
  A1/A2/A3 rows.
- **Filing date vs due date** — a late prior-year return means its losses were never eligible to be
  carried forward, whatever the CFL shows.

## 3. Schedule AL (Assets & Liabilities)

Mandatory when **total income exceeds ₹50,00,000**. Report the **cost** — not market value — of:

- immovable property
- jewellery / bullion
- vehicles, aircraft, boats
- financial assets: bank balances, shares & securities, insurance, loans given, cash in hand

and the corresponding liabilities. Foreign assets already disclosed in Schedule FA still belong here
if within scope.

## 4. Taxes paid schedules

| Schedule | Source | Check |
|----------|--------|-------|
| TDS 1 (salary) | Form 16 Part A / 26AS | TAN, amount |
| TDS 2 (other than salary) | 26AS | Deductor TAN, amount, and the head it relates to |
| TDS 3 (26QB / 26QC — property, rent) | 26AS | |
| TCS | 26AS | **206CQ on LRS remittance is claimable** |
| Advance tax & self-assessment tax | 26AS / AIS Part B3 / challans | BSR code, challan serial, date, amount |

**Rule: every credit claimed must exist in 26AS.** Exclude entries relating to other assessment years
— a prior-year self-assessment payment, or an old demand appearing in AIS, is not this year's credit.

## 5. Other schedules to consider

- **Schedule EI** — exempt income: PPF interest, exempt LTCG, agricultural income, dividends exempt
  under a DTAA, gifts from relatives.
- **Schedule VDA** — virtual digital assets. 30%, no deductions, no loss set-off.
- **Schedule SPI** — income of spouse/minor to be clubbed.
- **Schedule 5A** — Portuguese Civil Code (Goa) apportionment.
- **Unlisted equity shares held** — mandatory disclosure table if applicable.
- **Directorship in a company** — mandatory disclosure table if applicable.
- **Bank accounts** — all accounts held during the year; nominate one **pre-validated** account for
  the refund.

## 6. Output

`ITR2_SetOff_and_TaxesPaid_conclusions.md`, in the structure required by `10_output_templates.md`.
It must carry: the CYLA/BFLA/CFL numbers, the Schedule AL applicability decision (with the total
income figure that drove it), and a line-by-line list of every tax credit claimed with its 26AS
match.
