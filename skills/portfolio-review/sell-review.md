# Sell review

Use this when the user asks about selling, trimming or booking profit on a holding, asks whether a
stock has peaked, or reports a sale. SKILL.md routes here; every step it names by number stays as
SKILL.md writes it, and this file only adds what selling needs.

Nothing here predicts a top. The point is to notice when a rise rests on a stretched P/E rather
than on earnings, to sell in parts so a false alarm is cheap, and to weigh the tax saved by waiting
against what a normal pullback would cost. Every number in a sell recommendation comes from a
script; none is worked out in prose.

## The flow

1. **Steps 0 and 1 as usual**: sync in, then fetch the ticker.
2. **Run the sell script first:**

   ```
   python3 scripts/sell_signals.py TICKER
   ```

   It prints the case (tier, business kind, how much of the 3- and 6-month rise came from profit
   and how much from P/E, the P/E's percentile in the stock's own band, the three peak tests), the
   suggested plan (step 1 now, step 2 on a trigger, a core kept), the step-2 trigger prices, and,
   for each account the holding sits in, the lots FIFO would sell with gain, short- or long-term,
   estimated tax and net, and a total line. Under each account it gives the break-even drop against
   the stock's typical pullback (`max_drawdown_1y_pct`) and the advice that follows from it. If a
   plan is already open, it prints that plan and how many shares have been sold since it opened.
   For a stock only on watch it shows "if you trimmed a third" as a preview, not a plan.
3. **The judgment the script cannot make**, by reference to SKILL.md: 3b validation of the inputs,
   3c consensus and red-flag searches (auditor, governance, pledge, promoter selling, value
   migration), the 3d peak test and the rest of 3d, and 3g verification for any SELL. This is
   where a flag can be overruled, for example when EPS is about to jump on guided capacity that
   is already being commissioned, so the stretch will be earned within a few quarters. Say so in
   one sentence when you overrule it.
4. **Rate it**: HOLD, or SELL / trim with the plan steps, under the rules in the next section. Then
   record it to the ratings ledger as SKILL.md 3g says. A SELL that the user accepts gets its plan
   saved:

   ```
   python3 scripts/sell_signals.py TICKER --open-plan "deciding sentence"
   python3 scripts/sell_signals.py TICKER --open-plan "deciding sentence" --full-exit
   ```

   The script sizes step 1, step 2 and the core from the tier and the business kind; a weak
   business gets no core. `--full-exit` is for a deliberate exit (half now, the rest on the
   trigger, no core): the crisis case, or an exit window the script rates only "watch". It refuses
   to open a second plan for the same ticker; when a plan is finished or abandoned, close it with
   `--close-plan`.
