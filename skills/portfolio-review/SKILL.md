---
name: portfolio-review
description: >-
  Review a long-term Indian equity portfolio from a broker export (Zerodha's by default). Refreshes
  fundamentals from screener.in, places each stock in the P/E vs ROE/ROCE signal rows, rates
  BUY / HOLD / SELL-trim, and writes stocks/<TICKER>.md notes. Use when the user asks
  about their holdings or a named stock: whether to buy, add, hold, trim or sell; a
  portfolio-wide sweep or refresh; or ideas for stocks outside the portfolio.
argument-hint: "[TICKER ...] | [filter, e.g. \"not analysed in 30 days\"]"
allowed-tools:
  - Bash(python3 *fetch_fundamentals.py*)
  - Bash(python3 *close_on.py*)
  - Bash(python3 *three_year_case.py*)
  - Bash(python3 *tax_lots.py*)
  - Bash(python3 *rating_ledger.py*)
  - Bash(python3 *calendar_notes.py*)
  - Bash(curl *)
  - Bash(pdftotext *)
  - Read
  - Write
  - Edit
  - Glob
  - WebSearch
  - WebFetch
---

Request for this run: **$ARGUMENTS**

You are helping with a long-term Indian equity portfolio held on Zerodha. The goal is long-term
compounding: hold quality names, average down where something is genuinely undervalued, and avoid
value traps. Ratings are advisory only — never place or suggest placing an order.

**Where things live.** Everything the skill reads or writes sits under `${CLAUDE_SKILL_DIR}/data/`,
which is gitignored wholesale, and splits into two tiers:
- `data/` directly — what the user provides: a broker CSV (`zerodha_holdings_<date>.csv`) or a
  lot-level Console export (`zerodha-portfolio-<date>.md`, see `zerodha-portfolio-template.md`).
- `data/skill-data/` — everything the skill fetches or writes: the fetch cache, `snapshot-*.json` /
  `screen-*.json`, `stocks/<TICKER>.md` notes and `PORTFOLIO.md`.

Run every command from `${CLAUDE_SKILL_DIR}` so the script's default root (the working directory)
resolves there. If the user keeps their data in a separate folder instead — the safer option if this
checkout is ever shared or backed up somewhere public — pass `--root /path/to/that/folder` (or set
`$PORTFOLIO_ROOT`); everything below still applies, just rooted there instead. Write
`stocks/<TICKER>.md` notes into `data/skill-data/stocks/`, not anywhere else.

**Route the request first:**
- **Tickers the user holds** → Steps 1, 3 and 4.
- **Nothing named** → Steps 1 and 2 only; do not research.
- **A filter** ("not analysed in 30 days", "all row-1 names") → the triage rule at the end of
  Step 2, then Step 3 for the shortlist only.
- **Stocks they don't hold, or "what else is worth buying"** → read
  `${CLAUDE_SKILL_DIR}/new-ideas.md` and follow it. It reuses Steps 3b–3d and 3g.
- **Invoked from a plain question rather than `/portfolio-review`:** take the tickers from the
  user's message. If their scope is unclear and the fetch would be broad, confirm the scope before
  researching.
- **Tax-loss harvesting, gain booking, or "what should I sell for tax reasons"** → Step 1, then
  `python3 ${CLAUDE_SKILL_DIR}/scripts/tax_lots.py --harvest` (3e). No per-ticker research needed
  unless the user then asks about a specific name it surfaces.

## Step 1 — refresh the data

Scope the fetch to what you are actually reviewing:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_fundamentals.py TICKER ...   # refresh just those
python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_fundamentals.py              # refresh everything
```

A subset run refreshes the named tickers and **merges** them into today's snapshot, so the other
holdings keep the rows the last full run gave them. Either way `data/skill-data/snapshot-<today>.json` and
`PORTFOLIO.md` end up complete — every holding in the CSV, not just the one you named.

If today's snapshot does not exist yet, a subset run says so and promotes itself to a full refresh;
let it. That is the first run of the day paying for the network, and it is what makes every later
run in the day nearly free.

Caching is per ticker per day, so a full rebuild from cache takes under a second and no network
calls. Re-run freely — never skip Step 4 to save time.

For stocks the user does not hold, use `--screen` instead (see `new-ideas.md`); it never touches the
snapshot or `PORTFOLIO.md`.

Add `--refresh` to bypass the cache and re-fetch live:
`python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_fundamentals.py --refresh AARTIIND`. Use it only when the user explicitly asks for fresh prices, or when a
same-day price move is itself the subject — the ratios only change quarterly, so on an ordinary
re-run the cache is the correct source.

The run also pulls promoter pledge, insider dealing and large-stake filings from NSE. Those are
cached for a week rather than a day, so only the first run of the week pays for them. `--no-nse`
skips them if NSE is down or slow; say so in your summary if you used it, because the pledge and
insider flags are then simply absent rather than clean.

`PORTFOLIO.md` carries a *Prices fetched* line and the last full-refresh time. If the user asks
about a holding you did not fetch this run, check that line before quoting its price, and say when
it was last fetched rather than implying it is live.

If any ticker reports a fetch failure, say so plainly in your summary. Never rate a stock whose
ratios failed to load — report the gap instead.

## Step 2 — if no tickers were named

Report what changed at the portfolio level and stop. Do not research anything:
- total P&L, the row distribution, and the top of the sector-exposure list
- everything under "Worth a look" in `PORTFOLIO.md`, which is mechanical flags only — call out any
  "financials stale" flag first, since every ratio on that row is suspect
- any holding whose signal row moved since the previous `data/skill-data/snapshot-*.json` — before calling a
  move a "threshold crossing," check `profit_yoy_pct` (or the one-off–adjusted figure in
  `one_offs`) for that ticker. A P/E rising through a row boundary because profit fell is an
  earnings problem, not multiple noise, and must be named as such rather than filed as minor.
  CIPLA's row 4→3 move on 18 Sep 2026 was P/E crossing 30 because TTM profit fell ~39% YoY
  (no one-off), not because the price re-rated — that is the single most material item to flag
  in that run, not an aside.
- the "Risk and concentration" section: beta against the Nifty, the book's 1-year return against
  the index at today's weights, effective positions against the number actually held, and the tail of
  sub-0.5% positions. Report the effective-position count whenever the user asks whether they
  hold too many names — a long list of holdings is not the same number of bets, and that section
  says how many it really is.
  The 1-year return line applies today's weights to each holding's own 1-year price move, so it is
  not the user's actual return: never present it as their performance.
- the biggest rupee P&L contributors and drags across the book, not just the largest percentage
  movers — a small position's 40% gain can matter less than a large position's 8% move. The CSV
  and snapshot have position size and price move; compute this rather than eyeballing percentages.
- when the user asks how the book's sectors compare to the market, not just to itself: the
  snapshot's `sector_weight_pct` is the book's own concentration, not the Nifty's sector
  composition. Get the Nifty's sector weights from a WebSearch (same sourcing discipline as
  consensus targets — dated, from a named source) rather than approximating them, and say plainly
  if you can't find a current breakdown.
- the "Notes on an old template" list, if present

Then tell the user they can run `/portfolio-review TICKER ...` to get a rating on any of them.

**If $ARGUMENTS is a filter rather than tickers** ("everything not analysed in 30 days", "all
row-1 names"), do not research the whole match. Triage it from the snapshot first: signal row,
one-off flags, technicals, profit trend, weight. Then propose a shortlist of the names where
changing the position is plausible, and research only those. List the rest as screened, not rated.
On 11 Sep 2026 the user chose this over full notes for 64 names.

## Step 3 — research each named ticker

For each ticker being researched (named in the request, or on the shortlist from a filter):

### 3a. Read what you already have

1. **The prior note** at `stocks/<TICKER>.md`, if it exists. Its rating, date and reasoning are the
   baseline you are updating. If it recorded management guidance, you will score it this run.
2. **This run's entry** in `data/skill-data/snapshot-<today>.json`. Beyond the ratios, signal row, quarters,
   pros/cons and `technicals` block (see `${CLAUDE_SKILL_DIR}/CHEATSHEET.md`), it carries:
   - `basis` (consolidated or standalone), `fiscal_year_end`, `latest_quarter_end`, `results_stale`
   - `price`, `fetched_at`, and the holdings CSV's `ltp` / `csv_date` / `price_vs_csv_pct`
   - `week52_check` — screener's 52-week range against the chart's own daily closes
   - `pe_runrate` and `pe_runrate_diverges` — latest quarter annualised against trailing P/E
   - `leverage` — gross borrowings, D/E, debt/EBITDA and direction, from the last balance sheet
   - `one_offs` — screener folds exceptional gains into Other Income, so this compares each
     quarter's other income with the company's own norm: `latest.flag` (run-rate P/E flattered),
     `year_ago.flag` (YoY not comparable), `pe_runrate_ex_one_off`, `profit_yoy_ex_one_off_pct`,
     and `other_income_heavy` (profit is mostly other income). Absent for lenders.
   - `cash_flow` — five years of operating cash flow and free cash flow, and `cfo_to_pat`, the
     ratio of the two totals. `applicable` is false for lenders, whose operating cash flow is
     deposit and loan movement rather than a quality signal.
   - `ratio_history` — five years of ROCE (ROE for lenders), debtor days, inventory days and the
     working-capital cycle, with `roce_fading` and `debtor_days_stretching`.
   - `growth_ranges` — 10/5/3-year compounded sales, profit and price CAGR, and ROE by period,
     plus `roe_vs_trend` and `earnings_above_trend` / `earnings_below_trend`.
   - `shareholding` — eight quarters of promoter, FII, DII and public holding, with
     `*_change_pp` over that window and the window itself.
   - `concalls` — the last three earnings calls with dated transcript and PPT links.
   - `nse` — `pledge` (share of promoter holding pledged, and as of when), `insider` (promoter and
     insider buying and selling by value over the last year) and `sast` (large-stake filings).
   - `market_risk` — `beta` against the Nifty with the `r2` that says how much of the move the
     index explains, and `technicals.max_drawdown_1y_pct` alongside it.
   - `weight_pct`, `sector_name`, `sector_weight_pct`, `sector_peers`

### 3b. Validate the data before reasoning from it

A confident conclusion built on a bad input is worse than no conclusion. Do these first.

1. **Stale financials.** If `results_stale` is true, the script already tried both consolidated
   and standalone pages. Treat the gap as a *data-source* problem until proven otherwise: find the
   company's latest filed result (NSE/BSE, the company's investor page) and use that. Never draw a
   conclusion about the business from the gap itself.
2. **Fiscal year.** Read `fiscal_year_end`. Name quarters by their end month ("the Jun 2026
   quarter"). Use FY labels only when they match that company's year end: many MNC subsidiaries
   (Sanofi India among them) close in December, and "FY to March" does not exist for them.
3. **Price.** Quote screener's price with its fetch date. If `price_vs_csv_pct` is beyond ±2%,
   give the CSV's LTP and `csv_date` alongside it, so the reader can see why the P&L differs from
   their broker. Never take a price or 52-week range from a web aggregator: they lag and disagree.
   If `week52_check.agrees` is false, say so and use the chart's closing range instead.
4. **Distorted multi-year figures.** If a demerger, scheme of arrangement, merger or major
   divestment falls inside a multi-year window, label the figure not comparable and do not use it
   as evidence. Screener's auto-generated cons ("poor sales growth of X% over five years") inherit
   this blindly. The same applies to a one-off quarter (a scheme gain, an exceptional item) inflating
   ROE or deflating P/E. Use the like-for-like quarterly series instead.
5. **One-offs in the two quarters you compare.** Read `one_offs`. If `latest.flag`, quote
   `pe_runrate_ex_one_off` (or the company's pre-exceptional PAT), not `pe_runrate`. If
   `year_ago.flag`, the reported YoY is not comparable; `profit_yoy_ex_one_off_pct` is a pointer,
   and the company's own like-for-like figure is the answer. When you strip a one-off yourself,
   compute both years on the **same basis** and cross-check against standalone. Hero's
   consolidated-minus-gain gave +44%, but standalone was +29%, because the consolidated figure also
   carried swings in associates. The flag misses exceptionals below ~15% of PBT (ITC's Jun 2026
   quarter), so always check the result's exceptional-items line.
6. **Absence of evidence in the NSE block.** `nse.insider.stale` means the endpoint's newest
   filing for that company is old, and `available: false` means the call failed. Neither is
   evidence that insiders have not been selling — coverage is genuinely patchy (current for
   BAJFINANCE and INFY in Sep 2026, nothing after 2022 for TCS, nothing at all for PAYTM). Write
   "no insider dealing on file" only with the date of the newest filing beside it, and otherwise
   write that the data is unavailable. The same applies to `pledge`: no disclosure on file is not
   proof of no pledge.
7. **Policy and tax base effects**, which the script cannot see. Before calling growth
   operational, ask what changed between the year-ago quarter and this one: a GST or tax change, a
   price control, or an exclusivity window opening or closing. The Sep 2025 GST cut on small cars
   and two-wheelers inflates auto volumes YoY until Oct 2026. The Feb 2026 cigarette tax resets
   ITC's base until Feb 2027. Name the month the base laps.

### 3c. Search the web for what the numbers cannot tell you

- **Consensus.** For every target you quote, record the house, the rating, the date and the close it
  was written against. A target is **stale** if it predates the latest result, or its reference
  close is more than ~15% from today's price. Report how many of the targets you found are
  post-result ("3 of 8 post-result"). If none are current, write consensus unavailable rather than
  quoting it. The rules below exist because a target list has been wrong twice:
  - **A search answer is not a source.** WebSearch's prose is a summary written by another model,
    and it invents targets. On 11 Sep 2026 it produced a "Kotak Buy ₹6,720" for Hero when Kotak's
    actual call was a Sell at ₹5,000. It also relabelled Motilal's target as ICICI Direct's. A
    target counts only if you have seen it on a fetched page, or in a result title, that names the
    house, rating, target and date. Keep the URL for each one in your working.
  - **Search for the bears by name**, e.g. `<company> sell OR underweight OR reduce target`.
    Post-result roundups lean bullish, so the bear call is the one that gets dropped.
  - **Check the year.** Results mix "Q1 FY26" and "Q1 FY27" reports under the same quarter name.
    HUL's Goldman, UBS and Nuvama targets from 2025 surfaced as current. An undated target is
    unusable.
  - **Reference close:** `python3 ${CLAUDE_SKILL_DIR}/scripts/close_on.py TICKER YYYY-MM-DD`
    prints the close on the report date and flags anything beyond 15%. Never use an aggregator's "price at report" column:
    Trendlyne's shows today's price on every row.
  - **Sources:** Trendlyne's research-reports page is dated but lags by weeks (in Sep it had no Aug
    reports for Hero). TradingView's Moneycontrol mirror ("Buy X; target of Rs N: Broker") and
    StreetInsider (foreign-house target changes) fetch reliably. Business Standard and Zee Business
    block fetches (403/402), so use their search snippets to find a call, then confirm it
    elsewhere.
  - **Broad "consensus" aggregators (S&P/stockanalysis.com, Trendlyne's own blended line, Univest,
    Alpha Spread) are not a cross-check baseline.** Two pulls of the same aggregator on the same
    day for the same stock have disagreed by 5–10% (SBIN read ₹1,205 avg / ₹1,312 high from one
    pull and ₹1,263 avg / ₹1,390 high from another, both on 18 Sep 2026). If your named/dated
    average disagrees with an aggregator's headline number, that is not by itself evidence of an
    error — check whether the aggregator itself is stable before revising a target down to match
    it. The named, dated, post-result average is the deliberately narrower and more defensible
    number; don't let a noisier, wider one overrule it without a real reason (a target you missed,
    one that's actually stale, or a math error in your own average).
  - **If no named, dated brokerage target exists**, say so precisely rather than "no analyst
    coverage": name that an unattributed aggregator figure may exist and was excluded per the rule
    above, so the reader knows the gap is a sourcing choice, not a blank screen. SWARAJENG (17 Sep
    2026) had a real ₹4,571 aggregator consensus that was correctly excluded but then described to
    the user as "no analyst coverage," which overstated the gap.
- **The latest result**, and the quality of its growth (see 3d).
- **Management guidance** from the latest earnings call or investor presentation: what was guided,
  and when it was said. Guidance may be missed, but it must be recorded so the next note can score
  it. If the prior note recorded guidance, check whether it was met.
  - **Take it from the transcript, not from a summary of one.** The snapshot's `concalls` block
    has the dated transcript and PPT links from the company's own filing. Read the latest one:

    ```
    curl -sL -A "Mozilla/5.0" -o /tmp/<TICKER>-concall.pdf "<transcript url>"
    pdftotext /tmp/<TICKER>-concall.pdf - | grep -inE "guidance|guide|outlook|expect|margin|capex|target" | head -40
    ```

    Then read the pages around the hits for the sentences themselves, and quote the speaker and
    the call's month. A concall transcript is a primary source in a way a news roundup is not —
    this is the same rule as the consensus targets in the bullet above, applied to guidance.
  - If the block is empty, or only a PPT is listed (ITC in Sep 2026), say guidance came from the
    presentation or from press coverage, and name which.
- **Latest net debt**, where `leverage.applicable` is true and `trend` is not `low`. The snapshot's
  figure is gross, excludes cash, and comes from the last annual or half-year balance sheet, so the
  quarter's investor presentation is usually the better source. Date whichever you use.
- **Corporate actions, capacity changes, management changes, regulatory news.** Search
  `<company> news <month> <year>` alongside the concall and target searches above, not as an
  afterthought — a chairman exit, a raid or SEBI order, a plant shutdown or a licence issue rarely
  shows up in screener's ratios until the next quarter, but it is exactly the kind of thing that
  makes a rating stale between reviews.
  - **Date a corporate action (OFS, buyback, block deal) from news coverage, not from the NSE
    `sast` filing date alone.** The filing date can lag the actual event by a week or more —
    LICI's `sast` block dated the government's OFS to 13 Aug 2026, but the OFS itself opened
    4 Aug 2026 at a ₹382 floor. A week's difference changes how "recent" the overhang reads and
    whether other price action in between is being correctly attributed to it. Search
    `<company> OFS/buyback <month> <year>` to confirm the actual date, and note if it was
    oversubscribed — that's a materially different read on whether the overhang has cleared than
    the bare fact that a sale happened.
- **Auditor and governance red flags.** Search `<company> auditor resignation OR qualified opinion
  OR SEBI order OR forensic`. An auditor resigning mid-year, a qualified or adverse audit opinion,
  or an active SEBI/MCA order is a stronger and more specific red flag than anything the ratios can
  show, and it is missed entirely by a review that only reads screener's numbers. Absence of a hit
  is not the same as a clean record — say you searched and found nothing, dated, the same rule 3b.6
  already applies to pledge and insider data.
- **Government or PSU ownership, where the promoter is the state.** `shareholding`'s promoter figure
  already shows this; read what it implies rather than treating a PSU like any other promoter-held
  stock. Note the specific policy exposure by name (a disinvestment overhang, a subsidy or
  price-control dependency, a directive the company doesn't control commercially) rather than a
  generic "government-linked, so lower risk" or "government-linked, so higher risk" — either
  direction stated without the specific mechanism is a guess dressed as analysis.
- **Value migration, for a holding you already own, not only when sourcing a new one.**
  `new-ideas.md` already uses secular themes (ICE to EV, renewables, AI-linked capex, the
  public-to-private shift in defence/space/energy) as a sourcing hint for new candidates — ask the
  same question of an existing holding: is value moving toward this business's segment, or away
  from it toward a substitute or an adjacent business model further up or down the chain? A
  company can look statistically fine on every ratio above while sitting in a segment the market is
  structurally de-rating — that is a forward-looking, qualitative read, not something the ratios
  will show until the migration has already shown up in falling growth.

Prefer recent Indian market sources. If coverage is thin, which is common for smallcaps, say so
rather than inventing a consensus.

### 3d. Decide a rating

BUY, HOLD or SELL / trim. Weigh the factors below by holistic judgment, not a formula — but three
of them are named explicitly as carrying more weight than the rest, and one is named as
subordinate, so when two factors disagree these are not equal votes:
- **Price against the consensus target** is called out below as the single strongest argument for
  trimming.
- **Who is buying and selling the stock** — specifically promoters cutting a stake — is called out
  below as the strongest single bear signal in the ownership data.
- **The peak-earnings check** (part of the signal-row re-check below) must run before, and can
  override, the growth-vs-price-paid read further down — a favourable PEG built on earnings the
  business is losing is not a real signal, so that check does not get to run as if the peak-earnings
  question were still open.
- **Technicals are explicitly subordinate to all of the above**: they decide the re-look price,
  never the rating itself.

Everything else below is weighed together, not ranked against each other by a fixed order:

- **The signal row**, checking it yourself when confidence is `low` or the row is printed with `?`.
  Also check it when confidence is `high`, if trailing earnings contain something that is
  leaving: an exclusivity window or limited-competition product, a commodity peak, or a one-off.
  The row is then built on earnings the business no longer has. Re-place it on guided forward
  earnings and override the confidence. Natco and Lupin both read as high-confidence row 1 at
  ~12–16x trailing, and are ~20–23x on guidance as US exclusivities end.
- **Price against the consensus target**, using current targets only. A price above the average
  target is the single strongest argument for trimming, and was what drove the APOLLOPIPE call.
- **Quality of growth.** Separate what is operational from what is not: constant currency against
  reported, volume against realisation, mix (segment, channel, OE against replacement), other
  income, forex, inventory gains and one-offs. Say which drove the quarter. Mix shift toward a
  lower-margin channel does not reverse when input costs fall. When volume holds up after a tax or
  cost shock, check the segment margin before calling it resilience: volume can be bought with
  margin. ITC's cigarette volume fell only 5% because ITC absorbed tax, and cigarette EBIT fell 31%.
- **The balance sheet.** Leverage and its direction. Rising debt during a margin squeeze is how a
  cyclical problem becomes a structural one.
- **Related-party transactions**, gated to when it's worth the cost — every BUY/SELL (3g already
  scopes deep verification to these), any ticker with a pledge or promoter-selling flag already
  fired, or a small/thin-coverage name where less else is checking the promoter. Skip it for an
  ordinary HOLD in a broad sweep and say so, rather than pulling an annual report for every ticker.
  When you do run it: from the latest annual report or Secretarial Compliance Report's notes to
  accounts — the snapshot carries neither, and this is easy to skip for lack of a concrete method,
  so use one: fetch the annual report PDF from the company's investor page or BSE/NSE filings, then
  `pdftotext -layout <file>.pdf -` (the `-layout` flag matters — plain `pdftotext` on
  a multi-column financial table silently scrambles which number belongs to which line, and
  misattributed a dividend-to-parent line as a fee payment on one run, with no error to catch it),
  then read the RPT schedule itself. **Don't grep for the section title alone** — "related party"
  and "contingent liabilities" recur as running headers and TOC/cross-reference entries dozens of
  times before the note with actual numbers in a large annual report, so `grep -inA5 "related
  party"` lands on a heading, not the transaction table. Grep for a distinctive line-item label
  instead ("Purchase of Goods", "Guarantees", "Dividend received", "Sale of Goods") to land on the
  disclosure with figures. Loans, guarantees or sales to promoter-linked entities off market terms,
  or transactions made without required Audit Committee approval, are red flags on their own,
  orthogonal to the pledge and insider checks above; size any RPT you find against net worth before
  calling it material — a small one that was later ratified is a line, not a rating driver.
  **Contingent liabilities need sector-aware reading, not a blanket check.** `pros_cons.cons`
  sometimes already carries screener's auto-flagged figure — for a bank or NBFC this is off-balance-
  sheet notional (guarantees, forward contracts, derivatives) that is structurally large for that
  sector and not comparable to the same line for a non-financial company; don't flag it as a red
  flag by its size alone without checking the notes-to-accounts breakup for anything unusual inside
  it.
- **Growth against the price paid — but only after the peak-earnings check above, not instead of
  it.** Read `growth_ranges`' 3/5-year profit CAGR alongside the P/E as a rough GARP cross-check
  (P/E at or below the CAGR is priced fairly for its growth). This CAGR is backward-looking, so if
  the signal row was just re-placed on guided forward earnings (exclusivity ending, commodity peak,
  one-off), do the same here: a favourable backward PEG built on earnings the business is losing is
  not a "cheap growth" signal, it's the peak-earnings case wearing a growth costume. Natco read
  PEG ≈ 0.5 on a +28% five-year CAGR that was entirely the Revlimid exclusivity window, while
  forward guidance implied a profit *decline* — use the guided figure, not the trailing CAGR, once
  3d's exclusivity check has already fired.
- **The 3-year case, for every BUY/SELL — this is the actual question (2-3 year upside, not the next
  12 months) and the arithmetic is deterministic, so let the script do it rather than eyeballing a
  chart:**

  ```
  python3 ${CLAUDE_SKILL_DIR}/scripts/three_year_case.py TICKER \
    --fwd-eps-base N --fwd-eps-bear N --eps-asof YYYY-MM-DD [--div-yield-pct N]
  ```

  It builds the stock's own 5-10yr trailing P/E band from data already fetched (screener's annual
  EPS row against year-end closes, one extra long-history chart fetch), and a Nifty hurdle CAGR
  computed from NIFTYBEES's own realised price history — not a web search, so it can't go stale or
  get misquoted. Source `--fwd-eps-base`/`--fwd-eps-bear` yourself first (guided or dated consensus
  EPS for the base case, a trend/normalised figure for the bear case — the same sourcing discipline
  as a consensus target); the script multiplies each against an exit P/E (the band's median for
  base, its low for bear, by default) to give a CAGR over the actual time to `--eps-asof` (the
  fiscal year-end that forward EPS is FOR — a fixed "3 years" is meaningless without knowing
  whether the EPS you sourced is one year out or four, and the script refuses to run without it once
  you pass `--fwd-eps-base`), and states plainly whether it clears the Nifty hurdle. A stock whose
  base case doesn't beat the index-fund hurdle by a real margin has a weak case for new money
  regardless of how the signal row reads. Run it without `--fwd-eps-*` to get the band alone —
  useful on its own for the peak-SELL read below.
  **A short horizon (common — dated forward multiples rarely reach past the next fiscal year)
  inflates the annualised base/bear gap.** The script flags this itself when the horizon comes out
  under 2 years and prints the un-annualised total price move alongside the CAGR; quote that total
  move in the note, not just the CAGR, so a modest EPS spread doesn't read as a near-binary outcome
  (ITC's FY28E-based case: a ±19pp total-return spread became a ±20pp/yr *annualised* one on a
  1.7-year horizon).
  **A dated, named EPS estimate is rarer than a price target — don't block on one.** If nothing
  turns up (common: analysts publish price targets far more often than explicit EPS numbers),
  extrapolate from TTM EPS at management's own guided growth rate (credit growth, volume guidance,
  margin corridor — whatever the concall gave) instead. Label it plainly as your own extrapolation
  from guidance, not a consensus figure, in the note — the same distinction 3c already draws between
  a sourced target and an invented one.
