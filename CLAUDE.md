# Working in this repo

This repo holds Claude Code skills as tooling. **It must never contain personal or financial
data** — broker exports or holdings, per-stock notes with quantities and cost, generated portfolio
reports, tax paperwork (ITR, Form 16, 26AS, AIS, capital-gains statements, contract notes), or
identifiers such as PAN, Aadhaar, demat or bank account numbers. The README states the invariant in
full; `hooks/pre-commit` and `.gitignore` enforce it.

Why the risk is real: a skill directory here is symlinked into a working folder that *does* hold
that data (for `portfolio-review`, `~/Documents/mygitprojects/atishstocks`), so the scripts execute
from inside this checkout and a careless `git add` would publish someone's portfolio.

Rules when you commit here:

- Stage named paths. Never `git add -A` or `git add .` without reading `git status` first.
- Never pass `--no-verify`. If the hook fires, the default assumption is that it is right; if it is
  genuinely a false positive, say so and let the user decide.
- Examples in skills use invented tickers and round numbers, never a real position.
- A generic skill never names a vendor, platform, bank, broker or other tool its user happens to
  use, nor another skill that is specific to one. Describe the input generically ("bond
  interest", "a broker export") and document the file format. Which vendor a figure comes from,
  and how to refresh it, is personal: it goes in that skill's gitignored `data/notes.md`, which
  the skill reads at runtime. A skill built for one platform may of course name that platform.
- A skill that needs personal input reads it at runtime from the user's own project folder and
  documents that in its README — it does not ship a copy here.
- If a skill has a `scripts/` folder, its deterministic logic gets unit tests under
  `scripts/tests/` (`python3 -m unittest discover -s tests -p 'test_*.py'`, run from that skill's
  `scripts/` folder — no dependency beyond the standard library). `hooks/pre-commit` runs every
  skill's suite whenever a `.py` file is staged and blocks the commit on a failure, so a skill's
  tests must already be green before you stage its scripts.

## Prefer a deterministic script over a prompted step

This applies to every skill in this repo, not just the one you're touching. Where a step in a
skill is arithmetic, parsing, classification, or anything else with one correct answer for a given
input, put it in the skill's Python script and have the model call the script and read its output
— not describe the steps in SKILL.md and trust the model to carry them out by hand. A model
re-deriving a median, a CAGR, or a same/different-basis comparison from prose instructions is the
same computation done less reliably and less cheaply than a function call, and a wrong instance is
much harder to catch than a wrong test.

Two concrete tells from this session's work on `portfolio-review`, worth applying elsewhere:

- **If you catch yourself writing "compute X by doing A, then B, then C" in a SKILL.md bullet,
  that's a function**, not a paragraph. `three_year_case.py` and `tax_lots.py` exist because the
  3-year return case and the per-lot LT/ST math were originally prose instructions the model had
  to carry out inline — the same category of arithmetic 3g already has to double-check by hand for
  everything else in the note. Moving it into a script removed the error class instead of adding a
  check for it.
- **A skill file should read short because the work moved, not because it was deleted.** Trimming
  a bullet's prose is only real progress if the thing it described still happens somewhere
  deterministic; cutting the explanation without cutting the requirement just hides the gap.

This doesn't mean every judgment call becomes a script — sourcing a consensus target, reading a
concall transcript, or deciding whether a growth number is operational still needs a model reading
real sources with judgment. The line is whether the step has one correct answer given its inputs:
if it does, script it; if it's genuinely a judgment call, it stays in SKILL.md, but should still
read its inputs from a script's output rather than from numbers the model half-remembers or
recomputes inline.
