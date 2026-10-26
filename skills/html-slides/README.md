# html-slides

A Claude skill that builds visual slide decks as one self-contained HTML file: charts, diagrams,
blocks and big numbers with brief text, each figure sourced. It works from a topic (quick web
research, or deep research when asked), from a report or data file another tool wrote, or from a
codebase to explain. The deck reads on a phone and on a laptop:

- **Navigation:** ← → (also Page Up/Down, Space), swipe, tap the left or right edge, or the
  on-screen buttons; Home/End; **O** shows every slide's title; **T** switches light/dark; **N**
  shows speaker notes; **F** goes full screen. The slide number is in the URL (`#4`).
- **Layout:** each slide type has a phone layout (bars stack their labels, flows and timelines
  turn vertical, grids collapse to one column). It follows the system's light or dark mode.
- **Self-contained:** no external fonts, scripts or images, so it works offline and as a private
  claude.ai page.

Claude does the judgment: what the story is, what each slide shows, which sources to trust.
Tested Python scripts (standard library only) do everything with one right answer: number
formatting (Indian or international), bar lengths, shares that add up to 100%, changes and
growth rates, pulling figures out of a data file, the checks, and the HTML.

## How a deck is made

1. **Gather.** Research the web (findings saved with sources), read a data file or report, or read
   a codebase.
2. **Storyline.** Slide titles first, each one a claim.
3. **Deck JSON.** One file listing the slides (format: `references/deck_format.md`). Figures from a
   data file are referenced, not copied: `"items_from": {"ref": "spend:by_category", "top": 6}`.
4. **Build.** `scripts/build_deck.py` resolves the references and checks the deck: word limits,
   a source on every data slide, no card, account, PAN or Aadhaar numbers, no script in a diagram.
   Then it writes the HTML.
5. **Layout check.** `scripts/check_layout.py` opens the deck in headless Chrome or Chromium at
   phone and laptop sizes, reports slides that need scrolling, and takes screenshots to review.
6. **Publish.** It goes up as a private page when the host has a publishing tool, and the link is
   recorded in the deck index.

| Script | Does |
|---|---|
| `build_deck.py` | deck JSON → checked, resolved JSON + HTML; updates the index |
| `lint.py` | the checks (used by `build_deck.py`) |
| `render.py`, `assets/deck.html` | the HTML and its template |
| `deckdata.py` | number formatting, shares, lengths, data references |
| `calc.py` | change, share, ratio, CAGR, annual, sum: the numbers in insight sentences |
| `inspect_data.py` | lists the paths in a JSON or CSV file, for data refs |
| `check_layout.py` | headless-browser overflow check and screenshots |
| `decks.py` | the deck index: list, show, record a published link |
| `common.py` | the working folder (`--where`) and the profile |

## Where the data lives

Nothing personal ships with the skill, and **no deck ever enters git**. A deck can carry your
own figures, so everything a run writes goes in a working folder's `data/` (gitignored):
`--root`, else `$SLIDES_ROOT`, else this folder's own `data/` in a checkout.

```
data/
  notes.md                   your style and where recurring decks' inputs live (from notes-template.md)
  profile.json               accent colour, number style, currency, slide limit, research depth (from profile-template.json)
  raw/                       source files you drop in
  skill-data/
    decks.json               index: every deck, its date, files and private link
    decks/<id>.deck.json     the deck as written, with data references
    decks/<id>.json          the deck with every reference resolved
    decks/<id>.html          the built deck
    research/<id>.md         research findings with sources
```

The repository's `.gitignore` ignores every `.html` except a skill's `assets/*.html`, and
`hooks/pre-commit` refuses a staged `.html` anywhere else.

## Cloud copy

`scripts/drive-sync.json` and `references/cloud_sync.md` keep `notes.md`, `profile.json`, the
index and each deck's JSON in your cloud storage (both ways), and bring down anything you drop into
the cloud folder's `raw/`. The HTML is not synced: it is rebuilt from the resolved JSON, and you
view a deck through its private link, which works in the Claude app and in a phone browser
signed in to the same account.

## Install

From this repository's marketplace (`marketplace.json`), plugin `html-slides`. In Claude Code:

    /plugin marketplace add atishbits/claude-skills
    /plugin install html-slides --marketplace atishbits/claude-skills

Turn on auto-update for the marketplace under `/plugin` → Marketplaces so the plugin follows the
latest commit. In the Claude app, add the marketplace `atishbits/claude-skills` once and install the
plugin. Or symlink this folder into `~/.claude/skills/` from a clone.

The layout check needs Chrome or Chromium (`$CHROME` picks the binary). Without one, the check is
skipped and everything else still works.

## Tests

```
cd scripts && python3 -m unittest discover -s tests -p 'test_*.py'
```

Fixtures are synthetic. A test card number is built at runtime so no valid one is written in the
repository.