- **A SELL "because it's at its peak" needs the same test, not a feeling.** Read the P/E band
  output above: is today's P/E at or above the top of the stock's own historical range (the script's
  percentile line), is `earnings_above_trend` true, and is price already above the consensus
  average? Two of three together is a real peak case; one alone (a high percentile with earnings
  still on trend) is a re-rating, not a peak, and argues for HOLD, not SELL.
- **Reinvestment**, as a qualitative read, not a computed ratio — manufacturing, mining and pharma
  only. Is the company visibly plowing cash into capex while `roce_fading` is true (`leverage.trend`
  rising alongside falling FCF is the tell), or is growth coming from M&A/stake buys a fixed-assets
  ratio can't see anyway (Natco's real reinvestment was the Adcock stake, invisible to that math)?
  Don't compute the ratio by hand — the snapshot has no fixed-assets field, and the number is rarely
  worth the scrape.
- **Whether profit becomes cash.** `cash_flow.cfo_to_pat` below ~0.6 over five years says reported
  profit is not arriving as cash, which is the value-trap tell the ratios miss. Read it with
  `ratio_history.debtor_days`: profit that stays in receivables is the usual reason. Both are
  skipped for lenders, so say so rather than quoting a meaningless number.
- **The direction of returns, not just the level.** `ratio_history.roce` is five years of ROCE.
  A 15% ROCE on the way down from 30% is a different business from a 15% on the way up, and the
  signal row sees only today's figure. `roce_fading` marks the first case.
