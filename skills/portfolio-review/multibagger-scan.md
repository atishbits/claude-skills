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
   them if the user explicitly asks for a stricter or looser one. Then, for **every** ticker in its
   output JSON (`data/skill-data/multibagger-shortlist-<today>.json`) — not just survivors —
   record it:

   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/scan_history.py record TICKER mechanical <pass|fail|borderline> "<one-line reason from the script's own output>"
   ```

   This is what makes coverage build up automatically run over run.

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

   (`--next-checkin` only when a calendar reminder was actually set that run.)

Close with: *Not investment advice — verify prices and figures before acting.*
