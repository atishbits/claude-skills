# advance-tax

Computes advance income tax due for a given installment date, from estimated FD interest, savings
balance, dividends and house rent income.

Replaces a manual spreadsheet calculation. Three changes from that sheet, made deliberately (see
`SKILL.md`):

- Dividends and house rent are taxed directly at slab rate, not discounted through the savings
  interest-rate factor (the old sheet's `(savings + dividends [+ rent]) x 3.5% x tax%` formula
  understated house rent tax by roughly the difference between a ~1% and ~31% effective rate).
- House rent gets the statutory 30% standard deduction (Section 24(a)) before tax.
- The amount due nets off tax actually paid this FY, rather than chaining off the previous
  installment's *computed* figure — the standard Sec 208/211 approach.

## Your numbers stay yours

This repo holds statutory constants only: the due-date schedule, the Section 24(a) deduction and
the 4% cess, all in `config.json`. Anything personal — your slab rate, your bank's FD and savings
rates, your surcharge band — lives in a `tax-profile.json` in **your own folder**, which this repo
never sees.

1. Copy `tax-profile-template.json` somewhere private and fill it in. The template says where to
   read each number from: last year's ITR computation for the slab and surcharge, an FD receipt for
   the deposit rate, a salary slip or Form 16 if the ITR is not to hand.
2. Run the script from that folder, or point at the profile explicitly:

   ```
   python3 ~/.claude/skills/advance-tax/scripts/compute_advance_tax.py \
     --person self --installment Q2 \
     --fdr-total N --savings-balance N --dividends-total N --house-rent-total N --already-paid N
   ```

   `--profile /path/to/tax-profile.json` or `$TAX_PROFILE` work from anywhere.

For a one-off, skip the file entirely and pass the rates as flags: `--fd-tax-pct`,
`--other-tax-pct`, `--surcharge-multiplier`, `--fd-interest-rate`, `--savings-interest-rate`.
Nothing is written to disk. If a rate is missing the script names it rather than guessing a slab.

---

*Not tax advice — verify figures with your CA before paying.*
