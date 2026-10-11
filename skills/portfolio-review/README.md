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
  skill-data/                      the skill's — fetched data and everything it writes
    .cache/                          the per-ticker fetch cache
    snapshot-<date>.json             the day's fundamentals snapshot
    stocks/<TICKER>.md               one note per holding
    PORTFOLIO.md                     generated summary table
    from-cowork/                     files fetched from the cloud mirror's inbox (optional, below)
  drive-mirror/                    the optional cloud mirror's OAuth client, sign-in token and state
```

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

## Optional: a copy in Google Drive

The skill's data lives on one machine, so a Claude session elsewhere (Cowork, the mobile app)
cannot see it. `scripts/drive_mirror.py` keeps a copy of the outputs in a Drive folder of your
choosing, and brings back what another session leaves for it. The skill works without this.

- **Pushed** on every run, changed files only, each overwritten in place: `PORTFOLIO.md`,
  `stocks/*.md`, `ratings-ledger.jsonl`, `entry-budgets.json`, `calendar.md`, and a `README.md`
  that tells the reader how the folder works. `--with-snapshot` adds the newest snapshot as
  `snapshot-latest.json`. This machine stays the source of truth; an edit made to a mirrored file
  is overwritten by the next run.
- **Pulled** on every run: new files in the folder's `from-cowork/` subfolder, saved to
  `data/skill-data/from-cowork/`. That subfolder is where another session writes — a trade, a
  decision, some research — as new files. The next review reads them, folds them into the notes
  and budgets, and marks them merged (SKILL.md 3a.4). A trade reported there does not change share
  counts: those still come only from a broker export.

Setup, once:

1. In Google Cloud Console, create a project, enable the **Google Drive API**, and configure the
   OAuth consent screen (user type External, yourself as the only user). Set its publishing status
   to **In production**: left in Testing, Google expires the sign-in every seven days.
2. Create an OAuth client ID of type **Desktop app**, download its JSON, and save it as
   `data/drive-mirror/client.json`.
3. `python3 scripts/drive_mirror.py set-folder <folder id or link>` — the Drive folder to mirror
   into. Create it first.
4. `python3 scripts/drive_mirror.py auth` — opens a browser to sign in. Google shows an
   "unverified app" warning for a personal client; that is expected.

Then `python3 scripts/drive_mirror.py sync` runs at the start and end of every review.

Two things to know before you turn it on. The sign-in asks for full Drive access, because the
narrower per-file scope cannot see files another session created; the script only ever writes
inside the folder you set. And `data/drive-mirror/token.json` is a credential that can reach your
whole Drive: it is written owner-only and sits under the gitignored `data/` folder, so keep that
folder out of any backup or sync you do not control. To revoke it, remove the app under *Third-party
access* in your Google account and delete the file.

## Keep your data out of git

Holdings, notes, snapshots and the generated `PORTFOLIO.md` are personal. This repo's `.gitignore`
already ignores this skill's `data/` folder wholesale, and the pre-commit hook double-checks staged
content for the same thing, so nothing under `data/` reaches git by accident — but colocating it
here at all is a convenience, not a requirement: `--root` (see Layout) keeps it out of this tree
entirely if you'd rather. If you point the skill at a folder of your own instead, apply the same
deny-by-default `.gitignore` there.

---

*Ratings are advisory. Not investment advice — verify prices and figures before acting.*
