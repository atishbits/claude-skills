# wint-wealth

Monitors a bond portfolio held on Wint Wealth and screens the bonds on sale there. Python scripts
do the arithmetic; the skill does the credit research and gives ENTER / SKIP verdicts on new bonds
and HOLD / REVIEW / EXIT on what you hold. It never places an order.

## What it needs

**From you**

| Input | Where it comes from | Needed for |
|---|---|---|
| Master Report (`data/wint-master-report-<date>.xlsx`) | Wint: account menu -> Reports and documents -> Master Report | Everything. It carries five sheets: holdings, upcoming cash flows, repayments received, purchases, sales |
| Your limits (`data/profile.json`) | Copy `profile-template.json` and edit it: tax slab, rating floor, tenure ceiling, issuer and rating-bucket caps, whether unsecured or subordinated paper is allowed | Limit breaches and screening |
| Optional, in the same file: `effective_tax_rate_pct` and `tax_multiplier` | Your slab plus cess and any surcharge (for example 31.2 for the 30% slab with 4% cess), and the surcharge-and-cess multiplier on its own. If you use the `advance-tax` skill, `scripts/tax_profile.py --tax-profile <your tax-profile.json> --person NAME --write` fills both from the rates you already keep there | A closer post-tax yield and exit tax; without them the bare slab is used |
| Optional, in the same file: `annual_investment_budget` and `min_ytm_pct` | The most you will put into new bonds in a financial year (April to March), and the lowest yield worth buying | The screener rejects bonds under the yield floor, counts what you have already invested this year, and caps each purchase at what is left |
| Optional, in the same file: `total_investable` | Everything you invest, in rupees, not only what is on Wint | Measuring the issuer and rating-bucket caps against your whole portfolio; without it they are a share of the Wint book alone, which is looser than it sounds if Wint is a small part of your money |
| A second Master Report, some weeks later | Same download, kept alongside the first | Checking that payments due in between actually arrived |

Save the report under the name above: the name Wint gives it carries your phone number.

**From the session Claude runs in**

| Access | Used for | Without it |
|---|---|---|
| Chrome with Claude in Chrome, logged in to Wint | Capturing the bonds on sale (`capture-listings.js`) and reading a bond's detail panel (`read-bond-details.js`): ISIN, rating and outlook, agency, collateral, seniority, listed or not | No screening of new bonds; holdings can still be reviewed, with ratings taken from the agencies |
| Web search and page fetch | The rating agency's own rationale for each issuer, exchange filings, trustee payout reports for securitised pools | Verdicts cannot be given; the scripts still produce the portfolio and cash-flow figures |

Both browser snippets only read what is already on the page. They make no network request of
their own and read no token, cookie or account detail. The skill never invests, sells, or signs
anything.

**What makes a run good**

- A Master Report downloaded the same day.
- A listings capture under six hours old (the screener refuses an older one).
- For each bond, the agency's rationale opened and read, at every agency that rates the issuer.
  The rating on Wint's own page is the seller's statement of one agency's grade.
- An earlier snapshot on disk, so late or short payments can be detected.

## What you get

Ask "review my Wint portfolio", "what is due this quarter", "is Alpha Finance still safe", or
"what should I buy with the money coming back". A full review ends with a short summary in the
conversation and a dated folder on disk. The example below uses invented issuers and round
numbers.

**In the conversation**

> No holding warrants an exit. Two of three are HOLD and one is REVIEW.
>
> - **Beta Capital:** on a negative rating outlook; it matures on 30 Jun 2027, so that principal
>   payment is the test.
> - **Issuer cap:** Alpha Finance is 50% of the portfolio against your 25% cap.
>
> | Holding | Share | YTM | Matures | Rating (agency, outlook) | Verdict | What settles it |
> |---|---|---|---|---|---|---|
> | Alpha Finance | 50.0% | 11.0% | 2027-12-31 | A (Agency One, stable) | HOLD | - |
> | Beta Capital | 30.0% | 12.0% | 2027-06-30 | BBB+ (Agency Two, negative) | REVIEW | Principal paid on 30 Jun 2027 |
> | Gamma Microfin | 20.0% | 10.5% | 2028-03-31 | A- (Agency One, stable) | HOLD | - |
>
> Not verified: Gamma Microfin's rating is the issuer's, not confirmed for this bond. The
> repayment check has no earlier snapshot to compare against yet.