- **Whether the earnings the P/E rests on are normal.** `growth_ranges.roe_vs_trend` is last
  year's ROE over the five-year figure. Above ~1.4 (`earnings_above_trend`) the trailing P/E is
  resting on profits above the company's own history, so re-place the row on normalised earnings
  as 3d already requires for exclusivity and commodity peaks. This is the mechanical form of the
  Lupin case, at 29% against 10% over ten years. It is not a complete test: Natco read 17%
  against 19% and was still on peak earnings, because its problem was forward, not trailing.
  Below ~0.6 (`earnings_below_trend`) the opposite applies — a high P/E on depressed earnings is
  not automatically expensive.
- **Who is buying and selling the stock.** `shareholding` gives eight quarters of promoter, FII
  and DII holding. Promoters cutting a stake is the strongest single bear signal here; FIIs
  leaving over many quarters is weaker and often flow rather than judgement, so treat a fall as
  context unless it is large. Where the `nse` block is fresh, promoter pledge and insider selling
  belong in the same sentence. Never write that insiders are not selling from an absent or stale
  block (3b.6).
- **Management guidance**, and the track record on the last guidance you recorded.
- **Valuation, honestly framed.** When `pe_runrate_diverges` is true, neither trailing P/E nor the
  annualised quarter is usable alone. Give a low / base / high forward multiple, each with its
  assumption stated. Anchor the base case on management guidance or consensus EPS, not a number you
  picked. Screener's dividend yield is trailing. When earnings are falling, give a forward yield
  from guided EPS times the usual payout (ITC: 5.6% trailing, ~4.5% forward).
  Even when `pe_runrate_diverges` is false (the gap didn't trip the script's threshold), if
  `pe_runrate` is meaningfully higher than trailing P/E because of one soft quarter, lead with the
  run-rate figure in any one-line summary, not just in the note's fine print. APOLLOTYRE's note
  correctly said "size any add with 18.9x in mind, not the headline 12.3x," but a later summary to
  the user quoted only 12.3 — the caveat has to survive compression, not just exist in the note.
