# mutual-fund-review

A Claude skill that reviews Indian mutual-fund holdings held across several platforms and
statements, and answers: how is each fund doing against its index and against "the same money in
the index on the same dates", does it beat a bank FD after tax, what does it cost, and what tax
sits in it. Every number comes from a tested Python script (standard library only); Claude reads
the output and words the verdicts.

## What it reads

| Input | How it arrives | Script |
|---|---|---|
| Portal holdings and transactions | `capture/capture.js` run in a logged-in tab, driven by a per-portal adapter JSON kept in your own `data/adapters/` | `ingest_capture.py --capture` |
| Consolidated account statement (detailed, with transactions) | A PDF you put in `data/raw/` (unlocked first with the pdf-unlock skill if protected) | `ingest_cas.py --pdf` |
| Anything else | A CSV in the format of `manual-import-template.csv` | `ingest_capture.py --csv` |
| Fund facts (category, benchmark, expense ratio) | Filled by Claude from public pages, dated | `fund_meta.py` |
| NAVs | AMFI's daily file and mfapi.in, cached | `nav.py` |
| Your tax rates | Your advance-tax skill profile | `tax.py import` |

Nothing personal ships with the skill. Your data lives in a working folder's `data/` (gitignored):
`--root`, else `$MF_ROOT`, else this folder's own `data/` in a checkout. `data/notes.md` records
which platforms you use and where sibling skills keep their data; the tracked files name none.

## What it produces

`data/skill-data/analysis-<date>.json` (every figure) and `data/skill-data/PORTFOLIO.md` (a dated
scorecard with a glossary). Per fund: value, XIRR, the same cash flows in the benchmark, 1/3/5-year
returns against the benchmark, rolling 3-year win rate and median lead, expense ratio and its gap
to an index fund, and flags (`keeps_fee`, `fails_fee_test`, `below_fd_hurdle_rolling`, …).
Portfolio: totals per source, weighted expense ratio and its rupee cost, unrealised short- and
long-term gains with the tax if everything were sold, and the after-tax FD hurdle.

## Cloud copy

`scripts/drive-sync.json` and `references/cloud_sync.md` keep `data/` in your cloud storage, so the
Claude app and Claude Code work from the same data. Statement PDFs only ever come down.

## Install

From this repository's marketplace (`marketplace.json`), plugin `mutual-fund-review`.

## Tests

```
cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'
```

Fixtures are synthetic (invented funds and numbers). The CAS parser is tested on a synthetic
statement in the common registrar layout; check it against a real statement before relying on it.

## Coming next

Allocation against targets including direct stocks, bonds and FDs; tax harvesting using the shared
yearly exemption; new-money, SIP and lump-sum planners; a verdict ledger (Plan 2). Look-through to
company fundamentals, overlap, market-cap split and the valuation-tilt backtest (Plan 3).
