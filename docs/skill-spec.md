# Skill spec

How every skill in this repo is built. Read it before creating a skill or restructuring one, and
copy the newest skill that follows it (`skills/my-spendings`, `skills/mutual-fund-review`) rather
than starting from a blank folder.

**Keep it current.** When a change sets or alters a convention that more than one skill follows
(folder layout, sync rules, the plugin entry, a SKILL.md section every skill has), update this file
in the same commit. If a skill has to depart from it, say why in that skill's README rather than
letting the spec and the skills drift apart.

The goal behind every rule here: one skill, generic and public, that runs both in Claude Code on
the laptop and in the Claude app on the phone, from the same personal data, and that stays up to
date on both from the latest commit to this repo.

## 1. Generic and public

The repo invariant in `README.md` and `CLAUDE.md` applies in full. In short:

- No personal or financial data in any tracked file. That means none of:
  - **bank accounts:** account or customer numbers, IFSC beside an account, balances, statements,
    transactions, payees, salary;
  - **credit and debit cards:** card numbers, full or masked, expiry, CVV, limits, bills, spends;
  - **stocks:** holdings, quantities, buy prices, cost, P&L, weights, broker exports, contract notes,
    demat IDs, or the tickers actually held;
  - **mutual funds:** the funds held, folio numbers, units, NAV paid, SIP amounts and dates,
    account statements;
  - **bonds, FDs and other investments:** what is held, amounts, maturity dates, the platform;
  - **tax and identity:** ITR, Form 16, 26AS, AIS, PAN, Aadhaar, address, phone, email;
  - real amounts of any kind, and generated reports built from any of the above.

  Examples and test fixtures use invented names, invented tickers (`STOCKA`, `FUNDX`), round numbers,
  and card numbers that fail the Luhn checksum: `hooks/pre-commit` (through `hooks/card_numbers.py`)
  blocks any staged line holding a card number that passes it, or a masked one with real leading
  digits, examples included. A user's own card names and last 4 digits go in the gitignored
  `.private-terms`.
- No vendor, platform, bank or broker the user uses is named in a generic skill, and no skill that
  is specific to one. Describe the input by its format ("a broker export with these columns").
- What is personal, including which vendor a figure comes from and how to refresh it, goes in the
  user's `data/notes.md` (section 2), which the skill reads at the start of every run.
- Settings the user fills in ship as a `*-template.*` file with invented values (the only files
  `.gitignore` lets through by name); the filled-in copy lives in `data/`.

## 2. Folder layout

Two places, never mixed: the **skill folder** (tracked, generic, replaced on every plugin update)
and the **working root** (personal, never tracked, kept locally and in cloud storage).

```
skills/<name>/                  tracked
  SKILL.md                      instructions, with frontmatter
  README.md                     what it does, where its data lives, how to install, tests
  *-template.json|csv|md        what the user fills in, with invented values
  references/                   docs the skill reads on demand (cloud_sync.md, glossary.md, ...)
  scripts/
    *.py                        every deterministic step (see CLAUDE.md)
    drive-sync.json             what syncs to cloud storage (section 3)
    drive_sync.py               copy of shared/scripts/drive_sync.py, never edited here
    tests/test_*.py             stdlib unittest, synthetic fixtures

WORKROOT/data/                  personal, gitignored, mirrored to cloud storage
  notes.md                      the skill's memory: the user's sources, vendors, refresh steps
  profile.json                  the user's settings (from the template)
  raw/                          inputs the user drops in: statements, exports, captures
  skill-data/                   what the skill writes: reports, analyses, ledgers, snapshots
  .sync-base.json, .listing-*   sync state, written by drive_sync.py
```

- **WORKROOT** is `--root`, else an environment variable named for the skill (`<NAME>_ROOT`), else
  the skill's own folder when it runs from a checkout of this repo (where `data/` is gitignored and
  refused by the pre-commit hook). Every script takes `--root`, and one of them prints the resolved
  folder with `--where`, so SKILL.md never guesses a path.
- **Never write into the skill folder when it is installed as a plugin.** An update replaces it.
  If no WORKROOT resolves, SKILL.md asks where to keep the files (Claude Code), uses a folder the
  user shared (desktop app), or uses a temporary folder with the cloud copy as the only lasting
  one (Claude app).
- Run every command from `${CLAUDE_SKILL_DIR}`.
- State that both the user and the skill edit (settings, a payment ledger, `fds.csv`) sits at the
  top of `data/`. `raw/` is what came in; `skill-data/` is what the skill generated. Anything a
  script can rebuild from `raw/` (a cache, a parsed ledger) can be left out of sync.

Documented exceptions, each explained in the skill's README:

- `itr2-filing-assistant` works in one folder per assessee per assessment year, chosen by the user,
  with their documents directly in it (`data_dir: "."`).
