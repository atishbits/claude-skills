# my-spendings

A Claude skill for a personal financial check-up from your own bank and credit-card statements:
where the money went, how income splits into spending, saving and investing, how investments are
spread, and what to review — recurring payments and auto-debits, fees and hidden charges, and
transactions that look wrong. It also answers "should I?" questions from the same data, such as
whether a credit-card offer pays off at your actual spend. Every number comes from a tested Python
script (standard library only); Claude reads the output, words the judgement, and never acts on an
account.

## What it reads

| Input | How it arrives | Script |
|---|---|---|
| Bank statements (CSV, XLSX, XLS, PDF) | Downloaded in a browser by Claude after you log in, or dropped into `data/raw/` | `ingest.py` with a table adapter |
| Card statements (usually PDF) | Same | `ingest.py` with a text adapter (`pdftotext -layout`) |
| Anything else | A CSV in the format of `manual-import-template.csv` | `ingest.py --adapter manual-import` |
| Your labels for payees | Asked when a payee is unknown, saved in `data/rules.csv` | `classify.py add-rule` |
| Current investments (optional) | `data/holdings.csv` in the format of `holdings-template.csv`, filled from your other finance skills' reports | `analyse.py` |
| Card offers | One JSON per card in `data/offers/` (and `data/cards/` for your current cards) | `card_offer.py` |

Nothing personal ships with the skill. Your data lives in a working folder's `data/`
(gitignored): `--root`, else `$SPENDINGS_ROOT`, else this folder's own `data/` in a checkout.
`data/notes.md` records which banks and cards you use, where their statements are and which
adapter reads each; the tracked files name none.

`data/accounts.json` (from `accounts-template.json`) lists each account and card by an alias and
its **last 4 digits only**, the pattern each card's bill payment shows in a bank statement, any
add-on cards (their spending is yours, marked with whose card it was), and the name patterns that
mark transfers between your own accounts and money sent to family.

### Adapters

One JSON file per statement layout, in `data/adapters/`. Examples with invented layouts are in
`adapters/`.

- **`kind: "table"`** (CSV/XLSX/XLS): `header_contains` (words that find the header row below any
  title rows), `columns` (header names for `date`, `description`, `reference`, `balance`, and
  either `debit` + `credit` or `amount` with an optional `drcr` column), `date_format`.
- **`kind: "pdf_text"`**: `line_regex` with named groups `date`, `description`, `amount` and
  optionally `drcr` and `reference`; `credit_marker` (a line ending in it is money back onto the
  card); optional `holder_regex` with a `last4` group that starts each cardholder's section, so
  add-on card rows get their label.

A bank statement's balances are checked: opening balance plus every transaction must equal the
closing balance, or the ingest stops. Re-ingesting a file, or one that overlaps another, adds only
transactions not already in the ledger.

### Card offer fields

`name`, `joining_fee`, `annual_fee`, `fee_waiver_spend` (yearly spend on the card that waives the
annual fee), `gst_on_fees_pct` (default 18), `rates` (reward rate per category, e.g.
`{"fuel": 0.05, "default": 0.01}`), `reward_cap_month` (rupees a month per category),
`point_value_inr` (rupee value of one reward unit; 1 for cashback), `fuel_surcharge_pct` (default
1), `surcharge_waiver_pct` (100 = fully waived), `surcharge_txn_min` / `surcharge_txn_max` (the
transaction band the waiver applies to), `surcharge_waiver_cap_month`, `use_for` (the categories
you would move to this card; default: everyday spending that cards usually accept, leaving out
rent, EMIs, cash, fees, tax and education — the output notes what was left out), `source`, `as_of`.

## What it produces

`data/skill-data/analysis-<date>.json` (every figure) and `data/skill-data/REPORT-<date>.md`:

- **Spending**: by category and month; card bills paid from a bank account are replaced by the
  card's own purchases when its statement is in, and shown as "card spend (not broken down)" when
  it is not, so nothing is counted twice. Add-on card spending is shown by holder.
- **Savings vs investing**: income, spending, tax, money sent to family, net investing; savings
  and investing rates; where new money went; the mix of current holdings with concentration
  flags.
- **Flags for review**: recurring payments and auto-debits with their yearly cost, fees and
  charges, and transactions to check (duplicates, tiny debits, a large first payment to a new
  payee, amounts far above a payee's usual, foreign-currency charges).
- **Decisions** and **Terms used**.

## The read-only browser guard

`SKILL.md` declares a `PreToolUse` hook, `scripts/browser_guard.py`, that runs only while the
skill is active. It covers every browser- or desktop-driving tool (any MCP server whose name mentions a
browser, Chrome, Playwright, Puppeteer, Selenium, DevTools or a computer). It lets Claude read pages,
open and close tabs, and click or choose things whose description is about statements, dates or
file formats. It denies any click or choice that also commits or moves something (pay, transfer,
proceed, continue, confirm, submit, save, cancel, open an FD, amount, OTP, and so on), every page
script, `javascript:` link, batched action and upload, and any browser tool it does not know.
Typing is limited to dates and years, form values to dates, months, periods and file formats, and
keys to navigation keys. If the guard itself fails, the action is blocked.

Limitation: the guard judges an action by Claude's own description of it, so it stops mistakes
and instructions planted in a page, not a model mislabelling on purpose. Keep watching the tab.
Before opening a bank site the skill checks that the guard is active by making one call it must
block; if that call goes through, it uses the folder route instead. Browser pulls are for Claude
Code only.

The hook command looks for the guard script in the skill's folder (`$CLAUDE_SKILL_DIR`, which
Claude Code does not always set for hooks), then the plugin's folder, then
`~/.claude/skills/my-spendings`. If it finds none it blocks every browser action, so a broken
install fails safe: downloads stop working rather than the guard switching off.

## Cloud copy

`scripts/drive-sync.json` and `references/cloud_sync.md` keep settings, labels, adapters, offers
and saved reports in your cloud storage, so the Claude app can show the latest report and value a
card offer. Statements only ever come down; the ledger stays local.

## Install

From this repository's marketplace (`marketplace.json`), plugin `my-spendings`.

## Tests

```
cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'
```

Fixtures are synthetic (invented banks, payees and amounts).