- **Portfolio context.** Position weight, sector weight, and whether a same-sector holding already
  does the job better. The comparison for adding to TCS is TCS against COFORGE, not TCS against cash.
  The CSV's sector tags understate some themes: TMCV, ASHOKLEY and SWARAJENG sit under Capital
  Goods but ride the auto cycle, so "Autos 9.2%" was really ~12% auto-linked. Quote both figures
  when they differ, and frame a BUY in an already-heavy theme as a swap, not new money.
- **Position within the 52-week range.**
- **The `technicals` block**, as a **secondary** input. Fundamentals decide the rating;
  technicals decide the re-look price. A row-1 name well below its 200 DMA with RSI near 30 is the
  "quality on sale" setup worth calling out, while a row-3/4 name below its 200 DMA is confirmation
  of the value trap, not a discount. Never upgrade a rating on an oversold RSI alone. Ignore
  `dma200` where `dma200_reliable` is false.

### 3e. Recommendation hygiene — hard rules

- **No argument may depend on the user's cost basis.** Test each sentence: if it would change or
  vanish with a different average cost, delete it. "Adding lowers my average" and "adding would
  worsen an already-good position" both fail. The purchase price is sunk. The only legitimate use
  is tax (the long-term holding period — more than 12 months, not 12 months to the day —
  harvesting a loss, or booking a tax-free gain), and it must be labelled as tax.
