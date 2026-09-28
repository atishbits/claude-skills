# Known gaps

**Update:** item 3 (aggregate track record) is now built — see `scripts/rating_ledger.py`,
wired into SKILL.md 3g/Step 4. Item 2 (entry/exit levels) is partially addressed —
`scripts/calendar_notes.py` now deterministically flags when price is near a technical
re-look level, but there is still no scored entry/exit band. Item 1 (market-wide scan) is
still fully open. Kept below for the historical record of what each gap originally was.

Surfaced while writing a technical-marketing deck that walks through the skill end to end and had
to check every claimed step against `SKILL.md`, `CHEATSHEET.md` and the scripts rather than
describing it from memory. Each item below is a real gap in what the skill does today, not a
wording nitpick.

## 1. No true market-wide idea scan

`new-ideas.md` screens candidates the user or model already named — from a thin sector in the
book, or a named secular theme. There is no step that scans a sector or index for candidates on
its own. That's a meaningful gap against "find me multibagger ideas in a sector" as a request:
today, answering it well still depends on the model already knowing plausible tickers, which is
exactly the "never pick from memory" failure mode `new-ideas.md` step 2 exists to prevent for the
research phase — it just doesn't reach the sourcing phase.

**Possible fix:** accept an index/sector constituent list (a static file the user drops in, or a
fetch from an NSE sector-constituents endpoint), batch-run `fetch_fundamentals.py --screen` across
it, and apply the existing peak-earnings pre-filter (`earnings_above_trend`, `cfo_to_pat`,
`roce_fading`) before anything reaches research. This is deterministic filtering work, so it
belongs in the script per this repo's own "prefer a deterministic script" rule, not in prose.

## 2. Entry/exit levels stay a prose judgment call

`3d`'s "position within the 52-week range" and the note template's re-look price are written as a
sentence ("add at the 60-day low", "trim toward the consensus average"), anchored to a real level
but not scored or computed. Every other multi-input decision that has one correct answer given its
inputs (the 3-year case, tax-lot LT/ST status) already got moved into a script; this one hasn't.

**Possible fix:** a small script that takes the snapshot's `technicals` block (200/50 DMA, 60-day
range) and the sourced consensus low/high, and returns a scored entry band and trim band with the
anchor named — the same treatment `three_year_case.py` gave the "beats the Nifty hurdle" question.

## 3. No aggregate track record

Every `stocks/<TICKER>.md` note keeps its own rating history via the `(prev ...)` field, so a
single stock's call history is readable — but nothing rolls that up across the book. There's no way
to ask "of the BUYs rated in the last six months, how many are up" without reading every note by
hand. For a tool whose main credibility claim is discipline over gut feel, an aggregate accuracy
read is the strongest trust signal it could offer and currently doesn't.

**Possible fix:** a script that walks `stocks/*.md`'s rating history (or a lightweight ratings log
written alongside it), pulls today's price for each, and reports realised return since each
rating by call type (BUY/HOLD/SELL) and how many are still open. Read-only, no change to the
research flow.
