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
2. Export your holdings as `zerodha_holdings_<date>.csv` in the project root, with the columns
   `Instrument, Qty., Avg. cost, LTP, Invested, Cur. val, P&L, Net chg.` Any broker export works
   if you rename the columns to match.
3. `python3 scripts/fetch_fundamentals.py` builds `data/snapshot-<today>.json` and `PORTFOLIO.md`.
4. In Claude Code: `/portfolio-review TICKER ...`, or just ask about a holding.

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
