# portfolio-review

Reviews a long-term Indian equity portfolio. A Python layer pulls fundamentals, price history and
disclosures for every holding; the skill then researches the stocks you name and writes a
BUY / HOLD / SELL note per stock.

The framework is P/E judged against ROE and ROCE, placed on four signal rows, with a technical read
for the re-look price, an evidence layer (cash conversion, the ROCE trend, earnings against the
company's own history, shareholding, promoter pledge, insider dealing) and a book-level risk
section. `CHEATSHEET.md` explains all of it.

## Layout

Data lives under this skill's own `data/` folder, which the repo's `.gitignore` and pre-commit hook
keep out of git wholesale — nothing you put there or the skill writes there can end up committed by
an ordinary `git add`. It splits into two tiers, so it's clear at a glance what you gave the skill
versus what it fetched:

```
~/.claude/skills/portfolio-review -> <this folder>      installed once, for every project

data/                              yours — the only files you provide
  broker_holdings_<date>.csv         a plain broker export, or
  broker-portfolio-<date>.md         a lot-level broker export (adds buy dates for LTCG)
  slug-overrides.json              optional: {"SYMBOL-XX": "SLUG"} where your broker's symbol differs from the data source's
  notes.md                         local only: where the cloud copy lives
  .sync-base.json, .writer-id      local only: the last sync, and this copy's name in the logs
  skill-data/                      the skill's — fetched data and everything it writes
    .cache/                          local only: the per-ticker fetch cache
    snapshot-<date>.json             local only: the day's fundamentals snapshot
    digest.json                      a small per-ticker summary runs read before any note
    stocks/<TICKER>.md               one note per holding
    PORTFOLIO.md                     generated summary table
    entry-budgets.json, calendar.md
    ratings-ledger/, scan-history/   append-only logs, one file per copy per day
```

Everything not marked local only is also kept in cloud storage (below).

The root is chosen, in order, by `--root PATH`, then `$PORTFOLIO_ROOT`, then the working directory —
`SKILL.md` tells Claude to run from this checkout, so the working-directory default is what applies
day to day. If you'd rather keep your data in a folder outside this repo entirely (a little safer
still, since it means personal data is never in the same directory tree as tracked source at all,
gitignore notwithstanding), point every run at it with `--root /path/to/that/folder`
or `$PORTFOLIO_ROOT` — the same `data/` / `data/skill-data/` split applies there too.

## Setup

1. Python 3 with `requests`. `pdftotext` (poppler-utils) if you want guidance read from concall
   transcripts.
2. Install the skill for every project by linking this folder into your Claude skills directory:

   ```
   ln -s "$PWD/skills/portfolio-review" ~/.claude/skills/portfolio-review
   ```

   A symlink keeps the checkout as the single copy: `git pull` updates the skill in place. Copying
   the folder instead works too, and then updates have to be copied again.

### Two ways to use it

**Just rate a stock — no portfolio needed.** Nothing to set up beyond step 1:

```
python3 scripts/fetch_fundamentals.py --screen EXAMPLEA
```

Then ask Claude about it. `--screen` writes `data/skill-data/screen-<today>.json` and touches
nothing else. The portfolio-level parts of a review (position size, sector weight, what to swap)
simply do not apply, and the skill says so rather than inventing a book.

**Review your own holdings.** Put a broker export in `data/` as `broker_holdings_<date>.csv` (any
`*holdings*.csv` name works) with these columns:

```
Instrument,Qty.,Avg. cost,LTP,Invested,Cur. val,P&L,Net chg.
```

`holdings-template.csv` in this folder is a working example. A broker export with these columns
works as it is; any other needs its headers renamed to match. Only `Instrument` is truly required: with just
`Instrument` and `Qty.` you still get every rating, minus P&L and position weights.

If you want lot-level LTCG awareness (which quantity is already long-term, when the next lot turns
long-term, gains split by holding period), put a lot-level broker export in `data/` instead, named
`broker-portfolio-<date>.md` — see `broker-portfolio-template.md` for the format. The script reads
whichever file is newest; you don't need both.

Then `python3 scripts/fetch_fundamentals.py` builds `data/skill-data/snapshot-<today>.json` and
`data/skill-data/PORTFOLIO.md`, and in Claude Code you run `/portfolio-review TICKER ...` or just
ask about a holding.

A first full run of a few dozen holdings takes 10–15 minutes, mostly waiting out screener's rate limit.
Everything is cached per day afterwards, so later runs that day rebuild in under a second.

## Data sources

- **screener.in** for ratios, financials, cash flow, shareholding and concall links. Cached per
  ticker per day; it rate-limits under sustained fetching.
- **NSE** for promoter pledge, insider dealing and large-stake filings. Cached for a week, and
  fails soft: coverage is patchy by symbol, so a missing record is recorded as unknown rather than
  as nothing on file. `--no-nse` skips it.
- **Web search** at review time for analyst consensus, with rules in SKILL.md 3c for not trusting
  a search summary as a source.

Yahoo Finance and stooq are not used: neither returns usable data for NSE symbols from a plain
script.

## Cloud storage is the master copy

The skill's memory lives in a `portfolio-review/` folder in your cloud file storage, so Claude Code
on this machine and a Cowork session see the same notes, ratings, budgets and logs. The folder is
found by its marker file, `portfolio-review-sync.json`; keeping it below the folder that holds
`news-briefing-profile.json` lets news-briefing read the same broker export.

- **How it moves.** Claude moves files with the file-storage connector; `scripts/drive_sync.py`,
  which never touches the network, decides what moves. It compares each file's local copy, its
  cloud copy and the state at the last sync, so an unchanged file is never transferred and an edit
  made in the cloud is pulled rather than overwritten. Each run starts with a sync in (SKILL.md
  Step 0) and ends with a sync out (Step 5).
- **Conflicts.** A file changed in both places since the last sync: the newer copy wins and the
  other is kept beside it as `<name>.conflict-<date>.<ext>` for you to reconcile. The logs are one
  file per copy per day, so they never conflict.
- **What never goes up.** The fetch cache, snapshots, screens and shortlists. Scripts regenerate
  them, and moving files through the connector costs tokens on every byte.
- **Cheap on purpose.** A run reads `digest.json` instead of every note, pulls a full note only
  for a stock it re-rates, and `scripts/freshness.py` keeps research found in the last weeks
  (consensus, guidance, peers) from being searched again.
- **Deletions are not synced.** Remove a file in both places if you mean it.

First run on a machine: Step 0 finds no marker file, asks which folder to use, and uploads the
local copy.

### Installing in Cowork

Add this repository's marketplace (`atishbits/claude-skills`) under the plugin settings, install
`portfolio-review`, and connect your file-storage connector. If Cowork offers to work in a folder
on your computer, grant one: the skill keeps a full copy there and transfers only what changed.
Without one it works in a temporary folder and pulls only what each request needs.

Cowork runs the fetch scripts itself. If its sandbox cannot reach screener.in or NSE, it says so
and falls back to web search for figures.

## Keep your data out of git

Holdings, notes, snapshots and the generated `PORTFOLIO.md` are personal. This repo's `.gitignore`
already ignores this skill's `data/` folder wholesale, and the pre-commit hook double-checks staged
content for the same thing, so nothing under `data/` reaches git by accident — but colocating it
here at all is a convenience, not a requirement: `--root` (see Layout) keeps it out of this tree
entirely if you'd rather. If you point the skill at a folder of your own instead, apply the same
deny-by-default `.gitignore` there.

---

*Ratings are advisory. Not investment advice — verify prices and figures before acting.*
