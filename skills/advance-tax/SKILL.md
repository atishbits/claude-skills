---
name: advance-tax
description: >-
  Compute advance income tax due for a given installment date (15 Jun / 15 Sep / 15 Dec / 15 Mar),
  from estimated FD interest, savings balance, dividends, house rent and bond interest. Use when the user
  asks what advance tax they owe, for a specific due date or "next installment", for themselves or
  for another person they name.
argument-hint: "[person] [due date | Q1-Q4] [FDR total] [savings balance] [dividends] [house rent] [already paid]"
allowed-tools:
  - Bash(python3 *compute_advance_tax.py*)
  - Bash(python3 *drive_sync.py*)
  - Read
  - Write
  - Edit
  - Glob
---

Request for this run: **$ARGUMENTS**

You are helping compute an advance tax installment for an individual (self-assessed "other sources"
income only — salary TDS is assumed already covered separately and folded into "already paid" if
the user gives it). The reference schedule (last checked Sep 2026) is Sec 208/211 of
the Income Tax Act, 1961 (renumbered 424/425 under the Income Tax Act 2025):

| Installment | Due date     | Cumulative % of estimated annual tax |
|-------------|--------------|---------------------------------------|
| Q1          | 15 June      | 15%                                    |
| Q2          | 15 September | 45%                                    |
| Q3          | 15 December  | 75%                                    |
| Q4          | 15 March     | 100%                                   |

`Advance tax due now = cum_pct x estimated annual tax on other-sources income - tax already paid this FY (TDS + prior installments)`

**Where the personal numbers live.** The skill ships statutory constants only — the due-date
schedule, the Section 24(a) standard deduction and the 4% cess. Every rate that depends on the
person (slab, FD and savings rates, surcharge band) comes from *their* `tax-profile.json`, which
is personal and is never committed. It sits in a **data folder** (WORKDIR below, the `data/` folder
inside a working root, WORKROOT) with the rest
of the skill's state: a payment ledger (`ledger.md`), `bond-interest.json` when the user holds
bonds, and `notes.md`, the skill's local memory. **Read `WORKDIR/notes.md` first if it exists**: it
is where the user's own sources for each input are written down (which account, platform or tool a
figure comes from and how to refresh it), and where you record anything of that kind you learn.
Nothing specific to a person, a platform they use or another tool of theirs belongs in this file.

## Step 0 — working folder

Run every command in this skill from the folder holding this file (`${CLAUDE_SKILL_DIR}` where that
variable is set). First run `python3 scripts/compute_advance_tax.py --where`. It prints JSON: the
data folder (`folder`), the working root that holds it (`root`), and which state files exist. The
data folder is `$ADVANCE_TAX_ROOT/data`, else this skill's own `data/` folder if it already exists
(the skill installed from a checkout of its repo, where `data/` is gitignored).

- **`folder` is set:** that is WORKDIR, and `root` is WORKROOT. Create WORKDIR if `exists` is false.
  If the output has a `note`, the user still has the old `ADVANCE_TAX_DIR` setting: the run works,
  but pass the note on and offer to move the files.
- **`folder` is null:** ask the user where to keep the files. The answer is WORKROOT, and WORKDIR is
  its `data/` folder.
  - **Claude Code:** any path, e.g. `~/Documents/advance-tax/`. Offer to set `ADVANCE_TAX_ROOT` to
    it in the `env` block of their Claude Code settings, so later runs find it.
  - **A desktop app with a folder shared to the session:** a folder inside it.
  - **Neither** (nothing written here outlasts the session): a temporary folder, with the cloud
    copy as the only lasting one (below).

Never create `data/` or any other file inside this skill's folder: when the skill is installed as
a plugin, an update replaces that folder.

**Cloud storage.** The user can keep a copy of the working folder in their cloud file storage, so a
run on another device or in another app carries on from the same ledger. To sync, read
`references/cloud_sync.md` and follow it.

- **A lasting working folder** (the first two cases above): touch cloud storage **only when the
  user asks**. "pull", "get my files from the cloud" and the like sync down; "sync", "push",
  "upload" and the like sync up.
- **A temporary folder:** sync down now, before Step 1, and sync up once at the end of the run,
  after Step 5, so only the final ledger, notes and profile go back. If there is no file-storage
  connector, say that nothing will survive the session, carry on, and give the user the updated
  ledger lines to keep themselves.

The script finds the profile in this order: `--profile PATH`, `$TAX_PROFILE`, `tax-profile.json` in
the current directory, then the one in the working folder from `--where`. With a working folder
`--where` did not report (a temporary folder, or one the user named this session), pass
`--profile WORKDIR/tax-profile.json`. If a rate is missing the script says exactly which, and it
accepts them as flags for a one-off run that saves nothing.

