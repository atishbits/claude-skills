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
rates, your surcharge band — lives in a `tax-profile.json` that is never committed. It sits in a
working folder of yours with the rest of the skill's state:

```
tax-profile.json      your rates, one entry per person
ledger.md             optional: what you paid, when, and what is still due
bond-interest.json    optional: the year's bond interest and the TDS on it
notes.md              optional: the skill's local memory, e.g. where each of your inputs comes from
```

The working folder is `$ADVANCE_TAX_DIR` if you set it. Otherwise, with the skill symlinked from a
checkout of this repo, it is the skill's own `data/` folder if that exists; the repo's `.gitignore`
excludes it and the pre-commit hook refuses it. Installed as a plugin, the skill never writes in its
own folder, because an update replaces it: it asks where to keep the files and offers to set
`ADVANCE_TAX_DIR`. `python3 scripts/compute_advance_tax.py --where` prints which folder it would use.

1. Copy `tax-profile-template.json` to `tax-profile.json` in that folder and fill it in. The
   template says where to read each number from: last year's ITR computation for the slab and
   surcharge, an FD receipt for the deposit rate, a salary slip or Form 16 if the ITR is not to
   hand.
2. Run the script from anywhere; it finds the profile in the working folder on its own:

   ```
   python3 ~/.claude/skills/advance-tax/scripts/compute_advance_tax.py \
     --person self --installment Q2 \
     --fdr-total N --savings-balance N --dividends-total N --house-rent-total N --already-paid N
   ```

   To keep the profile elsewhere, pass `--profile /path/to/tax-profile.json`, set `$TAX_PROFILE`,
   or run from the folder that holds it; those are tried first, in that order.

## Where it runs

It works in Claude Code and in Cowork, always on a local working folder:

- **Claude Code:** the folder above.
- **Cowork:** a folder inside the one you shared with the session. With no folder shared, a
  temporary one, which does not outlast the session.

**A copy in your cloud storage.** With a file-storage connector you can keep the working folder's
four files in one cloud folder too, so a run elsewhere picks up the same ledger. With a lasting
folder the skill touches cloud storage only when you ask: "pull" copies the cloud versions down,
"sync" uploads yours. With a temporary folder it pulls at the start of the run and pushes once at
the end, after recording the run in the ledger, so only the final state goes back and Claude Code
can carry on from it after a "pull". Nothing else in the folder moves, so a spreadsheet or backups
kept there stay local. It never changes a folder's sharing.

What moves is decided by `scripts/drive_sync.py`, which compares each file's local copy, its cloud
copy and the last sync, so an unchanged file is never moved and an edit on one side is never
overwritten by the other; a file changed on both sides is kept twice for you to reconcile. The
script is shared with other skills: its master copy is `shared/scripts/drive_sync.py` at the top of
this repository, and `scripts/drive-sync.json` sets what this skill syncs.

**Bond interest.** If you hold bonds, pass the year's gross interest and the TDS on it with
`--bond-interest-total N --bond-tds N`, or `--bond-interest-file` with the `bond-interest.json`
in your working folder. The
interest is taxed at your slab with surcharge and cess, and the TDS is taken off the result, so
do not count that TDS again in `--already-paid`. The file needs only this much, however you
produce it:

```json
{"as_of": "2026-10-01", "total": {"interest_gross": 12000.0, "tds": 1200.0}}
```

Where your own figures come from (a platform's statement, another tool) is personal: write it in
`notes.md` in your working folder, which the skill reads first, not in this repo.

Tests: `python3 -m unittest discover -s tests -p 'test_*.py'` from `scripts/`.

For a one-off, skip the file entirely and pass the rates as flags: `--fd-tax-pct`,
`--other-tax-pct`, `--surcharge-multiplier`, `--fd-interest-rate`, `--savings-interest-rate`.
Nothing is written to disk. If a rate is missing the script names it rather than guessing a slab.

---

*Not tax advice — verify figures with your CA before paying.*
