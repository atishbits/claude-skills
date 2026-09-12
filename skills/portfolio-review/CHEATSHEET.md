# Financial Metrics Cheat Sheet

Quick reference for the three ratios that come up most when judging whether a stock is cheap or expensive and whether the business is actually good.

---

## P/E Ratio (Price-to-Earnings)

**What it is:** How much you pay for every ₹1 of the company's annual profit.

**Formula:** `Share Price ÷ Earnings Per Share (EPS)`

**How to read it:**
- A P/E of 44 means investors are paying ₹44 for every ₹1 the company earns per year.
- High P/E = the market expects strong future growth (or the stock is expensive).
- Low P/E = cheaper, or the market expects trouble ahead.
- Only compare P/E within the same sector. A specialty-chemicals P/E means nothing next to a bank's.

**Rule of thumb:** A high P/E is only justified if earnings are actually growing fast. A P/E of 44 with flat or falling profits is a warning sign.

---

## ROCE (Return on Capital Employed)

**What it is:** How efficiently the company turns ALL its capital (equity + debt) into operating profit.

**Formula:** `EBIT ÷ Capital Employed` where Capital Employed = Total Assets − Current Liabilities

**How to read it:**
- Measures the return the business generates on every rupee of capital put to work, regardless of how it was funded.
- Higher is better. Broadly: below ~10% is weak, 15–20%+ is strong.
- Because it includes debt, ROCE shows whether the core business is genuinely productive, not just leverage flattering the numbers.

**Rule of thumb:** Compare ROCE against the company's cost of borrowing. If ROCE is below what the company pays on its debt, it's destroying value.

---

## ROE (Return on Equity)

**What it is:** How much profit the company generates on the shareholders' money specifically.

**Formula:** `Net Profit ÷ Shareholders' Equity`

**How to read it:**
- This is the return on YOUR slice as an equity owner.
- Higher is better. Broadly: below ~10% is weak, 15–20%+ is strong.
- Watch out: ROE can be pumped up artificially by taking on lots of debt (smaller equity base). That's why you check it alongside ROCE.

**Rule of thumb:** High ROE + high debt can be a mirage. High ROE + low debt + high ROCE is the real quality signal.

---

## Putting them together

| Row | Signal | What it suggests |
|:--:|---|---|
| 1 | Low P/E + high ROE/ROCE | Potentially undervalued quality business — worth a look |
| 2 | High P/E + high ROE/ROCE | Great business, but priced richly — growth must continue |
| 3 | High P/E + low ROE/ROCE | Expensive with weak fundamentals — caution |
| 4 | Low P/E + low ROE/ROCE | Cheap for a reason — possible value trap |

**Worked example (Aarti Industries, as of 23 Jul 2026):**
P/E ~44, ROCE ~6.85%, ROE ~7.13%. That's a rich valuation sitting on top of weak returns, i.e. the market is paying up for an expected earnings recovery that hasn't shown up yet. Justified only if profits rebound.

---

## How the script applies this

`scripts/fetch_fundamentals.py` assigns the row mechanically, with two adjustments that matter:

- **P/E is judged against the stock's sector, not an absolute number.** Screener's sector tag picks
  the band — a bank is "cheap" below ~12 and "rich" above ~25, while an FMCG name is only "cheap"
  below ~35. Falling back to an absolute 18/30 band marks the result low-confidence.
- **ROCE is ignored for lenders.** For banks, NBFCs and insurers, ROCE is structurally low as an
  artefact of the business model — HDFC Bank's ~7% is not weakness. Those are judged on ROE alone.

A row printed with a trailing `?` in `PORTFOLIO.md` means a ratio sat near a threshold and the row
could flip either way. Treat those as provisional and check them by hand.

**One-off flags.** Screener books exceptional gains inside Other Income, so the script compares
each quarter's other income with the company's own norm. A flagged latest quarter flatters the
run-rate P/E. A flagged year-ago quarter makes YoY growth not comparable. Hero's Jun 2025 Ather
gain made a +24–29% year look like −17%. "Other income N% of PBT" means the profit is mostly
treasury income, not operations. Lenders are skipped, because their Other Income is fee income.

A blank P/E means the company is **loss-making**, not that it is cheap. Those land in row 3: with no
earnings, no price is justified by earnings.

---

## The technical layer

The four rows above decide **whether a business is worth owning**. Technicals only inform **where to
re-look on price** — they never change a rating on their own. `fetch_fundamentals.py` pulls these
from screener's own chart series (the one that draws the DMA overlays) and stores them under
`technicals` in the snapshot.

