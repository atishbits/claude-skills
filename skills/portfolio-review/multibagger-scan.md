# Scanning the market for candidates

Use this only for an open-ended "scan the market/an index/a sector for strong candidates" request
with no tickers named — the search itself needs narrowing down, not a list of names to check. A
narrower "what else is worth buying" with named candidates goes to `new-ideas.md` instead.

0. **Before anything else, check the scan history:**

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py report
   ```

   Run it with no tickers so it surfaces the "Overdue re-checks" section regardless of what
   today's run is about, and mention any overdue re-check plainly in the final summary even if
   it's unrelated to today's scan. If the request names specific tickers or a sector that overlaps
   anything in the history, also run

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py report TICKER ...
   ```

   and say plainly if a ticker was rejected before, at which stage and why — and say plainly if
   today's numbers look like they might have changed enough to revisit that verdict (a judgment
   call, not automated).

1. **Stage 1 — build the universe (wide, cheap).** Default to `--scan "NIFTY 500"` unless the
   request implies a narrower one ("smallcaps" → `"NIFTY SMALLCAP 250"`, "midcaps" →
   `"NIFTY MIDCAP 150"`):

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_fundamentals.py --scan "NIFTY 500"
   ```

   A full-index scan can take 30+ minutes on tickers not already cached (each one costs a
   fundamentals fetch, a chart fetch and the NSE calls), so run it as a background/long-running
   command rather than a blocking foreground call. It rewrites `screen-<today>.json` after every
   batch of 50, and a same-day re-run resumes quickly from that day's per-ticker cache. If
   `multibagger_screen.py` later warns the scan is incomplete, finish or re-run the scan first.

   For a request scoped to a sector or theme with no clean index match, fall back to a named
   ticker list the same way `new-ideas.md` step 1 sources one, and run `--screen` instead of
   `--scan`. For a request about the user's *own* portfolio, skip sourcing entirely and point
   `multibagger_screen.py --source snapshot` at the existing snapshot instead — no scan needed.

2. **Stage 2 — mechanical pre-filter (cheap, deterministic).** Run

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/multibagger_screen.py
   ```

   The defaults (`--roce-min 18.0 --profit-growth-min 15.0 --pe-growth-multiple 2.5
   --cfo-to-pat-min 0.6 --pct52-max 20.0 --pct200dma-max 0.0`) are the standing bar; only override
   them if the user explicitly asks for a stricter or looser one. If it prints a warning that the
   scan is incomplete or that tickers failed to fetch, say so plainly in the summary — the screen
   covered only a partial universe. Then record **every** screened ticker — not just survivors —
   in one call, pointing at the shortlist file it just wrote (the path on its final `Wrote ...`
   line):

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py record-shortlist data/skill-data/multibagger-shortlist-<today>.json --stage mechanical
   ```

   Each stock is logged with its `quality_verdict` (pass/fail/borderline) as the outcome and the
   script's own mechanical `reason` (e.g. `roce short 8.9%; not near a local low`) — don't record
   Stage 2 ticker by ticker. This is what makes coverage build up automatically run over run.

3. **Stage 3 — judgment narrowing (prose, not scriptable).** For each survivor (pass + near a
   local low) and each borderline ticker worth a second look, apply the same real-sourcing
   judgment `new-ideas.md` already documents for TAM/optionality/structural-threat reads (a
   government-backed free alternative eating a paid moat, a single-customer ceiling, a market
   already near its highs rather than its lows despite passing the mechanical bar). Record the
   verdict:

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py record TICKER judgment <pass|fail> "<why>"
   ```

   Say plainly if nothing survives this stage — that is a valid, expected outcome of a strict bar,
   not a failure of the process.

4. **Stage 4 — full deep dive (expensive, thorough).** Run SKILL.md's existing Step 3a–3g on
   whatever survives Stage 3, capped at **3** names by default (more only if the user asks) — same
   rules as `new-ideas.md` step 4 (3b–3d, then 3g for anything rated BUY/SELL). Record every rated
   ticker to `rating_ledger.py` as usual, and additionally record the deep-dive stage to
   `scan_history.py`:

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py record TICKER deep-dive <pass|fail> "rated BUY/HOLD/SELL, see rating_ledger" [--next-checkin YYYY-MM-DD]
   ```

   Outcome is `pass` for BUY or HOLD (still worth tracking) and `fail` for SELL (done with it for
   now). `--next-checkin` only when a calendar reminder was actually set that run; it is what
   step 0's "Overdue re-checks" surfaces later, and a later entry without one (same day or not)
   does not clear it.

Close with: *Not investment advice — verify prices and figures before acting.*
