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
- A skill that needs personal input reads it at runtime from the user's own project folder and
  documents that in its README — it does not ship a copy here.
