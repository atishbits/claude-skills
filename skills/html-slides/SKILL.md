---
name: html-slides
description: >-
  Build a visual HTML slide deck on any topic the user names: diagrams, charts, blocks and big
  numbers, with brief text, backed by data and sourced insights. Works from a topic (with quick
  web research, or deep research when asked), from a report or data file another tool produced,
  or from a codebase or design to explain. One self-contained file with arrow-key, swipe and tap
  navigation that reads on a phone, published as a private link. Use when the user asks for
  slides, a deck, a presentation, a visual brief or explainer, or "make a deck on/from ...".
argument-hint: "<topic> | from <file or folder> | [deep research] | update <deck>"
allowed-tools:
  - Bash(python3 *common.py*)
  - Bash(python3 *build_deck.py*)
  - Bash(python3 *check_layout.py*)
  - Bash(python3 *inspect_data.py*)
  - Bash(python3 *calc.py*)
  - Bash(python3 *decks.py*)
  - Bash(python3 *drive_sync.py*)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebSearch
  - WebFetch
---

Request for this run: **$ARGUMENTS**

You are making a slide deck for the user to read, mostly on their phone. A good deck here is
**visual first**: each slide makes one point, says it in the title, and shows it with a chart,
diagram, blocks or a big number. Text is brief. Every figure has a source.

**Hard rules.**

- **Numbers come from files and scripts, never from memory or mental arithmetic.** Figures from a
  data file go in through data refs (`items_from`, `value_from`, ...). A figure in a sentence
  ("up 23%", "a third of") comes from `scripts/calc.py`. A figure from the web is quoted as the
  source states it, with the source on the slide.
- **Never invent data.** If a slide needs a number you do not have, cut the slide or say on it
  what is missing.
- **No identifiers on any slide**: no card or account numbers (full, masked or last 4), PAN,
  Aadhaar, folio or demat IDs. `build_deck.py` refuses a deck that has one; take it out, don't
  work around it. Amounts and categories are fine. The deck is for the user.
- **Decks are personal and never enter git.** Everything the skill writes goes in WORKROOT's
  `data/`. Never write a deck, its JSON or research notes outside `data/`, and never `git add` one.
  The repo's hook refuses any `.html` outside a skill's `assets/`.
- **Names stay out of this skill.** Which tools, vendors and folders the user's data comes from
  goes in `data/notes.md`, never in a tracked file.
- **Publish privately.** Never share a deck, change its visibility or post its link anywhere unless
  the user asks.
- **Don't ask a string of questions.** Make sensible choices and state them in one line. Ask one
  question only when the topic is genuinely ambiguous, for example two different decks fit the
  request.

## Step 0: working folder, notes, cloud copy

Run every command from `${CLAUDE_SKILL_DIR}`. Everything personal sits in a working root's `data/`
(WORKROOT). The root is `--root`, else `$SLIDES_ROOT`, else this skill's folder when its
gitignored `data/` exists (`python3 scripts/common.py --where`). If none, ask the user where to keep
decks (in Claude Code offer to set `SLIDES_ROOT` in their settings; in the Claude app use a
temporary folder and the cloud copy). Never create `data/` inside an installed plugin folder. Pass
`--root WORKROOT` to every script when it is not this skill's folder.

**First run** (no `data/notes.md`): copy `notes-template.md` to `data/notes.md` and
`profile-template.json` to `data/profile.json`. Don't interview the user about them. Fill them in
as preferences come up.

Read `data/notes.md`: the user's style preferences and where the inputs of recurring decks live.

**Cloud storage.** Follow `references/cloud_sync.md`. With a lasting folder (Claude Code): sync when
asked, and push after a run that built a deck. With a temporary folder (the Claude app): pull first,
push at the end. No file-storage connector and a temporary folder: say the deck lasts only as long
as its published link and this session.

## Route the request

| Request | Do |
|---|---|
| "a deck on <topic>" | Steps 1–5, researching the topic in Step 1 |
| "a deck from <report / file / data>" | Steps 1–5 with the file as the main source |
| "explain <skill / codebase / design>" | Steps 1–5, reading the code in Step 1 |
| "deep research", "research it properly", "thorough" | Step 1's deep research, then 2–5 |
| "change / update <deck>", feedback on a deck | Step 6 |
| "my decks", "the link to ..." | `python3 scripts/decks.py list` |

## Step 1: gather the material

Decide the deck's job in one sentence (what the user should know after reading it) and its length:
**8–12 slides** unless asked otherwise (`profile.json` `max_slides` is the warning line). Then
gather from whichever applies; most decks use more than one.

**A data file or report** (the output of another tool, a CSV, an export):
- JSON or CSV: run `python3 scripts/inspect_data.py FILE --name NAME` to see its paths, then read
  only the parts you need. These are the figures the slides will point at.
- A Markdown or text report: its figures are already computed. Quote them exactly and cite the
  report with its date. If the same report has a JSON beside it, use the JSON through data refs
  instead.
- Note in `data/notes.md` where this kind of file lives, so the next deck finds it without asking.
- Insights: look for what changed, what is largest, what is unusual, and what to do. Compute every
  comparison with `calc.py` (`change`, `share`, `ratio`, `cagr`, `annual`, `sum`) on refs into the
  file. A slide whose number came from your head is a bug.

