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
  - Bash(python3 *run_record.py*)
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
the Master Report and listings captures the user brings, directly in `data/`, and
`data/skill-data/` (everything the scripts write). If the
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
Master Report), then move it into `data/` under a name without the phone number Wint puts in it:

```
mv ~/Downloads/WintWealth_Master_Report_*.xlsx data/wint-master-report-$(date +%F).xlsx
```

Then:

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
3. `mv ~/Downloads/wint-listings-*.json data/`
4. `python3 scripts/ingest.py listings`

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

Report, briefly: totals and weighted YTM; any limit breach (issuers in one group are capped
together); what is due in the lookahead window; `principal_ahead` from `cashflows.py` (principal
returning over the longer horizon, by month, and its share of the book), since that is the
reinvestment to plan for; unrated holdings; `ratings_not_for_this_bond`; anything
`diff_snapshots.py` flags. Say when the book is concentrated in one sector: every bond on Wint is
lender paper, so reinvesting there does not diversify it.

- **`repayment_check.py` says "no baseline yet" or "nothing was checkable"**: say exactly that.
  It is not a clean result.
- **Any repayment flag** (missing or short) or **any `overdue` entry** -> that holding is REVIEW
  now. Go to Step 5 for it. An overdue entry can be a late payment or a report that lags the
  bank, so ask the user to check their bank statement for that credit before you conclude.
- **Any `held_issuer_signals` entry** -> Step 5 for that issuer.
- **Unrated holdings** -> offer to research and record them (Step 5's research, then
  `bond_facts.py set`). An unrated holding is unknown, not safe.

## Step 3: screen what is on sale

```
python3 scripts/screen_listings.py            # no cash filter; output shows cash_arriving
python3 scripts/screen_listings.py --cash 50000   # drop bonds whose minimum is above this
```

Ask the user how much they want to deploy and pass it as `--cash`; if they have not said, run it
without and report `cash_arriving` (what comes back within the lookahead window, and by when)
beside the shortlist. Exit code 2 means the capture is stale: recapture (Step 1) and do not pass `--allow-stale` unless
the user asks, in which case say every figure is stale. Present the shortlist in rank order with
its risk bucket, post-tax YTM, tenure, minimum and `max_buy`. Pass on every entry in the
output's `warnings` (for example, unrated holdings that the bucket caps cannot count). The ranking is by risk bucket first;
do not re-sort it by YTM. Mention how many were rejected and the commonest reasons.

## Step 4: ENTER or SKIP, for shortlisted bonds only

For each bond you take forward (at most five unless asked for more):

1. **Read its detail page** (`url` in the shortlist): open it and run the contents of
   `${CLAUDE_SKILL_DIR}/read-bond-details.js` in that tab. It opens "Other bond details" and
   returns the Overview panel: ISIN, rating with outlook, rating agency and date of rating,
   collateral type, seniority (for example "Senior secured bond"), listed or not, coupon, and
   maturity date. Never click "Invest Now". Record what you find:
   `python3 scripts/bond_facts.py set --bond-id ID --isin ISIN --issuer NAME --rating R --rating-scope "this bond" --agency A --secured yes|no --seniority senior|subordinated --listed yes|no --source URL`
   Wint's page is the seller's page: good for the bond's terms, **not a source for its credit**.
   It shows one agency's grade and a date; it cannot show a watch, a second agency's view, or
   asset quality, and its listing cards have been seen to disagree with the agency.
   Then **re-run `screen_listings.py`**: the recorded facts now go through the hard filters, and
   a bond the screen rejects on them is SKIP. A bond still "security unconfirmed" cannot get
   ENTER; `rating_ledger.py` refuses an ENTER whose secured and seniority facts are not recorded.
2. **Research the issuer's credit** from primary sources: the rating agency's latest rationale,
   recent results, exchange filings, and news. Open the rationale itself for every bond you give
   a verdict on, and say so plainly when you could not. Look specifically for **rating actions**,
   which matter more than the grade: rating watch negative, "issuer not cooperating", outlook
   changes, a downgrade at another agency. **Check every agency that rates the issuer**, not only
   the one Wint shows: a Negative outlook at any one of them counts, even if another is Positive.
   A lead you found and did not follow up is not something to leave out; follow it or report it.
   For a securitised pool (a PTC), the monthly trustee payout reports on the exchange are the
   primary source: collections, overdue buckets, and whether the cash collateral was drawn. Also: asset quality trend, capital and liquidity, who lends to
   them, auditor or regulator trouble. A search summary is a lead, not a source; open the page.
