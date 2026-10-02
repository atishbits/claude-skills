# wint-wealth

Monitors a bond portfolio held on Wint Wealth and screens the bonds on sale there. Python scripts
do the arithmetic; the skill does the credit research and gives ENTER / SKIP verdicts on new bonds
and HOLD / REVIEW / EXIT on what you hold. It never places an order.

## What you provide

1. **The Master Report**: on Wint, account menu -> Reports and documents -> Master Report. Leave
   it in `~/Downloads` or put it in `data/reports/`.
2. **Your limits**: copy `profile-template.json` to `data/profile.json` and edit it (tax slab,
   rating floor, tenure ceiling, issuer and rating-bucket caps, and so on).
3. **A listings capture**, when you want new bonds screened: Claude runs `capture-listings.js` on
   the listings page in your logged-in Chrome. It reads the bond cards on the page and saves one
   JSON file to Downloads. It makes no network request and reads no token or account detail.

## Layout

```
~/.claude/skills/wint-wealth -> <this folder>

data/                        gitignored: yours
  profile.json                 your limits
  reports/                     Master Report workbooks (optional location)
  skill-data/                  everything the scripts write
    snapshot-<date>.json         normalised holdings and cash flows
    listings-<time>.json         normalised listings capture
    bond-facts.json              rating, security, seniority per bond, with sources
    ratings-ledger.jsonl         every verdict, with the hashes of the data behind it
    PORTFOLIO.md                 generated summary
    bonds/<issuer>.md            one note per issuer
```

The data root is `--root PATH`, then `$WINT_ROOT`, then the working directory.

## Setup

```
ln -s "$PWD/skills/wint-wealth" ~/.claude/skills/wint-wealth
mkdir -p skills/wint-wealth/data
cp skills/wint-wealth/profile-template.json skills/wint-wealth/data/profile.json
```

Python 3 only; no packages. Browser capture needs Claude in Chrome.

## Scripts

| Script | Does |
|---|---|
| `ingest.py reports` | Master Report -> `snapshot-<date>.json`. Fails loudly on a renamed column. |
| `ingest.py listings` | Verifies the capture's checksum and normalises it. |
| `portfolio.py` | Shares by issuer, rating bucket and tenure; weighted YTM; limit breaches. |
| `cashflows.py` | What is due, income by month, principal coming back. |
| `repayment_check.py` | Flags a missing or short payment against the earlier schedule. Needs two snapshots. |
| `screen_listings.py` | Filters and ranks bonds on sale within risk buckets. Refuses a stale capture. |
| `diff_snapshots.py` | What changed since last time; rating signals on issuers you hold. |
| `exit_cost.py` | Estimated proceeds of selling now, conditional on a buyer. |
| `bond_facts.py` | Records per-bond credit facts with their source. |
| `rating_ledger.py` | Append-only verdict history. |

Tests: `cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'`.

## What `config.json` holds

Facts about the portal and the tax code, each with a date and a source: the early-exit deduction,
TDS on interest, how gains on listed and unlisted bonds are taxed, and the Master Report's column
names. These change. A script warns when an entry is over a year old; re-verify it then. The tax
entries were checked against secondary sources, not the Act; confirm with your CA before relying
on a post-tax figure.

## Limits

- The Master Report has no ratings. Until a bond's rating is recorded in `bond-facts.json` it is
  shown as unrated.
- The listings page does not say whether most bonds are secured or senior. Those show as
  "security unconfirmed" until the bond's detail page has been read.
- The exit estimate assumes a buyer and takes the 1% deduction on current value. Use the portal's
  own sell quote for the real number.
- Laptop only: capture needs your logged-in browser.

## Keep your data out of git

Everything personal is under `data/`, which the repo's `.gitignore` and pre-commit hook already
block. The snapshot never contains your name, phone or email: ingest skips the identity rows at
the top of each sheet and records only a hash of the workbook.

---

*Advisory only. Not investment or tax advice.*
