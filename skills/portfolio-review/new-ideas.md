# Ideas outside the portfolio

Use this only when the user asks what else is worth buying: stocks they don't hold, or new ideas
for a sector.

0. **If there is no `PORTFOLIO.md` yet** — no holdings CSV in the project — skip straight to step
   2 with the tickers the user named. `--screen` works without a portfolio; the sector and swap
   reasoning below simply does not apply, and you should say so rather than inventing a book.
1. **Pick candidates from sectors where the book is thin.** Read the sector list in
   `PORTFOLIO.md` and avoid adding to the top of it. Remember that the CSV's tags understate some
   themes, e.g. auto-cycle names tagged as Capital Goods.
2. **Screen them, never pick from memory:**

   ```
   python3 scripts/fetch_fundamentals.py --screen TICKER ...
   ```

   It uses the same signal rows, technicals and one-off flags as the holdings, writes
   `data/screen-<today>.json`, and leaves the snapshot and `PORTFOLIO.md` alone. Held tickers are
   skipped, because they belong in the normal run. Ratios move every quarter, so a list from
   memory is stale.
3. **Drop the row-1 names whose earnings are not normal, before researching anything.** The screen
   carries `growth_ranges.earnings_above_trend`, `cash_flow.cfo_to_pat` and
   `ratio_history.roce_fading`. A row-1 placement built on last year's ROE at 1.4x the company's
   own five-year figure is a cheap P/E on peak earnings, which is what four of the five failures
   below turned out to be. This is a first cut, not the whole test: Natco read in trend and was
   still on peak earnings (SKILL.md 3d).
4. **Research the survivors** with the same checks as a holding (SKILL.md 3b–3d), then run
   the 3g verification on anything you would call a BUY. Expect most to fail, and say why each one
   did. On 11 Sep 2026, four of five failed:
   - Lupin: peak earnings, with US exclusivities ending.
   - Colgate: a reinvestment phase, with more ad spend and slower earnings, plus a CEO exit.
   - IRCTC: flat profit, with growth shifting to low-margin catering.
   - Hero survived, but only after the target list was corrected (see 3c).
5. **Size a BUY as a swap** if it adds to a theme that is already heavy, and name what it
   replaces, not only what funds it.
6. **Don't write `stocks/<TICKER>.md`** for a stock the user doesn't hold unless asked.
   `PORTFOLIO.md` only picks notes up for holdings, so a note is only useful once the stock shows
   up in the holdings CSV.

Close with: *Not investment advice — verify prices and figures before acting.*
