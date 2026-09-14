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

Three things enforce it, and all three should stay:

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
3. **Sample data is invented.** Any example in a skill uses placeholder tickers and round numbers,
   never a real position.

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

## License

[MIT](LICENSE). Take these, fork them, adapt them.

The skills that touch money — `advance-tax`, `itr2-filing-assistant`, `portfolio-review` — are
tooling for my own use, published in case they are useful. They are not tax, legal or investment
advice, and the MIT warranty disclaimer means exactly what it says: verify anything that matters
with your own CA or adviser before acting on it.