3. **Decide.** ENTER needs: facts confirmed, no adverse rating action, a reason this bond beats
   the others in its risk bucket, and a size no larger than `max_buy`. Otherwise SKIP. A higher
   YTM than its bucket peers is a question to answer, not a reason to buy.
4. **Record it**, with the script's numbers as inputs:
   `python3 scripts/rating_ledger.py add --kind listing --issuer NAME --bond-id ID --verdict ENTER --reason "..." --inputs '{"ytm": .., "post_tax_ytm": .., "rating": "..", "risk_bucket": "..", "tenure_months": .., "max_buy": ..}' --source URL --source URL`
5. Write or update `data/skill-data/bonds/<issuer-slug>.md` from `note-template.md` (bond
   facts, credit read, what would change the verdict, sources).

## Step 5: HOLD, REVIEW or EXIT, for a holding

1. Find the holding's own bond among the listings if it is still on sale (same issuer and
   maturity) and read its detail page as in Step 4.1; the ISIN on the page tells you whether it is
   the same bond. Then research the issuer as in Step 4.2 and record what you find with
   `bond_facts.py set --isin ...`:
   - `--rating-scope "this bond"` only when the agency's own annexure or the bond's page lists
     this ISIN; otherwise `issuer` or `"sibling bond"`. A rating that is not this bond's, and
     security or seniority that is not confirmed for it, are stated in the verdict.
   - `--group NAME` when the issuer is rated together with a parent or subsidiary (the agency
     says "consolidated"): they are one credit and share one issuer cap.
2. Decide:
   - **HOLD**: no adverse rating action, payments on time, nothing new and material.
   - **REVIEW**: a repayment flag, a negative watch or outlook at any agency (including split
     outlooks), a held-issuer signal, or material bad news that is not yet a rating change. Say
     what would settle it and when to look again.
   "No adverse rating action" is the minimum for HOLD, not the whole case: agencies lag. For
   BBB-range issuers also weigh, from the rationale, the trend in profit and credit cost and the
   debt falling due in the next year against the liquidity available to pay it.
   - **EXIT**: credit has deteriorated enough that the remaining payments are in real doubt. Run
     `python3 scripts/exit_cost.py ISIN` and quote it as it is: an estimate, conditional on a
     buyer being found. Tell the user to check the portal's own sell quote for that bond first.
     If there may be no buyer, say so; an EXIT the user cannot execute is still worth knowing.
3. Maturity and reinvestment are not a sale: when `cashflows.py` shows principal coming back,
   say how much and when, and offer Step 3.
4. Record it:
   `python3 scripts/rating_ledger.py add --kind holding --issuer NAME --isin ISIN --verdict HOLD --reason "..." --inputs '{"ytm": .., "rating": "..", "rating_scope": "..", "outlook": "..", "repayment_check": ".."}' --source URL`
   For `repayment_check` write what the script actually returned: `"clean"` only if it checked
   this bond's dues and found none short, otherwise `"no baseline yet"`, `"nothing checkable"` or
   the flag itself. Never record an unchecked repayment history as clean.
5. Update the issuer's note.

## Save the run

Do this last, on every run, once the verdicts are in the ledger:

```
python3 scripts/run_record.py save
```

It writes `data/skill-data/runs/<date>/` (every script's output as JSON, the newest verdict per
bond, and a generated `REVIEW.md`) and refreshes the verdict history at the top of each issuer
note from the ledger. Then write `data/skill-data/runs/<date>/analysis.md` yourself: the reading
of this run that a script cannot produce. Keep it short:

- what changed since the last run, and what you concluded;
- each REVIEW or EXIT, and what would settle it;
- what you could not verify, and which verdicts rest on thin evidence;
- what the user should do or check, most important first;
- if a separate reviewer judged the run, its main findings and what you changed because of them.

Numbers in `analysis.md` are quoted from the JSON files beside it. If you change a verdict after
saving, record it in the ledger and run `run_record.py save` again; it rewrites the generated
files and leaves `analysis.md` alone.

In an issuer note, write below the generated verdict history. Do not write a verdict line of your
own there: the history comes from the ledger, so it cannot go stale.

## Before you finish

- The run is saved and `analysis.md` is written.

- Every number in what you wrote appears in a script's output from this run.
- Every ENTER and EXIT has sources you opened, and a ledger entry.
- You said plainly what you could not verify.
- If a script warned that a `config.json` entry is old, pass that on: tax rules and the portal's
  exit terms change, and the entry needs re-verifying before the numbers that use it are trusted.

*Advisory only. Not investment or tax advice.*