**On disk, in `data/skill-data/runs/<date>/`**

```
REVIEW.md             generated: totals, breaches, holdings and verdicts, returns by bond, repayments, cash coming back
analysis.md           the written reading of the run: conclusions, what was not verified, what to do
portfolio.json        shares by issuer group, rating bucket and tenure; weighted YTM; breaches
positions.json        per bond: invested, received, still to come, yearly return, rating, principal dates
cashflows.json        what is due, income by month, principal returning over the next 120 days
repayment_check.json  payments missing, short or overdue
diff.json             what changed since the last report and capture
screen.json           the shortlist of bonds on sale and why the rest were rejected
verdicts.json         the newest verdict for each bond
```

An extract of a generated `REVIEW.md`:

```
## Limit breaches

- Alpha Finance is 50.0% of the portfolio; limit 25%

## Holdings and verdicts

| Issuer | ISIN | Value | Share % | YTM % | Matures | Rating | Rating applies to | Verdict | Verdict date | Deciding reason |
|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Finance | INE000A07011 | 50000.0 | 50.0 | 11.0 | 2027-12-31 | A | this bond | HOLD | 2026-01-15 | Rating reaffirmed in December; payments on time. |
| Beta Capital | INE000B07022 | 30000.0 | 30.0 | 12.0 | 2027-06-30 | BBB+ | this bond | REVIEW | 2026-01-15 | Outlook cut to negative for rising overdue loans. |
| Gamma Microfin | INE000C07033 | 20000.0 | 20.0 | 10.5 | 2028-03-31 | A- | issuer | HOLD | 2026-01-15 | No adverse action at either agency. |

## Repayments

Baseline check: compared against schedules recorded since 2025-12-01 (4 due payment(s) checked).
No late, short or overdue payment flagged.

## Cash coming back

Next 45 days: 1450.0 (principal 0.0). Next 120 days, principal only: 10000.0, 10.0% of the portfolio.
```

When new bonds are screened, the shortlist is ranked within risk buckets, never by yield alone:

| Rank | Issuer | Risk bucket | YTM | Post-tax YTM | Tenure | Minimum | Most you can buy |
|---|---|---|---|---|---|---|---|
| 1 | Delta Housing | AA / secured / senior | 9.0% | 6.3% | 18 months | 10,000 | 33,333 |
| 2 | Epsilon Gold | A / secured / senior | 10.0% | 7.0% | 12 months | 10,000 | 33,333 |
| 3 | Zeta Finance | A / security unconfirmed | 10.5% | 7.35% | 24 months | 10,000 | 33,333 |

A bond gets ENTER only after its detail page and the agency's rationale have been read; the ledger
refuses an ENTER for a bond whose security and seniority are not recorded.

Every verdict is also appended to `ratings-ledger.jsonl` with its reason, the numbers it relied
on, its sources and the hash of the data behind it, and each issuer's note in `bonds/` carries
its verdict history.

## Layout

```
~/.claude/skills/wint-wealth -> <this folder>

data/                        gitignored: yours
  profile.json                 your limits
  wint-master-report-<date>.xlsx   the Master Report you downloaded
  wint-listings-<time>.json        listings captures
  skill-data/                  everything the scripts write
    snapshot-<date>.json         normalised holdings and cash flows
    listings-<time>.json         normalised listings capture
    bond-facts.json              rating, security, seniority per bond, with sources
    ratings-ledger.jsonl         every verdict, with the hashes of the data behind it
    PORTFOLIO.md                 generated summary
    POSITIONS.md                 generated returns-by-bond table
    bonds/<issuer>.md            one note per issuer; verdict history kept in step with the ledger
    runs/<date>/                 a dated record of each review: every script's output,
                                 REVIEW.md (generated) and analysis.md (the written reading)
```

