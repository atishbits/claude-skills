---
name: wint-wealth
description: >-
  Monitor a Wint Wealth bond portfolio and screen the bonds on sale there. Ingests the portal's
  Master Report and a capture of the live listings, summarises holdings and cash flows, checks
  that repayments arrived, shortlists new bonds against the investor's own limits, and gives
  ENTER / SKIP and HOLD / REVIEW / EXIT verdicts with sources. Use when the user asks about their
  Wint Wealth bonds: what they hold, what is due, whether a bond is still safe, what to buy with
  money coming back, or whether to exit.
argument-hint: "[issuer ...] | buy | refresh"
allowed-tools:
  - Bash(python3 *ingest.py*)
  - Bash(python3 *portfolio.py*)
  - Bash(python3 *cashflows.py*)
  - Bash(python3 *repayment_check.py*)
  - Bash(python3 *screen_listings.py*)
  - Bash(python3 *diff_snapshots.py*)
  - Bash(python3 *exit_cost.py*)
  - Bash(python3 *bond_facts.py*)
  - Bash(python3 *rating_ledger.py*)
  - Read
  - Write
  - Edit
  - Glob
  - WebSearch
  - WebFetch
---

Request for this run: **$ARGUMENTS**

You are helping with a bond portfolio held on Wint Wealth. Everything you say is advisory.
**Never invest, sell, sign Form 121, or change anything on the portal.** On the portal you only
read pages and run the capture snippet below.

