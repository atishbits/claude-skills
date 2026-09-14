# Output templates

Everything written goes to **the user's working folder**, never into this skill directory — it lives
in a public repo.

## 1. One file per schedule

If more than one person is being helped, use one subfolder per assessee and never let figures cross
between them.

```
00_Document_Review_and_Data_Inventory.md
ITR2_Schedule_Salary_conclusions.md
ITR2_Schedule_HP_conclusions.md
ITR2_Schedule_CG_conclusions.md
ITR2_Schedule_OS_conclusions.md
ITR2_Schedule_FA_conclusions.md
ITR2_SetOff_and_TaxesPaid_conclusions.md
ITR2_Tax_Computation_and_Regime_Comparison.md
ITR2_Final_Worksheet_and_Prefiling_Checklist.md
```

## 2. Mandatory structure of every conclusions file

```markdown
# ITR-2 Schedule <X> — Conclusions

- **Assessee:** <name>, PAN <PAN>
- **FY:** <fy> | **AY:** <ay> | **Regime:** <old/new>
- **Source docs:** <filenames used>
- **Last updated:** <YYYY-MM-DD>

## Computation

<every ITR line, its value, and its basis>

## Cross-check vs AIS / TIS / 26AS

<what ties out, what does not, and why>

## Flags to confirm before filing

<numbered, actionable>

## PENDING

<what is still missing and exactly where to get it>

## DECISION LOG

<date — decision taken — advice given — risk accepted>

*General help, not formal tax advice — CA review advised before filing.*
```

**Rules for the computation section:**

- Always show the **ITR line label** alongside the amount, so the user can type it straight into the
  portal.
- Always state the **basis** of each figure — which document, which page or section.
- **Never leave a number unexplained.**
- A schedule that does not apply still gets a file: one line saying so, and why.

## 3. The final worksheet

`assets/worksheet-template.md` is the shape of the Phase 10 deliverable: one section per ITR-2
schedule, each row labelled exactly as the portal labels it, the value to enter, and a checkbox
column — followed by the pre-submission checklist.

Copy it into the user's folder as `ITR2_Final_Worksheet_and_Prefiling_Checklist.md` and fill it from
the conclusions files. Do not fill it from memory of the earlier phases; read the files back.
