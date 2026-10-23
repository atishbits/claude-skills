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
  old-data/                        local only: superseded exports; never synced or read
  skill-data/                      the skill's — fetched data and everything it writes
    .cache/                          local only: the per-ticker fetch cache
    snapshot-<date>.json             local only: the day's fundamentals snapshot
    digest.json                      a small per-ticker summary runs read before any note
    stocks/<TICKER>.md               one note per holding
    PORTFOLIO.md                     generated summary table
    entry-budgets.json, calendar.md
    sell-plans.json                  open sell plans, one per ticker
    realised-gains-FY<fy>.json       the year's realised gains, for tax planning (below)
    ratings-ledger/, scan-history/,  append-only logs, one file per copy per day
      realised-gains/
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

**Accounts at more than one broker.** Name each export after its broker — `alphabroker_holdings_<date>.csv`,
`betabroker-portfolio-<date>.md` — and the script reads the newest export of each and merges them: a stock
held at both becomes one position (total quantity, weighted average cost, every lot tagged with its
broker, and a per-broker quantity split). Realised gains in each lot-level export's Tax position section
add up across brokers.

Then `python3 scripts/fetch_fundamentals.py` builds `data/skill-data/snapshot-<today>.json` and
`data/skill-data/PORTFOLIO.md`, and in Claude Code you run `/portfolio-review TICKER ...` or just
ask about a holding.

A first full run of a few dozen holdings takes 10–15 minutes, mostly waiting out screener's rate limit.
Everything is cached per day afterwards, so later runs that day rebuild in under a second.

## Selling and realised gains

`sell-review.md` is the guide for selling, trimming, booking profit or reporting a sale. Two
scripts carry its arithmetic:

- **`scripts/sell_signals.py`** splits a stock's 3- and 6-month rise into the part from profit
  growth and the part from a higher P/E, places the P/E in the stock's own long-run band, runs the
  peak tests, and grades the case: none, watch, trim a third, or trim half. `TICKER` prints the full
  case, a staged plan (step 1 now, step 2 on a price trigger, a core kept), and for each demat
  account the lots FIFO would sell with gain, estimated tax and net, plus the break-even drop: how
  far the price could fall before waiting for the long-term rate stops paying. `--open-plan
  "sentence"` (with `--full-exit` for a deliberate exit) saves the plan to
  `data/skill-data/sell-plans.json`; `--close-plan` removes it; `--flags` prints one line per
  flagged holding. Every portfolio run puts the flags in `PORTFOLIO.md`'s "Worth a look".
- **`scripts/gains_log.py`** records the sales you report. `record TICKER QTY PRICE --date
  YYYY-MM-DD --account NAME [--charges N]` matches the sale FIFO against that account's lots and
  logs it as unconfirmed (charges are deductible sale expenses, not STT; a sale dated on or before
  that account's own export date is refused, since the export already has it). Each snapshot
  keeps every broker's export date and tax position under `exports`, so two brokers exported on
  different days are each judged by their own date. Account labels are compared stripped and
  lower-cased. `report [--fy 2026-27]`
  prints the year's totals and the unconfirmed entries. `reconcile PATH` matches the log against
  the broker's tax report (and lists as `unmatched` logged sales the report should have but does
  not) and `export [--fy]` writes the hand-off file.

Tax rates (20% short-term, 12.5% long-term, Rs 1,25,000 long-term exemption per year) are constants
in `scripts/tax_lots.py`; check them against the current Finance Act.

### Reconcile input

`reconcile` reads a CSV with one row per matched buy lot of a sale:

```
account,symbol,sell_date,qty,sell_price,buy_date,buy_price,gain,term,charges
```

`realised-gains-template.md` describes each column with an example. Which broker report to
download, and where, is personal and goes in your `data/notes.md`.

### The hand-off file

`export` writes `data/skill-data/realised-gains-FY<fy>.json` (e.g. `realised-gains-FY2026-27.json`)
so another tool can read the year's gains without reading this code:

```json
{
 "fy": "2026-27",
 "generated_at": "2026-10-23T04:00:00+00:00",
 "baseline": {"as_of": "2026-10-01", "stcg": 1000.0, "ltcg": 2000.0,
              "accounts": {"brokera": {"as_of": "2026-10-01", "stcg": 1000.0, "ltcg": 2000.0}},
              "note": "broker FY total to as_of; includes mutual funds where the broker reports them"},
 "sales": [{"date": "2026-10-20", "ticker": "STOCKA", "account": "brokera", "qty": 10.0,
            "stcg": 480.0, "ltcg": 0.0, "status": "unconfirmed", "in_baseline": false}],
 "totals": {"net_st": 1480.0, "net_lt": 2000.0, "exempt_used": 2000.0,
            "exempt_left": 123000.0, "tax": 296.0}
}
```

- `baseline` is the sum of each broker export's own realised total for the year, or `null` when no
  export has one for that year. `accounts` gives each account's figure and its own `as_of` (the
  top-level `as_of` is the oldest of them; an older snapshot without per-broker data shows one
  `*` entry covering every account). A plain CSV export has no baseline. It can include mutual
  funds.
- `sales` lists every logged sale in the year by date, with gains in rupees after charges.
  `status` is `unconfirmed` (logged, not yet matched to a broker report) or `confirmed`.
  `in_baseline` is true for a sale on or before its own account's `as_of`, which that account's
  baseline already counts; a sale at an account with no baseline is always added.
- `totals` is baseline plus every sale not in a baseline: net short- and long-term gain, exemption used
  and left, and the estimated tax. A net short-term loss is set off against long-term gains first.
  Advance tax counts a gain from the installment after it arises, which is why sales carry dates.

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
  Step 0) and ends with a sync out (Step 5). The script is shared with other skills: its master
  copy is `shared/scripts/drive_sync.py` at the top of this repository, and what this skill syncs
  is set in `scripts/drive-sync.json`.
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