**Where things live.** Run every command from `${CLAUDE_SKILL_DIR}`. Everything personal sits under
`${CLAUDE_SKILL_DIR}/data/`, which is gitignored: `data/profile.json` (the user's limits),
`data/reports/` (Master Reports) and `data/skill-data/` (everything the scripts write). If the
user keeps data elsewhere, pass `--root /that/folder` to every script or set `$WINT_ROOT`.

**Numbers come from scripts.** Every figure in a verdict or note is read from a script's output.
Do not recompute a share, a YTM, a tax amount or a date difference yourself.

## Route the request

- **Nothing named, or "refresh"** -> Steps 1 and 2. No research.
- **"What should I buy" / money coming back / a named bond on sale** -> Steps 1, 2, 3, then 4 for
  the shortlist.
- **A named issuer the user holds, "is X still safe", "should I exit"** -> Steps 1, 2, then 5.
- **First run** (no `data/profile.json`) -> copy `profile-template.json` to `data/profile.json`,
  ask the user to set each limit, and only then continue. Do not invent their limits.

## Step 1: get the data in

**Holdings.** Ask the user to download the Master Report (account menu -> Reports and documents ->
Master Report). It may stay in `~/Downloads` or go in `data/reports/`. Then:

```
python3 scripts/ingest.py reports
```

A header error means Wint changed the report. Show the user the message; the fix is the named
column in `config.json` `report_columns`, never a guess. Do not use the PDF Holding Statement: its
password is the user's PAN.

**Listings** (only when the request needs them). With the user logged in to Wint in Chrome:

1. Open `https://www.wintwealth.com/bonds/listing/` in a new tab and wait for the cards to load.
2. Run the contents of `${CLAUDE_SKILL_DIR}/capture-listings.js` in that tab, once. It reads the
   cards already on the page and saves `wint-listings-<time>.json` to Downloads.
3. `python3 scripts/ingest.py listings`

Limits on what you do in the browser, with no exceptions: read-only; one capture per review; no
loops, polling or scheduling; no calls to Wint's API; never read, print or store a token, cookie
or account detail. If the capture returns far fewer bonds than the page's "Live (N)" or the
checksum fails, the page layout has probably changed: tell the user, and fall back to filling
`listings-template.json` by hand and `ingest.py listings --file <it> --no-checksum`.

## Step 2: the standing picture

```
python3 scripts/portfolio.py          # writes data/skill-data/PORTFOLIO.md
python3 scripts/cashflows.py
python3 scripts/repayment_check.py
python3 scripts/diff_snapshots.py
```

Report, briefly: totals and weighted YTM; any limit breach; what is due in the lookahead window
and how much principal comes back; unrated holdings; anything `diff_snapshots.py` flags.

- **`repayment_check.py` says "no baseline yet"**: say exactly that. It is not a clean result.
- **Any repayment flag** (missing or short) or **any `overdue` entry** -> that holding is REVIEW
  now. Go to Step 5 for it. An overdue entry can be a late payment or a report that lags the
  bank, so ask the user to check their bank statement for that credit before you conclude.
- **Any `held_issuer_signals` entry** -> Step 5 for that issuer.
- **Unrated holdings** -> offer to research and record them (Step 5's research, then
  `bond_facts.py set`). An unrated holding is unknown, not safe.

## Step 3: screen what is on sale

```
python3 scripts/screen_listings.py            # cash defaults to what is due in the lookahead window
python3 scripts/screen_listings.py --cash 50000
```

Exit code 2 means the capture is stale: recapture (Step 1) and do not pass `--allow-stale` unless
the user asks, in which case say every figure is stale. Present the shortlist in rank order with
its risk bucket, post-tax YTM, tenure, minimum and `max_buy`. The ranking is by risk bucket first;
do not re-sort it by YTM. Mention how many were rejected and the commonest reasons.

## Step 4: ENTER or SKIP, for shortlisted bonds only

For each bond you take forward (at most five unless asked for more):

1. **Read its detail page** (`url` in the shortlist) for ISIN, rating agency, security cover,
   secured or unsecured, seniority, collateral, listed or not, and call or early-redemption terms.
   Record what you find:
   `python3 scripts/bond_facts.py set --bond-id ID --isin ISIN --issuer NAME --rating R --agency A --secured yes|no --seniority senior|subordinated --listed yes|no --source URL`
   A bond still "security unconfirmed" after this cannot get ENTER.
2. **Research the issuer's credit** from primary sources: the rating agency's latest rationale,
   recent results, exchange filings, and news. Look specifically for **rating actions**, which
   matter more than the grade: rating watch negative, "issuer not cooperating", outlook changes,
   a downgrade at another agency. Also: asset quality trend, capital and liquidity, who lends to
   them, auditor or regulator trouble. A search summary is a lead, not a source; open the page.
3. **Decide.** ENTER needs: facts confirmed, no adverse rating action, a reason this bond beats
   the others in its risk bucket, and a size no larger than `max_buy`. Otherwise SKIP. A higher
   YTM than its bucket peers is a question to answer, not a reason to buy.
4. **Record it**, with the script's numbers as inputs:
   `python3 scripts/rating_ledger.py add --kind listing --issuer NAME --bond-id ID --verdict ENTER --reason "..." --inputs '{"ytm": .., "post_tax_ytm": .., "rating": "..", "risk_bucket": "..", "tenure_months": .., "max_buy": ..}' --source URL --source URL`
5. Write or update `data/skill-data/bonds/<issuer-slug>.md` from `note-template.md`.

## Step 5: HOLD, REVIEW or EXIT, for a holding

1. Research the issuer as in Step 4.2, and update `bond_facts.py set --isin ...` if the rating,
   action or outlook has changed.
2. Decide:
   - **HOLD**: no adverse rating action, payments on time, nothing new and material.
   - **REVIEW**: a repayment flag, a negative watch or outlook, a held-issuer signal, or material
     bad news that is not yet a rating change. Say what would settle it and when to look again.
   - **EXIT**: credit has deteriorated enough that the remaining payments are in real doubt. Run
     `python3 scripts/exit_cost.py ISIN` and quote it as it is: an estimate, conditional on a
     buyer being found. Tell the user to check the portal's own sell quote for that bond first.
     If there may be no buyer, say so; an EXIT the user cannot execute is still worth knowing.
3. Maturity and reinvestment are not a sale: when `cashflows.py` shows principal coming back,
   say how much and when, and offer Step 3.
4. Record it:
   `python3 scripts/rating_ledger.py add --kind holding --issuer NAME --isin ISIN --verdict HOLD --reason "..." --inputs '{"ytm": .., "rating": "..", "rating_action": .., "repayment_flag": ..}' --source URL`
5. Update the issuer's note.

## Before you finish

- Every number in what you wrote appears in a script's output from this run.
- Every ENTER and EXIT has sources you opened, and a ledger entry.
- You said plainly what you could not verify.
- If a script warned that a `config.json` entry is old, pass that on: tax rules and the portal's
  exit terms change, and the entry needs re-verifying before the numbers that use it are trusted.

*Advisory only. Not investment or tax advice.*
