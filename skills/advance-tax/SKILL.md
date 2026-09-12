---
name: advance-tax
description: >-
  Compute advance income tax due for a given installment date (15 Jun / 15 Sep / 15 Dec / 15 Mar),
  from estimated FD interest, savings balance, dividends and house rent income. Use when the user
  asks what advance tax they owe, for a specific due date or "next installment", for themselves or
  for another person they name.
argument-hint: "[person] [due date | Q1-Q4] [FDR total] [savings balance] [dividends] [house rent] [already paid]"
allowed-tools:
  - Bash(python3 *compute_advance_tax.py*)
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

**Where the personal numbers live.** The skill ships statutory constants only — the due-date
schedule, the Section 24(a) standard deduction and the 4% cess. Every rate that depends on the
person (slab, FD and savings rates, surcharge band) comes from *their* `tax-profile.json`, which
lives in their own folder and never in the skills repo. Run the script from that folder, or pass
`--profile /path/to/tax-profile.json`. If a rate is missing the script says exactly which, and it
accepts them as flags for a one-off run that saves nothing.

## Step 1 — identify who and which due date

- **Person**: the key under `people` in their profile (`self` by default). If they name someone the
  profile does not have, do not guess a slab: derive the rates from what they give you — last
  year's ITR computation is the best source, a salary slip or Form 16 for the slab, an FD receipt
  for the deposit rate — then either pass those as flags for this run, or offer to add an entry to
  their profile. Never write those numbers into the skill folder.
- **Due date**: map "15 June" / "next due date" / a specific date to Q1-Q4. If today's date is
  between two due dates and the user says "the upcoming one" or doesn't specify, pick the next
  unpassed due date in the current FY.

## Step 2 — gather the four income inputs

Ask for (or take from the user's message):
1. **FDR total** — total FD principal across all fixed deposits (Rs).
2. **Savings balance** — total balance across savings accounts (Rs). This is taxed as *balance x
   assumed interest rate x tax%*, not the actual interest — the convention carried over from the
   spreadsheet this skill replaced.
3. **Dividends total** — estimated total dividend income for the full FY (Rs). Taxed directly at the
   slab rate (not discounted through an interest-rate factor — that was a bug in the pre-existing
   spreadsheet, fixed here per the user's confirmation on 12 Sep 2026).
4. **House rent total** — estimated total rental income for the full FY (Rs), before deductions.
   The 30% standard deduction (Section 24(a)) is applied automatically.
   If the user has home loan interest (Sec 24(b)) or municipal taxes paid to net off beyond the flat
   30%, ask and pass a reduced `--house-rent-total` (net of those) since the script only knows the
   flat statutory deduction.

If the user doesn't have fresh numbers for one of these, ask them for the source rather than
assuming: last year's ITR, a recent salary slip, an FD receipt, or their own spreadsheet. Say
clearly which numbers you carried forward from an older figure and which they gave you fresh.

Also ask **how much tax has already been paid this FY** — TDS credited so far (e.g. on FD interest,
salary) plus any advance tax installments already paid. This nets off in the formula; if omitted,
assume 0 and say so (this will overstate what's due now).

## Step 3 — compute

Run it from the user's own folder, the one holding their `tax-profile.json`:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/compute_advance_tax.py \
  --person <key from their profile> \
  --installment <Q1|Q2|Q3|Q4> \
  --fdr-total <N> \
  --savings-balance <N> \
  --dividends-total <N> \
  --house-rent-total <N> \
  --already-paid <N>
```

Never do this arithmetic yourself — always run the script. If the rates were gathered in Step 1
rather than read from a profile, pass them as flags (`--fd-tax-pct`, `--other-tax-pct`,
`--surcharge-multiplier`, `--fd-interest-rate`, `--savings-interest-rate`) and offer to save them
into the user's own `tax-profile.json` for next time. Never into the skill folder: it is a public
repo, and a slab rate is personal information.

## Step 4 — report

State the due date and amount due now, then the breakdown (FD / savings / dividend / house rent tax
components) so the user can sanity-check which bucket dominates. If `--already-paid` was assumed 0,
repeat that assumption plainly next to the number. Note that Sections 234B/234C interest applies to
shortfalls against this cumulative schedule — mention it only if the computed due-now amount is
being paid late or the user asks about a past due date.

Close with: *Not tax advice — verify figures with your CA before paying.*