- **A SELL or trim names which lots, using the script rather than eyeballing purchase dates:**

  ```
  python3 ${CLAUDE_SKILL_DIR}/scripts/tax_lots.py TICKER
  ```

  It reads today's snapshot's per-lot data and prints each lot's LT/ST status, days held, unrealized
  gain, and flags any short-term lot within ~60 days of turning long-term (20% → 12.5%, and
  exemption-eligible) — a real choice between selling now and waiting worth naming explicitly, not
  leaving implicit. A lot with no numeric cost (a demerger, an unreconciled corporate action) falls
  back to the position's own average cost, labelled as an estimate, rather than being dropped from
  every total — TMCV's 25 demerger-cost shares out of 29 were silently excluded from its gain
  entirely before this fallback existed, on exactly the position most likely to get a trim call.
  For the portfolio-wide view — realised gains this FY, LTCG exemption headroom, and which lots
  across every holding are the best gain-booking or loss-harvesting candidates — run
  `python3 ${CLAUDE_SKILL_DIR}/scripts/tax_lots.py --harvest` instead. It reads the Console export's
  own "Tax position" section (present only in a lot-level `.md` export, not a plain CSV) for this
  FY's realised STCG/LTCG and Console's own loss-harvesting estimate, so it isn't guessing at
  exemption headroom the way a single-ticker run has to. Realised gains are usually small early in
  the FY, which means loss-harvesting has little current-year value (it mostly creates a carry-
  forward) — the bigger lever is usually the unused LTCG exemption itself: booking LT gains up to
  that headroom before FY-end is tax-free, and `--harvest` names the lots that do it.
