---
name: advance-tax
description: >-
  Compute advance income tax due for a given installment date (15 Jun / 15 Sep / 15 Dec / 15 Mar),
  from estimated FD interest, savings balance, dividends and house rent income. Use when the user
  asks what advance tax they owe, for a specific due date or "next installment", for themselves or
  a named person (e.g. a named person).
argument-hint: "[person] [due date | Q1-Q4] [FDR total] [savings balance] [dividends] [house rent] [already paid]"
allowed-tools:
  - Bash(python3 scripts/compute_advance_tax.py*)
  - Read
  - Edit
  - Glob
---

Request for this run: **$ARGUMENTS**

You are helping compute an advance tax installment for an individual (self-assessed "other sources"
income only — salary TDS is assumed already covered separately and folded into "already paid" if
the user gives it). The reference schedule (verified against ClearTax, Sep 2026) is Sec 208/211 of
the Income Tax Act, 1961 (renumbered 424/425 under the Income Tax Act 2025):

| Installment | Due date     | Cumulative % of estimated annual tax |
|-------------|--------------|---------------------------------------|
| Q1          | 15 June      | 15%                                    |
| Q2          | 15 September | 45%                                    |
| Q3          | 15 December  | 75%                                    |
| Q4          | 15 March     | 100%                                   |

`Advance tax due now = cum_pct x estimated annual tax on other-sources income - tax already paid this FY (TDS + prior installments)`

## Step 1 — identify who and which due date

- **Person**: `self` or another profile key (config keys in `config.json`). If the user names someone not in
  `config.json`, ask for their FD tax %, other-income tax % (slab), surcharge and cess multipliers
  before proceeding — do not guess a slab.
- **Due date**: map "15 June" / "next due date" / a specific date to Q1-Q4. If today's date is
  between two due dates and the user says "the upcoming one" or doesn't specify, pick the next
  unpassed due date in the current FY.

## Step 2 — gather the four income inputs

Ask for (or take from the user's message):
1. **FDR total** — total FD principal across all fixed deposits (Rs).
2. **Savings balance** — total balance across savings accounts (Rs). This is taxed as *balance x
   assumed interest rate x tax%*, not the actual interest — same convention as the user's existing
   `advanceTax.xlsx` ("Sheet A" / "Sheet B" sheets).
3. **Dividends total** — estimated total dividend income for the full FY (Rs). Taxed directly at the
   slab rate (not discounted through an interest-rate factor — that was a bug in the pre-existing
   spreadsheet, fixed here per the user's confirmation on 12 Sep 2026).
4. **House rent total** — estimated total rental income for the full FY (Rs), before deductions.
   `config.json`'s `house_rent_standard_deduction_pct` (30%, Section 24(a)) is applied automatically.
   If the user has home loan interest (Sec 24(b)) or municipal taxes paid to net off beyond the flat
   30%, ask and pass a reduced `--house-rent-total` (net of those) since the script only knows the
   flat statutory deduction.

If the user doesn't have fresh numbers for one of these, check
`<your advance-tax spreadsheet>` (sheets "Sheet A" / "Sheet B")
for the most recent quarter's figures as a starting estimate, and say clearly which numbers you
carried forward versus which the user gave you fresh.

Also ask **how much tax has already been paid this FY** — TDS credited so far (e.g. on FD interest,
salary) plus any advance tax installments already paid. This nets off in the formula; if omitted,
assume 0 and say so (this will overstate what's due now).

## Step 3 — compute

```
python3 scripts/compute_advance_tax.py \
  --person <person key> \
  --installment <Q1|Q2|Q3|Q4> \
  --fdr-total <N> \
  --savings-balance <N> \
  --dividends-total <N> \
  --house-rent-total <N> \
  --already-paid <N>
```

Never do this arithmetic yourself — always run the script. If a custom person's constants were
gathered in Step 1, pass them by temporarily adding an entry to `config.json` under `people`, or ask
the user whether to save it there permanently for reuse.

## Step 4 — report

State the due date and amount due now, then the breakdown (FD / savings / dividend / house rent tax
components) so the user can sanity-check which bucket dominates. If `--already-paid` was assumed 0,
repeat that assumption plainly next to the number. Note that Sections 234B/234C interest applies to
shortfalls against this cumulative schedule — mention it only if the computed due-now amount is
being paid late or the user asks about a past due date.

Close with: *Not tax advice — verify figures with your CA before paying.*
