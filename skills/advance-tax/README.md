# advance-tax

Computes advance income tax due for a given installment date, from estimated FD interest, savings
balance, dividends, house rent income and bond interest.

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
rates, your surcharge band — lives in a `tax-profile.json` that is never committed. By default it
sits in the skill's own `data/` folder, which the repo's `.gitignore` excludes and the pre-commit
hook refuses, the same layout the other skills here use:

```
data/
  tax-profile.json      your rates, one entry per person
  ledger.md             optional: what you paid, when, and what is still due
  bond-interest.json    optional: the year's bond interest, written by wint-wealth's fy_interest.py
```

1. Copy `tax-profile-template.json` to `data/tax-profile.json` and fill it in. The template says where to
   read each number from: last year's ITR computation for the slab and surcharge, an FD receipt for
   the deposit rate, a salary slip or Form 16 if the ITR is not to hand.
2. Run the script from anywhere; it finds `data/tax-profile.json` on its own:

   ```
   python3 ~/.claude/skills/advance-tax/scripts/compute_advance_tax.py \
     --person self --installment Q2 \
     --fdr-total N --savings-balance N --dividends-total N --house-rent-total N --already-paid N
   ```

   To keep the profile elsewhere, pass `--profile /path/to/tax-profile.json`, set `$TAX_PROFILE`,
   or run from the folder that holds it; those are tried first, in that order.

**Bond interest.** If you hold bonds, pass the year's gross interest and the TDS on it with
`--bond-interest-total N --bond-tds N`, or `--bond-interest-file data/bond-interest.json`. The
interest is taxed at your slab with surcharge and cess, and the TDS is taken off the result, so
do not count that TDS again in `--already-paid`. The `wint-wealth` skill writes the file from its
Master Report: `python3 scripts/fy_interest.py --out <this skill>/data/bond-interest.json`.

Tests: `python3 -m unittest discover -s tests -p 'test_*.py'` from `scripts/`.

For a one-off, skip the file entirely and pass the rates as flags: `--fd-tax-pct`,
`--other-tax-pct`, `--surcharge-multiplier`, `--fd-interest-rate`, `--savings-interest-rate`.
Nothing is written to disk. If a rate is missing the script names it rather than guessing a slab.

---

*Not tax advice — verify figures with your CA before paying.*