- **The rating and the Action must agree.** BUY means buying at today's price is right. If the
  level you would add at is more than ~5% below the current price, either rate it HOLD with "add at
  ₹X", or keep BUY and state the split: how much now, how much at the level.
- **Materiality.** If the position is under ~0.5% of the book, the Action must say whether to build
  it toward a named target weight or leave it as it is. A one-share add to a 0.2% position is not a
  recommendation. Zerodha delivery has no brokerage, so this is about the position mattering, not
  cost.
- **Say exactly what the number says.** Write "debt-free" only when borrowings are nil; otherwise
  write "effectively debt-free (₹779 Cr, D/E 0.04)". Label trailing figures as trailing. Never put
  a percentage in a note that you computed across two different bases.


### 3f. Write the note

Read `${CLAUDE_SKILL_DIR}/note-template.md` before writing or rewriting `stocks/<TICKER>.md`, and follow it exactly: the field set, the one-line fields, the `(prev ...)` history, the **UPGRADED/DOWNGRADED** marker, **Correction:** lines, and the disclaimer footer. `PORTFOLIO.md` flags any note that drifts from it.

### 3g. Verify every BUY and SELL before you summarise

The user acts on ratings that change a position, and so far every error the user caught came
from one of those. A HOLD can wait for the next review; a BUY or SELL gets this second pass first:

1. **Re-find each consensus target** from its source. Drop any you can't find, recompute the
   average, and recount post-result targets. Confirm any Sell/Underweight call you found is in the
   average.
2. **Recompute every percentage** in the note from the underlying numbers, with the same basis on
   both sides.
3. **Test the deciding sentence**, the one that says why it is BUY rather than HOLD (or SELL
   rather than HOLD), against its driver. Is that driver operational, or a base effect, a one-off
   or an exclusivity? Maruti's BUY rested on +29% volume that turned out to be mostly the GST cut.
4. **Explain any 10%+ move since the result.** Search the news after the result date: a chairman
   exit, monthly sales, an export drop. It always has a reason worth a line.
5. **Date every ownership, pledge and insider claim**, and check each came from the snapshot
   rather than from memory. A sentence about promoters or insiders with no date attached, or one
   drawn from a block marked stale or unavailable, comes out of the note.

If a check fails, fix the note, and the rating if its argument no longer holds, before writing the
summary. Say in the summary that the pass ran, and what it changed.

**Then record the rating to the ledger**, for every note you wrote or rewrote in this step,
whether or not it changed:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/rating_ledger.py record TICKER RATING PRICE "deciding sentence"
```

`RATING` is `BUY`, `HOLD` or `SELL` (a trim is `SELL`). `PRICE` is the note's own snapshot price,
not a web price. The deciding sentence is the same one 3g.3 just tested — the reason this is BUY
rather than HOLD, or SELL rather than HOLD — quoted, so a later `report` run can read back exactly
what would have to hold up for the call to still be right. This is the only way the skill's own
record survives past the next rewrite: the note template's `(prev ...)` field keeps only one hop of
history, so without this step there is no way to score a rating once two more rewrites have passed
over it.

## Step 4 — re-run and summarise

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_fundamentals.py` (no arguments, no `--refresh`)
once more so
`PORTFOLIO.md` picks up the new ratings from the `stocks/<TICKER>.md` files you just wrote. Every
ticker is already cached from Step 1, so this is a sub-second rebuild with no network calls — run
the full form here even when Step 1 was scoped, so the whole table is rebuilt.