5. **Scorecard** in the Step 4 format, with the sell lines Step 4 lists.
6. **Offer a calendar reminder for the step-2 re-check** at the trigger's review date or the next
   result, at 8–9 AM IST by default (the user's preference), not as an all-day event.
7. **If the user reports a sale**, record it and show the year's totals (next sections).
8. **End with the glossary footer** (`python3 scripts/glossary.py --terms "..."`, SKILL.md Step 4)
   and then the disclaimer, then sync out with Step 5.

## When the rating is SELL

HOLD stays the default. SELL is reached in two named cases, and SKILL.md 3d applies them on every
review, not only in a sell review.

1. **Exit window (profit booking).** The stock is up on P/E stretch rather than earnings (the
   `sell_signals.py` flag), and especially when it is a weak business (signal row 3 or 4, ROCE
   fading, red flags). A rally is the cheapest time to leave a bad business. Rate it SELL with a
   staged plan: a weak business's plan runs to a full exit, not to a kept core. For a strong
   business the same flag gives a SELL / trim with a core kept. The trigger is the stock's own
   stretch, not the user's profit (3e): show the profit, but it is not the reason.
2. **Crisis exit.** The business is breaking and the evidence agrees from independent sides:
   current analyst calls lean Sell or Reduce (3c sourcing rules: dated, post-result), *and* the
   frameworks agree (red flags fired, ROCE fading, earnings below trend, value migrating away, or
   promoter selling or pledging). Rate it SELL with a full-exit plan, whether the position is in
   profit or at a loss. A loss here also has tax value, since a short-term loss offsets gains:
   say so, and show what it offsets with `python3 scripts/gains_log.py report`.

Outside these two cases, rate HOLD. A change from HOLD to SELL goes into the ratings ledger like
any other, so `rating_ledger.py report` can later show whether the SELL calls helped, and whether
the skill has become too cautious or too eager.

A compounding machine (high ROCE with steady earnings growth) is not sold because it rose. When
it does flag, the script keeps a larger core and the trims are smaller; let them be.

## Which shares a sale takes: FIFO per account

Shares in one demat account are sold oldest first, and tax follows that order. The user cannot
pick a lot inside an account, so never offer that choice. The only choice is which account to sell
from, and that is why the script prints each account separately. Cost decides that choice and the
tax; it never decides whether to sell (3e).

A lot dated before 1 Feb 2018 or with no date shows "tax not estimated" and is left out of the
totals with a note. Say so beside the total rather than estimating it.

## Reading the sell lines in "Worth a look"

A portfolio-wide run (Step 2) shows mechanical sell flags in `PORTFOLIO.md`:

- `- **STOCKA** — sell: <flag>` — a new or stronger case. Offer a sell review; do not research it
  unasked.
- `- **STOCKA** — sell plan open (...); step 2 at ₹N` — a plan is open. When it ends in
  `STEP 2 TRIGGER HIT`, lead the Step 2 report with it: the step-2 trim is due for a look.
- `- still stretched, no change: STOCKA, STOCKB` — flagged before, no stronger now. One line, no
  action.

## Recording a sale

The skill records only sales the user reports or the broker report contains. It never assumes a
recommended trim was done.

**On the phone, or anywhere without the broker report**, record the sale and show the totals:

```
python3 scripts/gains_log.py record STOCKA 10 150 --date 2026-10-20 --account brokera --charges 20
python3 scripts/gains_log.py report
```

`--charges` is the deductible sale expenses (brokerage, exchange charges, GST on them; not STT).
The script matches the sale FIFO against that account's lots and stores the gain and estimated tax
as unconfirmed. It refuses a sale dated on or before that account's export date, because the
export already contains it. Quantity and average cost still come only from the broker export, so until a
newer one arrives write "sold on <date>, not yet in the export" beside the position. Then re-run
`sell_signals.py TICKER` so an open plan shows the step as done.

**On the laptop, with the broker's tax P&L report**:

1. Convert the report to the CSV in `realised-gains-template.md` (beside this file). Which report
   to download, and where, is in the user's `data/notes.md`.
2. `python3 scripts/gains_log.py reconcile PATH` confirms the logged sales with the broker's
   figures, imports sales never logged, and lists mismatches. It also lists as `unmatched` every
   logged, unconfirmed sale at an account the report covers, dated inside the report's date range,
   that no report row matches (usually a mistyped date or quantity). Those stay unconfirmed and
   still count in the totals. Show the user every mismatch and unmatched sale; do not resolve one
   by guessing.
3. `python3 scripts/gains_log.py export` writes `data/skill-data/realised-gains-FY<fy>.json`, the
   hand-off file for tax planning (format in the README).

FY totals are each account's broker figure up to that account's export date plus the logged
sales after it, so nothing is counted twice; an account exported as a plain CSV has no broker
figure, so all its sales are added. A baseline can include mutual funds where the broker reports
them.

## The scorecard and the close

The scorecard follows Step 4, with the sell lines added: plan step, the account and lots FIFO would
sell, gain / tax / net, break-even drop against the typical pullback, the step-2 trigger prices,
and the next check-in. Copy the figures from the script's output.

Example (invented ticker, round numbers):

```
STOCKA — Rating: SELL / trim  |  Row 3 (high P/E on weak returns)
As of: 2026-10-23 09:30 IST | Purchase: not logged
P/E 60x, ROE 9%, ROCE 8%
Consensus Hold, avg TP ₹140 = 7% downside (2026-10-15, 3 of 4 post-result)
3-Year case: base 4% vs bear -8% vs Nifty hurdle 11%/yr — doesn't clear
Action: sell 50 from brokera now (step 1); the rest only if step 2 triggers
Sell plan: step 1 of 2 — sell 50 of 100 now; step 2 below ₹132 or the 50 DMA ₹140; no core
Lots (FIFO, brokera): 50 sh, gain ₹2,500 ST, tax ₹500, net ₹7,000
Break-even drop 3% vs typical pullback 25% — trim now
Next check-in: 2026-11-10 08:30 IST (step-2 re-check)
```

End the reply with the glossary footer from `glossary.py`, after the prose, then:
*Not investment advice — verify prices and figures before acting.*
