# advance-tax

Computes advance income tax due for a given installment date, from estimated FD interest, savings
balance, dividends and house rent income.

Replaces the manual calculation previously done in `advanceTax.xlsx` ("Sheet A" / "Sheet B"
sheets). Two changes from that sheet, made deliberately (see `SKILL.md`):

- Dividends and house rent are taxed directly at slab rate, not discounted through the savings
  interest-rate factor (the old sheet's `(savings + dividends [+ rent]) x 3.5% x tax%` formula
  understated house rent tax by roughly the difference between a ~1% and ~31% effective rate).
- House rent gets the statutory 30% standard deduction (Section 24(a)) before tax.
- The amount due nets off tax actually paid this FY, rather than chaining off the previous
  installment's *computed* figure — the standard Sec 208/211 approach.

See `config.json` for the per-person constants (FD/other tax %, surcharge, cess) and
`scripts/compute_advance_tax.py` for the calculation.