**Lead with a scorecard, one per researched ticker, before any prose.** This is the chat-facing
summary's required opening, not optional formatting — the detailed reasoning (what changed, the
rotation discussion, everything else below) comes after it, not instead of it:

```
TICKER — Rating: BUY/HOLD/SELL  |  Row N (row's plain-English description)
As of: <data fetch date/time> | Purchase (if one happened this run): <date/time, or "not logged" if not given>
P/E N<x> (run-rate N<x> if it diverges), ROE N%, ROCE N%
Consensus <rating>, avg TP ₹N = N% <upside|downside> (<date>, <M> of <N> post-result — or "unavailable" per 3c)
3-Year case: base N% vs bear N% vs Nifty hurdle N%/yr — <clears|doesn't clear>    [BUY/SELL only, from three_year_case.py]
Action: <what was done or should be done, per 3e>
Next check-in: <date/time, if a calendar reminder exists or was just set>
```

Never fabricate a timestamp: if the user didn't give an exact purchase time, write "not logged"
rather than guessing, and offer to correct the line if they supply it. Omit the 3-Year case line
entirely for a HOLD, the same conditional rule note-template.md already uses.

After the scorecard(s), give the user the fuller summary: what changed versus the previous note
(corrections first), and any rotation worth considering: where to trim and where that money could
go, given the rest of the book and its sector weights. Keep it to a few sentences per stock.

**When multiple BUYs share a sector or theme, say so in the summary, not just in each note.** Each
note's own Portfolio context line can carry a concentration caveat, but if the summary lists them
as parallel, independent picks, the reader loses that they're two adds to the same bet. On 17 Sep
2026 SBIN and ICICIBANK (both Financial Services, already 24.3% of the book) and APOLLOTYRE and
SWARAJENG (both auto-linked, ~12% of the book) were presented as four separate BUYs with no mention
that they paired up — state the shared exposure explicitly when it's there.

**Offer the calendar candidates for any ticker researched this run:**

```
python3 ${CLAUDE_SKILL_DIR}/scripts/calendar_notes.py TICKER ...
```

This writes `data/skill-data/calendar.md` with each ticker's estimated next-results window and its
technical re-look levels (200/50 DMA, 60-day low) — a deterministic date/price computation, not a
forecast. If a calendar connector is available in this session, offer to turn the rows into actual
events; otherwise point the user at the file so they (or another Claude session with a calendar
tool) can do it. Never treat the results window as a confirmed date — it is a reporting-lag
estimate, and the note itself already says so.

**On a portfolio-wide sweep, or when the user asks how past calls have done, score the ledger:**

```
python3 ${CLAUDE_SKILL_DIR}/scripts/rating_ledger.py report
```

This is a fact report only — the recorded price, today's price, the realised return and the
deciding sentence recorded at the time, per rating. Reading whether that sentence actually held up
is your job, the same judgment call as everything else in 3d: pull the news and the results since
that date for anything the report flags as a large move or a long-held rating, and say plainly
whether the original thesis was right, wrong, or still open. Where it was wrong, name what you'd
change about how similar calls get made — that is the point of keeping the ledger at all, not just
a scoreboard. The ledger only starts counting from the first `record` call onward, so a first run
may show little or nothing; say that rather than treating an empty ledger as a clean track record.

Close with: *Not investment advice — verify prices and figures before acting.*