| Reading | What it is | How to use it |
|---|---|---|
| **200 DMA** | 200-day average price — the long-term trend line | Price below it means the market has been de-rating the name for months. On a row-1 business that's the "quality on sale" setup; on a row-3/4 it's confirmation of the fundamental problem. |
| **50 DMA** | 50-day average — the medium-term trend | 50 above 200 = uptrend, 50 below 200 = downtrend. |
| **RSI (14)** | Momentum, 0-100 | Below 30 = oversold (selling may be exhausted), above 70 = overbought (stretched). Mid-range says nothing — don't force a story onto it. |
| **3m / 6m return** | Price momentum | Separates "fell and stayed down" from "still falling". |
| **60-day high/low** | Recent trading range | The nearest real support/resistance, better than the 52-week levels for naming a re-look price. |
| **Volume 20d vs avg** | Recent volume against the year's average | Above ~1.5 means the move is being made on conviction, not drift. |
| **Delivery %** | Share of traded volume actually delivered | High delivery on a fall = real selling by holders, not intraday noise. |

**The one combination worth acting on:** a row-1 business trading meaningfully below its 200 DMA with
RSI near or below 30. That is a quality company the market is currently unhappy with — which is
exactly what averaging down is for. `PORTFOLIO.md` flags this under "Worth a look".

**The trap it guards against:** a row-3 or row-4 name that is *also* below its 200 DMA is not on
sale, it is being repriced. Cheap-and-falling is the value trap; technicals confirm the fundamental
verdict rather than overriding it.

**Caveat on recently listed stocks.** Screener ramps the DMA from the first bar it has, so a stock
that listed inside the last year (a demerger, an IPO) shows a "200 DMA" built on far less data. The
script sets `dma200_reliable: false` in those cases and `PORTFOLIO.md` shows the 50 DMA with a `*`
instead.

---

## The evidence layer

The four rows use today's P/E, ROE and ROCE. These readings say whether those numbers are *real*
and whether they are *normal*, which is most of the value-trap question. They come from sections of
the same screener page the script already downloads, plus three NSE endpoints.

| Reading | Where from | What it tells you |
|---|---|---|
| **CFO / PAT** over 5 years | Cash flow statement | Whether reported profit arrives as cash. Below ~0.6 the profit is sitting somewhere else — usually receivables or inventory. Not computed for lenders, whose operating cash flow is deposit and loan movement. |
| **Years of negative CFO** | Cash flow statement | A business funding itself from investors rather than customers. Swiggy: five of five. |
| **ROCE by year** | Ratios section | Direction, not level. 15% falling from 30% and 15% rising from 8% are different businesses with the same row. |
| **Debtor days** | Ratios section | Rising receivables are how revenue keeps growing after the cash stops. |
| **ROE last year vs 5/10-year** | Growth ranges | Whether the earnings under the P/E are normal for this company. Above ~1.4x, the trailing P/E is resting on profits the business does not usually make. Lupin: 29% last year against 10% over ten years. |
| **Promoter / FII / DII holding** | Shareholding pattern, 8 quarters | Promoters cutting a stake is the strongest bear signal here. Institutional flows are weaker evidence — often allocation, not judgement. |
| **Promoter pledge** | NSE | Promoter-pledged shares as a share of what promoters hold — a forced-selling risk no ratio shows. Ashok Leyland: 39% as of 30 Jun 2026. Read the promoter figure, not the company-wide "shares pledged" one, which counts public shareholders' pledges too (Whirlpool: 2.3% encumbered, promoters nil). |
| **Insider dealing** | NSE | Promoter and insider buying or selling by value over the last year. |
| **Concall transcript links** | Documents section | The primary source for guidance, dated, straight from the company's filing. |

**The one rule that matters here:** absence is not evidence. NSE's coverage is patchy — as of Sep
2026 it was current for Bajaj Finance and Infosys, had nothing after 2022 for TCS and nothing at
all for Paytm. A missing pledge or insider record means *unknown*, never *none*. The script marks
those blocks `stale` or `available: false` and the notes must repeat the distinction.

**What it does not do:** none of this replaces reading the result. The flags point at the quarter
to check, they do not conclude anything on their own.

## Risk and concentration

`PORTFOLIO.md` closes with a book-level section. The benchmark is NIFTYBEES, the Nifty 50 ETF,
fetched through the same chart API as every holding.

- **Beta** — how much the book moves with the index, weighted by position size. Each holding also
  carries its own beta and an `r2`, which says how much of that stock's move the index explains at
  all. A beta from a stock with low r2 is a number without a meaning.
- **1-year return vs the index** — today's weights applied to each holding's own 1-year price
  move. It is *not* your actual return: it ignores when you bought and what you have added since.
- **Effective positions** — `1 / Σ(weight²)`. 73 holdings with 10% in one name are not 73 bets.
  This is the honest answer to "am I over-diversified".
- **The sub-0.5% tail** — how many positions are too small for anything you do to them to matter.

Portfolio-level volatility and drawdown are deliberately absent: they need every holding's daily
series at once, and a subset run only refreshes some of them. A half-computed risk number is worse
than none.

---

*Not financial advice. These ratios are inputs, not verdicts — always read them alongside debt levels, cash flow, and the sector cycle.*