- `pdf-unlock` keeps no state at all: no `data/`, no cloud copy, no `--where`.

A new skill uses this layout unless it has a reason as strong as those.

## 3. Local and cloud copies

The phone app cannot see this laptop, so every skill whose data a later run needs keeps a copy of
`data/` in the user's cloud file storage, through whichever file-storage connector is connected.

- **One cloud folder per skill**, inside the folder the user keeps for Claude. It is found by a
  marker file named exactly `<name>-sync.json`; never hard-code a folder name or ID in a tracked
  file (if one is needed, it goes in `notes.md`).
- **`scripts/drive_sync.py` decides every move.** The skill ships `scripts/drive-sync.json` (format
  in `shared/README.md`) and the sync steps, preferably as a `references/cloud_sync.md` copied from
  the newest skill and adjusted (`portfolio-review` keeps them in SKILL.md). Run
  `shared/sync-copies.sh` after adding the config; the hook refuses a stale copy.
- **One small file needs no sync engine.** A skill whose whole state is one small profile can keep
  a single shared copy, found by exact name, and merge it with a script, as `news-briefing` does
  with `news-briefing-profile.json`.
- **What syncs:**
  - both ways: `notes.md`, `profile.json`, other settings, and the reports and analyses in
    `skill-data/` that the phone needs to answer from;
  - down only (`"upload": false`): `raw/` statements and exports, so the user can drop a file into
    the cloud folder from the phone;
  - not at all: caches and anything a run rebuilds.
- **Keep uploads small.** Every byte sent through the connector passes through the model and costs
  tokens. Sync the newest report, not the history, and leave large rebuildable files local.
- **When to sync** (SKILL.md, Step 0):
  - lasting local folder (Claude Code): sync when asked, and push after a run that wrote a new
    report;
  - temporary folder (Claude app): pull at the start, push once at the end;
  - no connector and a temporary folder: say that nothing will outlast the session.
- In the Claude app there may be no browser and no local files: say what the skill can do there
  (usually: answer from the newest synced report) and what needs the laptop.

## 4. Installable as a plugin, tracking the latest commit

Every skill gets an entry in `.claude-plugin/marketplace.json`, in the same shape as the others:

```json
{
  "name": "<name>",
  "description": "<one line; say if it needs a file-storage connector or a browser>",
  "source": "./",
  "strict": false,
  "skills": ["./skills/<name>"],
  "homepage": "https://github.com/atishbits/claude-skills"
}
```

- **Never add a `version` field**, here or in a `plugin.json`. Without one, an installed plugin
  follows the repo's commits; with one, users stay on the cached copy until the string changes.
- The entry `name` matches the skill folder and the SKILL.md `name`.
- Add the skill to the plugin list and the install lines in `README.md`.
- Run `claude plugin validate .` after editing the file.
- To receive updates: in Claude Code, `/plugin` → Marketplaces → this marketplace → Enable
  auto-update (it is off by default for a third-party marketplace), or run
  `/plugin marketplace update atishbits-claude-skills`. In the Claude app, add the marketplace
  `atishbits/claude-skills` once and install the plugin; update it there if a change has not shown up.
- Changes reach users only after they are pushed to `main`.

## 5. SKILL.md

- Frontmatter: `name`, a `description` that says what it does and when to use it, and
  `allowed-tools` listing the skill's scripts (`Bash(python3 *<script>.py*)`).
- **Step 0 — working folder, notes, cloud copy**: resolve WORKROOT with the `--where` script, read
  `data/notes.md`, then sync as section 3 says.
- Arithmetic, parsing and classification are scripts; SKILL.md says which script to run and how to
  read its output (see *Prefer a deterministic script* in `CLAUDE.md`).
- Anything the skill learns about the user's own sources is written to `notes.md`, never to a
  tracked file.
- Finance skills end each reply with **Terms used**: the full form and a one-line meaning of each
  finance term (`references/glossary.md`), and carry a not-advice line on investment comments.

## 6. Checklist for a new skill

1. Copy the layout of the newest skill; rename, and delete what does not apply.
2. Write SKILL.md and README.md; README states where the data lives, the cloud copy, the install
   lines, and how to run the tests.
3. Put every one-answer step in `scripts/`, with tests in `scripts/tests/` that pass:
   `cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'`.
4. Add templates with invented values; put personal sources in your own `data/notes.md`.
5. Add `scripts/drive-sync.json` and `references/cloud_sync.md`, then run `shared/sync-copies.sh`.
6. Add the marketplace entry (no `version`), update `README.md`, run `claude plugin validate .`.
7. Grep the tracked files for vendor names and real figures; stage named paths; let the pre-commit
   hook run.
8. Push, then update or reinstall the plugin on the phone and check one run there.
9. If anything above changed a shared convention, update this file in the same commit.
