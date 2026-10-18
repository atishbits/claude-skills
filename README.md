# claude-skills

A collection of Claude Code skills I'm building.

## Invariant: no personal data, ever

**This repo holds tools. It never holds anyone's financial or personal data.** Not broker exports
or holdings, not per-stock notes carrying quantities and cost, not generated portfolio reports,
not tax paperwork — no ITR, Form 16, 26AS, AIS, capital-gains or contract-note files — and no
identifiers (PAN, Aadhaar, demat or bank account numbers).

This matters more here than in a normal repo: a skill directory is designed to be **symlinked into
a working folder that does hold that data**, so the scripts run from inside this checkout and a
`git add` in the wrong place would publish it.

Four things enforce it, and all four should stay:

1. **`.gitignore`** excludes what a run produces — `data/`, `stocks/`, `PORTFOLIO.md`,
   `*holdings*.csv`, `__pycache__/` — with the one exception of a skill's
   `holdings-template.csv`, which contains only made-up rows.
2. **`hooks/pre-commit`** blocks a commit whose staged files look like data: broker exports, tax
   documents, spreadsheets and statements (`.xlsx`, `.pdf`, `.ofx`, …), generated reports, or
   content matching a PAN, Aadhaar, demat ID or a broker export header. Enable it in a fresh clone
   with:

   ```
   git config core.hooksPath hooks
   ```

   `git commit --no-verify` overrides it. That is for a genuine false positive, not for "just this
   once".

   The hook also reads prose, because a leak is as often a sentence as a file:

   - **`.private-terms`**, a gitignored file at the repo root that you write yourself. One term or
     extended regular expression per line, `#` for a comment: the broker, platform and bank names
     you use, the tickers you hold, anything else that must not appear here. A commit whose staged
     content or file paths match any line is blocked, whatever the case, and even on a line that
     looks like an example. The hook reports the line number that matched, not the term.

     ```
     # .private-terms
     acmebroker
     examplebank
     \bSTOCKHELD\b
     ```

     Without the file the check is skipped, so create it in every clone you commit from.
   - **A weight beside a ticker.** A percentage "of the book" or "of my portfolio" on, or just
     after, a line with a ticker-like word is blocked. Write examples with the placeholder tickers
     (`STOCKA`, `BANKX`, `EXAMPLEA`) or as a fraction ("a quarter of the book").
3. **Sample data is invented.** Any example in a skill uses placeholder tickers and round numbers,
   never a real position.
4. **No vendor is named in a generic skill.** A skill describes its input by format ("a broker
   export with these columns", "the platform's holdings report"). Which broker, platform or bank
   you use goes in that skill's gitignored `data/notes.md`, which the skill reads at runtime.

A skill that needs personal input should read it at runtime from the user's own project folder,
and say so in its README, rather than shipping a copy here.

## Structure

Each skill lives in its own directory under `skills/`, following the standard
Claude Code skill format (a `SKILL.md` with frontmatter, plus any supporting
files/scripts the skill needs).

```
skills/
  <skill-name>/
    SKILL.md
    ...
```

## Adding a new skill

1. Create `skills/<skill-name>/SKILL.md`
2. Add frontmatter with `name` and `description`
3. Write the instructions the skill should follow
4. Keep the invariant above: no real data in examples, and anything the skill generates from a
   user's own files belongs in `.gitignore`

## Installing as a plugin

`.claude-plugin/marketplace.json` makes this repository a plugin source. It lists the skills that
work without a local project folder: `news-briefing` and `portfolio-review`. In Cowork, add the
marketplace `atishbits/claude-skills` once and install each plugin; in Claude Code:

    /plugin install news-briefing --marketplace atishbits/claude-skills
    /plugin install portfolio-review --marketplace atishbits/claude-skills

An installed plugin follows this repository: update the plugin to get the latest commit. The
other skills read a working folder on your own machine and are installed by symlink, as described
above.

## License

[MIT](LICENSE). Take these, fork them, adapt them.

The skills that touch money — `advance-tax`, `itr2-filing-assistant`, `portfolio-review`,
`bond-portfolio-monitor` — are tooling for my own use, published in case they are useful. They are not tax, legal or investment
advice, and the MIT warranty disclaimer means exactly what it says: verify anything that matters
with your own CA or adviser before acting on it.
