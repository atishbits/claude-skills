---
name: mutual-fund-review
description: >-
  Review Indian mutual-fund holdings across every platform and statement they sit on: returns
  (XIRR) against the right index and against "the same money in the index", whether each fund
  beats an FD after tax, what each costs, and the tax sitting in it. Works from saved data and
  pulls fresh data (a portal capture or a consolidated account statement) only when asked or
  stale. Use when the user asks about their mutual funds or a named fund: how they are doing,
  whether a fund still earns its fee, whether to switch to an index fund, what to do with new
  money, SIPs or a lump sum.
argument-hint: "[fund name ...] | refresh | from YYYY-MM-DD to YYYY-MM-DD"
allowed-tools:
  - Bash(python3 *common.py*)
  - Bash(python3 *freshness.py*)
  - Bash(python3 *ingest_capture.py*)
  - Bash(python3 *ingest_cas.py*)
  - Bash(python3 *nav.py*)
  - Bash(python3 *fund_meta.py*)
  - Bash(python3 *tax.py*)
  - Bash(python3 *analyse.py*)
  - Bash(python3 *report.py*)
  - Bash(python3 *drive_sync.py*)
  - Bash(pdftotext *)
  - Read
  - Write
  - Edit
  - Glob
  - WebSearch
  - WebFetch
---

Request for this run: **$ARGUMENTS**

You are reviewing the user's mutual funds. Everything you say is advisory. **Never buy, sell,
switch, start or stop a SIP, or change anything on any portal; never log in or type a password or
OTP.** On a portal you only read pages and run the capture snippet.

**Numbers come from scripts.** Every return, value, cost, tax amount, hurdle and break-even you
quote is read from a script's output. Do not compute a CAGR, an XIRR, a tax or a date difference
yourself. If a number you need has no script, say so instead of estimating it.

**Which platforms.** This file names none. `data/notes.md` in the working root is the user's own,
gitignored: it says which sources they use (portal names, adapter files, where their consolidated
account statement arrives), their bank's FD-rates page, and where sibling skills keep data (the
advance-tax profile and person, the ITR working folder, the stock and bond skills' working roots).
Read it in Step 0. Never copy what it says into a file outside `data/`.

## Step 0: working folder, cloud copy, freshness

Run every command from `${CLAUDE_SKILL_DIR}`. Everything personal sits in a working root's `data/`
(WORKROOT): `profile.json`, `notes.md`, `fds.csv` (optional), `adapters/`, `raw/` (captures,
statements), and `skill-data/` (what scripts write). The root is `--root`, else `$MF_ROOT`, else
this skill's folder when its gitignored `data/` exists (`python3 scripts/common.py --where`). If
none, ask the user where to keep it (in Claude Code offer to set `MF_ROOT` in their settings; in the
Claude app use a temporary folder and the cloud copy). Never create `data/` inside an installed
plugin folder. Pass `--root WORKROOT` to every script when it is not this skill's folder.

**Cloud storage.** The cloud copy of `data/` is what lets the Claude app and Claude Code share the
same data. Follow `references/cloud_sync.md`. With a lasting folder: sync when asked, and push up
after any run that brought in new data. With a temporary folder: pull before Step 1, push at the end.
No file-storage connector and a temporary folder: say nothing will outlast the session.

**Freshness first.** `python3 scripts/freshness.py` shows each source's age, whether its
transaction history is complete, the FD rate's age and funds missing metadata. Use cached data
unless the user asked for a refresh, or a source is in `suggest_refresh` and the question depends
on it (then offer the refresh; say the date of the data you used either way).

**First run** (no `data/profile.json`): copy `profile-template.json` to `data/profile.json`. Do
not ask for tax rates: run `python3 scripts/tax.py import --tax-profile <path from notes>
--person <name from notes> --write` and say whose rates were used (the advance-tax profile says its
values are unverified against the latest ITR; mention it beside any after-tax figure). If notes
name an ITR working folder, read its capital-gains conclusions for gains already booked this year
and brought-forward losses before asking the user anything. Ask only for what no sibling skill
holds.

**Leaving a fund out.** When the user wants a fund kept out of this review (held for another
purpose, managed elsewhere), add its ISIN to `exclude_isins` in `data/profile.json`; every
ingest drops it and reports how many rows it dropped. Funds already in the ledger leave on the
next ingest of their source.

**FD rate.** If `fd_rate_age_days` is missing or over 30, read the user's bank FD-rates page (from
notes) and set `fd_rate_pct` (the rate for 3–5 years, general public, below ₹3 crore),
`fd_rate_as_of` and `fd_rate_source` in `data/profile.json`. The hurdle is always today's market FD
rate, not the rate on FDs the user already holds.

## Route the request