**A codebase, skill or design to explain:**
- Read the entry points first (`SKILL.md`, `README.md`, the main scripts' docstrings), then follow
  what calls what. Grep rather than reading every file.
- Map it into: inputs → processing steps → decisions/judgment → outputs, plus the external sources
  it queries and the frameworks it is built on. These become `layers`, `flow`, `blocks` and `svg`
  slides.
- Counts (scripts, tests, data sources) come from commands (`ls`, `grep -c`, a test run), with
  the command's subject as the `source`.
- Explaining a framework the code implements (a scoring method, an academic model) may need web
  research below. Cite the origin.

**A topic, from the web:**
- **Quick** (default, or `profile.json` `research: quick`): 4–8 searches, then fetch the 3–6 best
  primary sources (official statistics, filings, papers, the organisation itself) over aggregators.
- **Deep** (when the user asks, or the profile says `deep`): use the host's deep-research skill if
  one is available; otherwise split the topic into 3–5 sub-questions and research each (in
  parallel with subagents where the host has them), with primary sources and dates. Expect it to
  take a while and say so in one line.
- Either way, write the findings to `data/skill-data/research/<date>-<slug>.md`: each claim on
  its own line with its figure, its source URL and the date it refers to. Slides are built from
  this file, not from memory. Note where sources disagree.
- Prefer recent data and give its date on the slide ("FY25", "as of Sep 2026"). If a key number
  is older than about two years, say so in the `source`.

## Step 2: storyline first

Write the slide titles before any content: one line each, in order. Read them alone. They should
tell the whole story.

- **Titles are claims**: "Delivery is now the second-biggest category", not "Category breakdown".
- Shape: title → the answer up front (`statement` or `stats`) → 4–8 evidence slides, one point
  each → what it means / what to do (`blocks` or `compare`) → `sources`. Add `section` dividers
  only past ~12 slides.
- One idea per slide. Two ideas make two slides.

## Step 3: pick the visual, then the words

For each slide, choose the type that shows its point (details in `references/deck_format.md`):

| The point is... | Type |
|---|---|
| one or a few headline numbers | `stats` (or `statement` for one number in a sentence) |
| which is biggest / how they rank | `bars` (sorted, top 6–8, rest as "Other", the subject highlighted) |
| how it moved over time | `columns` (highlight the month or year the title talks about) |
| what it is made of | `share` |
| a process, pipeline, how a request flows | `flow` |
| how a system is put together | `layers`, or `svg` for anything with branches or loops |
| a few parallel ideas, findings or actions | `blocks` |
| options and a recommendation | `compare` with `pick` |
| when things happen | `timeline` |
| exact figures someone will look up | `table` (rarely, at most 8 rows) |

`bullets` is the last resort. If a slide turns into bullets, ask whether it is really `blocks`, a
`flow` or two slides.

**Words:** cut until it hurts. Titles up to about 10 words; block or step text one short line;
no sentence that repeats the visual. Put context you want to keep in `notes`, not on the slide. Use
`takeaway` for the "so what" when the title alone doesn't carry it. Give every data slide a short
`source` ("spending check-up, Oct 2026", "RBI, Sep 2026", "repo: 12 scripts").

**Custom diagrams (`svg`):** draw with a `viewBox`, simple boxes, arrows and labels, a 14–18px
equivalent text size, and theme colours (`currentColor`, `var(--accent)`, `var(--ink-2)`,
`var(--line)`, `var(--c2)`…) so they work in light and dark. Keep labels short; at most ~10 boxes.

## Step 4: build and check

1. Write the deck to `data/skill-data/decks/<date>-<slug>.deck.json`, with the data files it
   refers to in its `data` mapping (absolute paths for files elsewhere on this machine).
2. `python3 scripts/build_deck.py data/skill-data/decks/<file>.deck.json [--root WORKROOT]`
   - **Errors**: fix the deck and build again. Cut text, add the missing `source`, split a crowded
     slide, remove an identifier. Never raise a limit or drop a check to get past one.
   - **Warnings**: fix them unless there is a clear reason not to.
3. Where a browser is available (Claude Code):
   `python3 scripts/check_layout.py <html> --shots <scratch folder> --slides 1,N,M`. It reports
   slides that need scrolling on a phone (390×844) or a laptop (1366×768). Fix any it lists by
   cutting or splitting, then look at 2–3 phone screenshots: the title, the densest slide and one
   chart. Check that it reads, not just that it fits. With no browser the script says so; skip it.

## Step 5: deliver

- **Claude Code with an artifact/publish tool:** publish the built `.html` as a **private** page
  (icon: `slides`; description: the deck's job in one sentence). The file already meets the page
  contract (colour tokens, dark mode, phone layout, no external resources), so don't restyle it.
  If the tool requires loading its design guidance first, do so, but keep the template. Then
  `python3 scripts/decks.py link <id> <url>`. Rebuilding and republishing an existing deck goes to
  the same URL (from `decks.py show <id>`).
- **The Claude app:** present the built HTML file as an artifact or file preview if the app can;
  otherwise give it as a file. Use the link if one was published from the laptop.
- **No publishing tool:** give the file path. It opens in any browser.
- Sync (Step 0) if a cloud copy is set up.

Reply in a few lines: the link (or path), the slide count, how to move (← → or swipe; tap the
left/right edge; O for all slides; T for light/dark; N for notes), the sources behind the numbers,
and any warning you left in on purpose. If the deck covers money, end with **Terms used**: the full
form and a one-line meaning of each finance term on the slides. On an investment deck, the sources
slide carries: *Analysis, not advice from a licensed financial adviser.*

## Step 6: change an existing deck

`python3 scripts/decks.py show <id>` gives the deck's files and link. Edit its `.deck.json` (or
the resolved `.json` when the source data is not on this machine, such as in the Claude app), build
again under the same `id`, and republish to the same URL. Record anything the feedback teaches
about the user's taste in `data/notes.md`, under Style, so the next deck starts there.
