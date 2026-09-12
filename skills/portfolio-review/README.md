# portfolio-review

Reviews a long-term Indian equity portfolio. A Python layer pulls fundamentals, price history and
disclosures for every holding; the skill then researches the stocks you name and writes a
BUY / HOLD / SELL note per stock.

The framework is P/E judged against ROE and ROCE, placed on four signal rows, with a technical read
for the re-look price, an evidence layer (cash conversion, the ROCE trend, earnings against the
company's own history, shareholding, promoter pledge, insider dealing) and a book-level risk
section. `CHEATSHEET.md` explains all of it.

## Layout

The skill expects to run from a project folder that holds your own data, with the scripts at the
project root:

```
<your project>/
  .claude/skills/portfolio-review/    SKILL.md, note-template.md, new-ideas.md (from this folder)
  scripts/                            fetch_fundamentals.py, nse_disclosures.py, close_on.py
  CHEATSHEET.md
  zerodha_holdings_<date>.csv         your broker export — never commit this
  stocks/                             one note per holding, written by the skill
  data/                               daily snapshots and the fetch cache
  PORTFOLIO.md                        generated summary table
```

`SKILL.md` calls the scripts as `python3 scripts/fetch_fundamentals.py`, so they belong at the
project root rather than inside the skill folder.

## Setup

1. Python 3 with `requests`. `pdftotext` (poppler-utils) if you want guidance read from concall
   transcripts.
2. Copy `SKILL.md`, `note-template.md` and `new-ideas.md` into
   `<your project>/.claude/skills/portfolio-review/`, and `scripts/` and `CHEATSHEET.md` to the
   project root.

### Two ways to use it

**Just rate a stock — no portfolio needed.** Nothing to set up beyond step 1:

```
python3 scripts/fetch_fundamentals.py --screen TITAN
```

Then ask Claude about it. `--screen` writes `data/screen-<today>.json` and touches nothing else.
The portfolio-level parts of a review (position size, sector weight, what to swap) simply do not
apply, and the skill says so rather than inventing a book.

**Review your own holdings.** Put a broker export in the project root as
`zerodha_holdings_<date>.csv` (any `*holdings*.csv` name works) with these columns:

```
Instrument,Qty.,Avg. cost,LTP,Invested,Cur. val,P&L,Net chg.
```

`holdings-template.csv` in this folder is a working example — Zerodha's own export already matches,
and other brokers need the headers renamed. Only `Instrument` is truly required: with just
`Instrument` and `Qty.` you still get every rating, minus P&L and position weights.

Then `python3 scripts/fetch_fundamentals.py` builds `data/snapshot-<today>.json` and
`PORTFOLIO.md`, and in Claude Code you run `/portfolio-review TICKER ...` or just ask about a
holding.

A first full run of ~70 holdings takes around 15 minutes, mostly waiting out screener's rate limit.
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

## Keep your data out of git

Holdings, notes, snapshots and the generated `PORTFOLIO.md` are personal. Use a deny-by-default
`.gitignore` in your project that opts in only the tool files.

---

*Ratings are advisory. Not investment advice — verify prices and figures before acting.*