The data root is `--root PATH`, then `$WINT_ROOT`, then the working directory.

## Setup

```
ln -s "$PWD/skills/wint-wealth" ~/.claude/skills/wint-wealth
mkdir -p skills/wint-wealth/data
cp skills/wint-wealth/profile-template.json skills/wint-wealth/data/profile.json
```

Then put the Master Report in `skills/wint-wealth/data/` and ask Claude to review your Wint
portfolio, or run `/wint-wealth`.

Python 3 only; no packages. Browser capture needs Claude in Chrome.

## Scripts

| Script | Does |
|---|---|
| `ingest.py reports` | Master Report -> `snapshot-<date>.json`. Fails loudly on a renamed column. |
| `ingest.py listings` | Verifies the capture's checksum and normalises it. |
| `portfolio.py` | Shares by issuer, rating bucket and tenure; weighted YTM; limit breaches. |
| `cashflows.py` | What is due, income by month, principal coming back soon and over the next few months. |
| `positions.py` | One row per bond: rating, invested, received so far, still to come, the yearly return (XIRR on the report's dated flows) before and after tax, and the dates principal returns. Shown on every portfolio review. |
| `repayment_check.py` | Flags a missing or short payment against the earlier schedule. Needs two snapshots. |
| `screen_listings.py` | Filters and ranks bonds on sale within risk buckets. Refuses a stale capture. |
| `diff_snapshots.py` | What changed since last time; rating signals on issuers you hold. |
| `exit_cost.py` | Estimated proceeds of selling now, conditional on a buyer. |
| `bond_facts.py` | Records per-bond credit facts with their source, the issuer's group, and whether a rating is the bond's own. |
| `rating_ledger.py` | Append-only verdict history. |
| `run_record.py` | Saves a dated record of a review and refreshes the issuer notes from the ledger. |
| `tax_profile.py` | Fills the profile's tax rates from the `advance-tax` skill's personal profile. |

Tests: `cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'`.

## What `config.json` holds

Facts about the portal and the tax code, each with a date and a source: the early-exit deduction,
TDS on interest, how gains on listed and unlisted bonds are taxed, and the Master Report's column
names. These change. A script warns when an entry is over a year old; re-verify it then. The tax
entries point at the Income Tax Department and PIB, but were read through search summaries (the
pages refuse a direct fetch) and describe the 1961 Act as amended in 2024, so open them yourself
and confirm with your CA before relying on a post-tax or exit figure.

## Limits

- The Master Report has no ratings. Until a bond's rating is recorded in `bond-facts.json` it is
  shown as unrated.
- The listings page does not say whether most bonds are secured or senior. Those show as
  "security unconfirmed" until the bond's detail page has been read.
- The exit estimate assumes a buyer and takes the 1% deduction on current value. Use the portal's
  own sell quote for the real number. It taxes each purchase lot on its own holding period.
- Post-tax YTM is YTM x (1 - tax rate): an approximation that treats the whole yield as interest
  taxed at one rate. It is good for ranking bonds against each other, not for a tax computation.
- The screener uses the rating recorded in `bond-facts.json` when there is one, and the listing
  card's rating only as a fallback; it warns when the two differ.
- A capture with fewer than 90% of the bonds the page says are live is rejected as partial.
- Laptop only: capture needs your logged-in browser.

## Keep your data out of git

Everything personal is under `data/`, which the repo's `.gitignore` and pre-commit hook already
block. The snapshot never contains your name, phone or email: ingest skips the identity rows at
the top of each sheet and records only a hash of the workbook.

---

*Advisory only. Not investment or tax advice.*
