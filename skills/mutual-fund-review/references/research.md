# What the research says (distilled, October 2026)

The skill's defaults come from here, not from the user's instincts. Read it when a verdict needs a
reason, and cite the source. Claims marked [UNVERIFIED] could not be confirmed against a primary
source when this was written.

## Where the experts agree

1. Asset allocation and behaviour dominate returns; timing on news usually costs money.
2. Costs compound against you. Low fees are the most reliable predictor of future returns
   (Morningstar: the cheapest fifth of US equity funds had a 62% chance of surviving and beating
   their category, the dearest fifth 20%).
3. Stay invested for long horizons; use few funds (about 5–6 equity funds at most).
4. Avoid new fund offers and chasing recent winners: top-quartile funds rarely stay there.
5. Rebalance to targets, preferably by directing new money rather than selling.

## Active vs index, in India (SPIVA India, year-end 2025)

Share of active funds that trailed their benchmark:

| Category | 1 yr | 3 yr | 5 yr | 10 yr |
|---|---|---|---|---|
| Large cap | 75% | 74% | 84% | 76% |
| ELSS | 69% | 55% | 59% | 83% |
| Mid/small cap | 12% | 42% | 46% | 79% |

Default from this: **index funds for large cap; mid and small cap judged fund by fund** on rolling
returns against their own index. An active fund keeps its place only if it beat its index in at
least `keep_min_window_win_pct` (65%) of rolling 3-year windows by a positive median margin. The
comparison is against an index fund's NAV, so both sides are already after their fees: a positive
margin means the higher fee was earned.

## Allocation

- Core-satellite: a core of 70–85% in broad low-cost funds; satellites (mid/small, sector, factor,
  international) capped, sector themes at 10–15% in total.
- Gold 5–15% as a diversifier [UNVERIFIED range]; no new sovereign gold bonds since Feb 2024, so an
  ETF or fund of funds.
- International funds are often closed to new money while the industry's US$7 bn overseas cap
  binds; expect that.
- Debt after April 2023 is taxed at slab; for a high-slab investor an **arbitrage fund** (taxed as
  equity) is the low-risk alternative to compare with an FD. Direct bonds can fill the debt role.
- Count direct stocks and bonds in the split, or an all-equity fund list looks riskier or safer
  than the household really is.
- Rebalancing bands (Swedroe 5/25): act when a sleeve drifts more than 5 points or 25% of its
  target, whichever is smaller.

## When to exit or switch, and when not

Review a fund when it trails its index over most rolling 3- and 5-year windows (not one bad year),
costs clearly more than an index alternative, changes mandate or manager, duplicates another fund
(over 50% overlap), or breaks an allocation band. Do not switch for short-term lag, while an exit
load applies, while ELSS units are locked, or when the tax bill dwarfs the saving. Prefer stopping
new money into a laggard to selling it.

Switch break-even: n = ln(V/(V−C)) / ln((1+r−e_new)/(1+r−e_old)), with C the exit load plus tax.
Tax paid on switching is mostly paid early, not extra, since staying also pays tax at the exit.
Switch in tranches sized to the yearly ₹1.25 lakh long-term exemption.

## Tax (resident individual, FY 2026-27; check after every Budget)

| Fund type | Short term | Long term |
|---|---|---|
| Equity (≥65% Indian equity, incl. arbitrage) | ≤12 months, 20% | >12 months, 12.5% above ₹1.25L a year (one pool with direct stocks) |
| Hybrid 35–65% equity, gold, international FoF | ≤24 months, slab | >24 months, 12.5% |
| Debt bought from 1 Apr 2023 | slab, any holding period | slab |

Pre-2018 equity units are grandfathered at their 31 Jan 2018 value. Surcharge on capital gains is
capped at 15%. A short-term loss sets off short- or long-term gains; a long-term loss only
long-term gains. ELSS gives a deduction only under the old regime.

## Checklist and where each item lives

Plan 1 (this version) covers: CAS and portal ingestion; XIRR; the same cash flows in the benchmark;
rolling and trailing returns against the benchmark; expense ratio, its rupee drag and the gap to an
index fund; switch break-even; exit-load exposure; unrealised short- and long-term gains by tax
class with grandfathering; the after-tax FD hurdle.

Plan 2 adds: allocation against targets incl. stocks, bonds and FDs; 5/25 bands; sleeve split;
fund count; harvesting room using the shared exemption; new money, SIP and lump-sum plans; verdict
ledger.

Plan 3 adds: look-through to company fundamentals; overlap; market-cap and sector split; the
valuation-tilt and lump-sum-vs-staggered backtests.

Judgement throughout: the hold/exit verdict, manager and mandate changes, AMC governance, factor
and international suitability.

## Sources

- SPIVA India Year-End 2025 — https://www.spglobal.com/spdji/en/spiva/article/spiva-india-year-end-2025/
- Morningstar, fees as a predictor of returns — https://global.morningstar.com/en-gb/funds/how-fund-fees-are-the-best-predictor-of-returns
- Swedroe 5/25 rebalancing — https://awealthofcommonsense.com/2014/03/larry-swedroe-525-rebalancing-rule/
- freefincal switch-cost method — https://freefincal.com/switch-cost-calculator-cost-of-switch-from-regular-to-direct-plan/
- freefincal, Budget 2024 MF tax — https://freefincal.com/budget-2024-big-change-in-mutual-fund-taxation-rules
- Value Research on sectoral funds — https://www.valueresearchonline.com/stories/229691/what-to-do-sectoral-new-funds-you-already-own/
- SEBI expense-ratio framework from April 2026 — https://cafemutual.com/news/industry/37012-sebis-new-expense-ratio-framework-here-is-what-changes-after-april-1-2026
- SEBI recategorisation, Feb 2026 — https://taxguru.in/sebi/sebi-overhauls-mutual-fund-categorization-curb-portfolio-overlap.html
- Overseas cap and 2026 suspensions — https://www.businesstoday.in/mutual-funds/story/why-are-mutual-funds-stopping-international-sips-heres-how-sebis-overseas-investment-cap-works-543752-2026-07-18
- Grandfathering — https://taxguru.in/income-tax/grandfathering-provisions-capital-gains.html
- Arbitrage fund taxation — https://www.indmoney.com/blog/mutual-funds/why-arbitrage-funds-are-taxed-like-equity-funds
- AMFI daily NAV file — https://portal.amfiindia.com/spages/NAVAll.txt ; AMFI TER — https://www.amfiindia.com/ter-of-mf-schemes
- NAV history API — https://api.mfapi.in/