## Step 1 — identify who and which due date

- **Person**: the key under `people` in their profile (`self` by default). If they name someone the
  profile does not have, do not guess a slab: derive the rates from what they give you — last
  year's ITR computation is the best source, a salary slip or Form 16 for the slab, an FD receipt
  for the deposit rate — then either pass those as flags for this run, or offer to add an entry to
  their profile. Never write those numbers into the skill folder.
- **Due date**: map "15 June" / "next due date" / a specific date to Q1-Q4. If today's date is
  between two due dates and the user says "the upcoming one" or doesn't specify, pick the next
  unpassed due date in the current FY.

## Step 2 — gather the income inputs

Ask for (or take from the user's message):
1. **FDR total** — total FD principal across all fixed deposits (Rs).
2. **Savings balance** — total balance across savings accounts (Rs). This is taxed as *balance x
   assumed interest rate x tax%*, not the actual interest — the convention carried over from the
   spreadsheet this skill replaced.
3. **Dividends total** — estimated total dividend income for the full FY (Rs). Taxed directly at the
   slab rate (not discounted through an interest-rate factor — that was a bug in the pre-existing
   spreadsheet, fixed here).
4. **House rent total** — estimated total rental income for the full FY (Rs), before deductions.
   The 30% standard deduction (Section 24(a)) is applied automatically.
   If the user has home loan interest (Sec 24(b)) or municipal taxes paid to net off beyond the flat
   30%, ask and pass a reduced `--house-rent-total` (net of those) since the script only knows the
   flat statutory deduction.

5. **Bond interest** — only if the user holds bonds. It is the gross interest for the full FY
   (already received plus still scheduled) and the TDS on it; the script taxes the interest at
   the slab and takes the TDS off. Do not add it up yourself. If `notes.md` says how the
   user's bond figures are produced, follow it to refresh `WORKDIR/bond-interest.json` where this
   environment can, and pass `--bond-interest-file WORKDIR/bond-interest.json`; say which date the
   file is as of, and that bonds bought after it are not counted. Otherwise ask for the two numbers (the
   bond platform's tax or interest statement has them) and pass `--bond-interest-total` and
   `--bond-tds`. Bond TDS goes in here, never also in `--already-paid`.

If the user doesn't have fresh numbers for one of these, ask them for the source rather than
assuming: last year's ITR, a recent salary slip, an FD receipt, or their own spreadsheet. Say
clearly which numbers you carried forward from an older figure and which they gave you fresh.

Also ask **how much tax has already been paid this FY** — TDS credited so far (e.g. on FD interest,
salary) plus any advance tax installments already paid. This nets off in the formula; if omitted,
assume 0 and say so (this will overstate what's due now).

## Step 3 — compute

Pass `--profile` as Step 0 says:

```
python3 scripts/compute_advance_tax.py \
  --person <key from their profile> \
  --installment <Q1|Q2|Q3|Q4> \
  --fdr-total <N> \
  --savings-balance <N> \
  --dividends-total <N> \
  --house-rent-total <N> \
  --bond-interest-file WORKDIR/bond-interest.json \
  --already-paid <N>
```

Never do this arithmetic yourself — always run the script. If the rates were gathered in Step 1
rather than read from a profile, pass them as flags (`--fd-tax-pct`, `--other-tax-pct`,
`--surcharge-multiplier`, `--fd-interest-rate`, `--savings-interest-rate`) and offer to save them
into `WORKDIR/tax-profile.json` for next time. Never into the skill folder: it is a public repo,
and a slab rate is personal information.

## Step 4 — report

State the due date and amount due now, then the breakdown (FD / savings / dividend / house rent tax
components, and bond interest when given) so the user can sanity-check which bucket dominates. If `--already-paid` was assumed 0,
repeat that assumption plainly next to the number. Note that Sections 234B/234C interest applies to
shortfalls against this cumulative schedule — mention it only if the computed due-now amount is
being paid late or the user asks about a past due date.

Close with: *Not tax advice — verify figures with your CA before paying.*

## Step 5 — record

Offer to record the run in `WORKDIR/ledger.md`, keeping its existing layout: the date, the basis
(the inputs above), the estimated annual tax and the cumulative amount required, and any payment
the user reports with its date. Copy every figure from the script's output; never retype or round
one by hand. Write any new source of an input that you learned into `notes.md`. With a temporary
working folder, sync up now (Step 0).