| Request | Do |
|---|---|
| Nothing specific, "how are my funds", a named fund | Step 2 (cached), Step 3 |
| "refresh", "pull my latest", "I invested since", a stale source the answer depends on | Step 1, then 2, 3 |
| "from DATE to DATE", "this year", "since March" | Step 2 with `--from/--to`, Step 3 |
| "where should ₹X go", SIP plan, lump sum | Step 2, then Step 4 |
| A new statement or capture file the user dropped in | Step 1 for that file, then 2, 3 |

## Step 1: bring in fresh data

**Portal capture** (needs a browser the session controls, the user logged in, and their tab in the
session's tab group; never log in yourself). Open the holdings page named in notes, paste the
adapter from `data/adapters/<source>.json` into `capture/capture.js` and run it once in that tab.
It saves `<source>-capture-<time>.json`; move it to `data/raw/`, then
`python3 scripts/ingest_capture.py --capture data/raw/<file>`. Read-only limits: one capture per
review, no network calls from the page, never read a cookie, token or account field. If a portal
changed and the adapter returns nothing, fix the adapter's selectors with the user; do not guess
numbers from screenshots.

**Consolidated account statement** (full history; covers every fund house that holds units in
folio form). If it is password-protected, the user unlocks it with the pdf-unlock skill; never ask
for the password here. Then `python3 scripts/ingest_cas.py --pdf data/raw/<file>.pdf`. Its holdings
replace another source's holding of the same folio and fund. `incomplete_history` lists funds whose
statement starts mid-way: ask the user for a statement from an earlier start date.

**Hand-made CSV** in the format of `manual-import-template.csv`:
`python3 scripts/ingest_capture.py --csv FILE --source NAME`.

A reconciliation failure (units in transactions do not add up to units held) stops the ingest.
Show which funds; re-capture, or `--force` to record them flagged if the user agrees.

**Fund facts.** `python3 scripts/fund_meta.py missing` lists held funds lacking an AMFI code,
category, benchmark or expense ratio. Fill each from the fund house's page or AMFI's TER page with
`fund_meta.py set ISIN --amfi_code … --category … --benchmark_key … --expense_ratio_pct …
--er_as_of … --er_basis post_2026_04 --er_source …` (benchmark keys: `references/benchmarks.json`).
`nav.py latest ISIN` finds the AMFI code.

## Step 2: analyse

```
python3 scripts/analyse.py [--as-of YYYY-MM-DD] [--from D --to D]
python3 scripts/report.py
```

`analyse.py` writes `skill-data/analysis-<date>.json`; `report.py` writes `skill-data/PORTFOLIO.md`
and prints it. Show the user the report's headline, the per-fund table and anything flagged.

## Step 3: verdicts (judgement on script output)

Word each fund's verdict from its flags, with the evidence row beside it:

- **KEEP**: `keeps_fee`, or `index_fund` that is cheap for its index, and not `below_fd_hurdle_rolling`.
- **SWITCH to index (candidate)**: `fails_fee_test` with enough history. Read the fund's
  `switch` block in the analysis: `tax_if_sold_inr`, `exit_load_inr` and
  `breakeven_years_to_index` (years a 0.2%-fee index fund needs to repay that cost, at the
  profile's `expected_return_pct`). Suggest switching only if break-even ≤
  `max_switch_breakeven_years`; otherwise suggest stopping new money into it instead. Switch in
  tranches that fit the yearly ₹1.25 lakh exemption.
- **WATCH**: `below_fd_hurdle_rolling`, `short_history`, or a sector fund over its cap.
- **Can't judge yet**: `transactions_incomplete` (say what statement would fix it), `er_missing`,
  `exit_load_period_unknown` (switch cost unknown), `idcw_no_growth_series` (record the growth
  plan's code as `growth_amfi_code`), `lots_error`, `no_benchmark`.
- `held_under_1y`: quote the plain gain, never the annualised XIRR.

Separate luck from skill: a fund's `same_flows.diff_pts` is about the user's timing and choice
together; `rolling.win_pct` is about the fund alone. Never treat a high recent return as a reason.
News or market outlook may support a verdict (cite it) but never triggers one by itself
(`references/research.md`). Index-fund holdings that are down while their index is down are the
market, not a mistake: say so.

## Step 4: new money, SIP, lump sum

Until the dedicated planners arrive, answer from the analysis and `references/research.md`, with
every figure from a script: the FD hurdle (`tax.py hurdle`), each candidate's rolling record and
cost from `analyse.py` output (run `fund_meta.py set` and `analyse.py` for a fund not yet held only
if the user wants it compared). Defaults: index funds for large cap; an active fund only where held
active funds pass the fee test; low-risk money to an arbitrage fund when it beats the FD after tax;
gold 5–15% via a gold ETF or fund of funds; lump sums into equity either at once or moved in over
3–12 months from an arbitrage or liquid fund. State plainly that allocation targets and the
SIP/lump-sum planners are not built yet.

## Finish

Say the date of the data behind every figure. Push to the cloud copy if Step 0 says so. End every
reply with **Terms used**: the full form and a one-line meaning of each finance term in it (the
report's glossary has the common ones).
