#!/usr/bin/env python3
"""A stock's own historical P/E band, a Nifty long-run hurdle computed from
real price data (not a web search, so it can't go stale or get misquoted),
and -- if you give it forward EPS -- the 3-year base/bear return case. This
exists so the CAGR arithmetic, and the temptation to eyeball a P/E band by
skimming a chart, never happens by hand.

    python3 scripts/three_year_case.py TICKER
        [--fwd-eps-base N] [--fwd-eps-bear N] [--div-yield-pct N]
        [--exit-pe-base N] [--exit-pe-bear N] [--years N]

Forward EPS is not something this script can know: source it yourself
(management guidance or a dated consensus estimate) and pass it in. Without
--fwd-eps-base/--fwd-eps-bear it only prints the P/E band and the Nifty
hurdle -- useful on its own for the peak-SELL read (where today's P/E sits
in the stock's own range).

Reads today's cached screener page for TICKER (run fetch_fundamentals.py, or
--screen, first). Fetches one extra long-history chart for the ticker and,
once per day, for NIFTYBEES -- cached separately from fetch_fundamentals.py's
own daily chart so the two don't collide or overwrite each other.

Years with non-positive EPS are excluded from the band and named, not
silently dropped (a loss year would otherwise divide a negative into the
band and corrupt it)."""
import argparse
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_fundamentals as ff  # noqa: E402
import requests  # noqa: E402

LONG_CHART_YEARS_DEFAULT = 10


def fetch_long_chart(ticker, company_id, session, days):
    """Same idea as fetch_fundamentals.fetch_chart, but a longer window and a
    distinct cache file -- the daily chart cache is only 365 days and is
    reused by technicals/beta, so this must not touch it."""
    cache = os.path.join(ff.CACHE_DIR, f"{ticker}-chart-long-{date.today().isoformat()}.json")
    if os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            pass
    url = (f"https://www.screener.in/api/company/{company_id}/chart/"
           f"?q=Price&days={days}&consolidated=true")
    body = ff.get(url, session)
    time.sleep(ff.REQUEST_DELAY)
    if not body:
        return None
    data = json.loads(body)
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def price_series(chart):
    if not chart:
        return []
    for ds in chart.get("datasets", []):
        if ds.get("metric") == "Price":
            return [(d, float(v)) for d, v in ds["values"]]
    return []


def close_on_or_before(series, target_date):
    prior = [c for c in series if c[0] <= target_date]
    return prior[-1] if prior else None


def pe_band(doc, series, years):
    """Trailing P/E for each of the last `years` fiscal year-ends: that
    year's closing price (nearest trading day on or before the year end)
    divided by that year's EPS. Returns the valid (year, pe) pairs and the
    excluded years with a reason."""
    dates, rows = ff.parse_table(doc, "profit-loss")
    eps_row = rows.get("EPS in Rs")
    if not eps_row or not dates:
        return [], [], None
    fiscal_dates = [d for d in dates if d != "TTM"]
    eps_by_year = dict(zip(fiscal_dates, eps_row))
    window = fiscal_dates[-years:]
    # A near-zero (but positive) EPS year -- a merger write-off, a one-off
    # provision -- divides into a P/E in the hundreds or thousands that would
    # otherwise corrupt the band's low/high. Screen it out relative to the
    # window's own typical earnings, not just against zero: SBIN's FY17 EPS
    # of Rs 0.30 (vs ~Rs 25-90 in surrounding years) produced a 978x "P/E".
    positive_eps = sorted(e for y in window if (e := eps_by_year.get(y)) is not None and e > 0)
    median_eps = positive_eps[len(positive_eps) // 2] if positive_eps else None
    near_zero_floor = 0.1 * median_eps if median_eps else None
    valid, excluded = [], []
    for y in window:
        eps = eps_by_year.get(y)
        if eps is None or eps <= 0:
            excluded.append((y, "no EPS" if eps is None else f"EPS {eps:.2f} <= 0"))
            continue
        if near_zero_floor and eps < near_zero_floor:
            excluded.append((y, f"EPS {eps:.2f} is a near-zero outlier "
                                 f"(< 10% of the window's median {median_eps:.2f})"))
            continue
        close = close_on_or_before(series, y)
        if not close:
            excluded.append((y, "before the chart's history starts"))
            continue
        pe = close[1] / eps
        valid.append((y, round(pe, 2)))
    latest_eps = None
    if "TTM" in dates:
        latest_eps = eps_row[dates.index("TTM")]
    elif fiscal_dates:
        latest_eps = eps_by_year.get(fiscal_dates[-1])
    return valid, excluded, latest_eps


def nifty_hurdle_cagr(session, years):
    chart = fetch_long_chart(ff.BENCHMARK["ticker"], ff.BENCHMARK["company_id"], session,
                              days=years * 365 + 30)
    series = price_series(chart)
    if len(series) < 2:
        return None
    first_date, first_price = series[0]
    last_date, last_price = series[-1]
    span_years = (date.fromisoformat(last_date) - date.fromisoformat(first_date)).days / 365.25
    if span_years < 1:
        return None
    cagr = (last_price / first_price) ** (1 / span_years) - 1
    return {"cagr_pct": round(cagr * 100, 1), "from": first_date, "to": last_date,
            "span_years": round(span_years, 1)}


def percentile_of(value, series):
    if not series:
        return None
    below = sum(1 for _, v in series if v <= value)
    return round(100 * below / len(series))


def median_of(values):
    """Plain median of a non-empty list -- pulled out once since the band and
    the 3-year case both need it and disagreeing implementations would be
    worse than one shared, tested one."""
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def three_year_cagr(current_price, fwd_eps, exit_pe, div_yield_pct=0.0):
    """The arithmetic behind one side (base or bear) of the 3-year case: an
    exit price from forward EPS x an exit multiple, the price CAGR to get
    there in 3 years, and dividends added as a simple annual addition (not
    compounded -- a reasonable approximation at these magnitudes, not a
    reinvestment model). Raises ValueError on a non-positive input rather
    than silently returning nonsense (a zero or negative price/EPS/multiple
    has no defined CAGR)."""
    if current_price <= 0 or fwd_eps <= 0 or exit_pe <= 0:
        raise ValueError("current_price, fwd_eps and exit_pe must all be positive")
    exit_price = fwd_eps * exit_pe
    price_cagr_pct = ((exit_price / current_price) ** (1 / 3) - 1) * 100
    return {
        "exit_price": exit_price,
        "price_cagr_pct": price_cagr_pct,
        "total_cagr_pct": price_cagr_pct + div_yield_pct,
    }


def clears_hurdle(total_cagr_pct, hurdle_cagr_pct):
    """(clears: bool, margin in percentage points)."""
    margin = total_cagr_pct - hurdle_cagr_pct
    return margin > 0, margin


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker")
    p.add_argument("--fwd-eps-base", type=float)
    p.add_argument("--fwd-eps-bear", type=float)
    p.add_argument("--div-yield-pct", type=float, default=0.0)
    p.add_argument("--exit-pe-base", type=float)
    p.add_argument("--exit-pe-bear", type=float)
    p.add_argument("--years", type=int, default=LONG_CHART_YEARS_DEFAULT)
    args = p.parse_args()
    ticker = args.ticker.upper()

    doc_path = os.path.join(ff.CACHE_DIR, f"{ticker}-{date.today().isoformat()}.html")
    if not os.path.exists(doc_path):
        sys.exit(f"No cached page for {ticker} today. Run fetch_fundamentals.py "
                  f"{ticker} first (or --screen {ticker} if you don't hold it).")
    with open(doc_path, encoding="utf-8") as fh:
        doc = fh.read()
    company_id = ff.parse_company_id(doc)
    if not company_id:
        sys.exit(f"Could not read a company id from the cached page for {ticker}.")
    ratios = ff.parse_ratios(doc)
    current_price = ff.to_float(ratios.get("Current Price", ""))
    if current_price is None:
        sys.exit(f"No current price in the cached page for {ticker}.")

    session = requests.Session()
    session.headers.update({"User-Agent": ff.UA, "Accept-Language": "en-US,en;q=0.9"})

    chart = fetch_long_chart(ticker, company_id, session, days=args.years * 365 + 30)
    series = price_series(chart)
    if not series:
        sys.exit(f"No long-history chart available for {ticker}.")

    valid, excluded, latest_eps = pe_band(doc, series, args.years)
    print(f"{ticker} -- own P/E band, last {args.years} fiscal years "
          f"({series[0][0]} to {series[-1][0]} chart coverage)")
    low_confidence = len(valid) < 3
    if not valid:
        print("  No usable years (EPS non-positive or price history too short) -- "
              "band unavailable.")
    else:
        pes = [v for _, v in valid]
        low, high = min(pes), max(pes)
        median = median_of(pes)
        print(f"  Years used ({len(valid)}): " + ", ".join(f"{y[:4]}:{pe}" for y, pe in valid))
        if excluded:
            print(f"  Excluded ({len(excluded)}): " +
                  ", ".join(f"{y[:4]} ({why})" for y, why in excluded))
        if low_confidence:
            print(f"  *** LOW CONFIDENCE: only {len(valid)} usable year(s) -- this is a single data "
                  f"point wearing a band's clothes, not a real range. Don't quote low/median/high as "
                  f"if they carry the weight of a 5-10yr band; say so in the note. ***")
        print(f"  Band: low {low:.1f}x / median {median:.1f}x / high {high:.1f}x")
        # Match the headline trailing P/E's own EPS basis (screener's ratios page,
        # already quoted elsewhere in the note) rather than recomputing from the
        # profit-loss table's TTM row -- the two can disagree (PAYTM: 132 vs 165,
        # apparently different EPS bases on screener's own two pages), and a note
        # quoting both looks like an error even when each is individually correct.
        headline_pe = ff.to_float(ratios.get("Stock P/E", ""))
        current_pe = headline_pe or (current_price / latest_eps if latest_eps and latest_eps > 0 else None)
        if current_pe:
            pct = percentile_of(current_pe, valid)
            print(f"  Today: {current_pe:.1f}x (screener's headline trailing P/E) -- {pct}th percentile "
                  f"of its own {len(valid)}-year range "
                  f"({'at/above the top of its own range' if pct is not None and pct >= 90 else 'at/below the bottom of its own range' if pct is not None and pct <= 10 else 'within its own range'})")
        else:
            print("  Today's trailing EPS is non-positive or unavailable -- no current P/E to place.")

    hurdle = nifty_hurdle_cagr(session, args.years)
    if hurdle:
        print(f"\nNifty (NIFTYBEES) realised CAGR, {hurdle['from']} to {hurdle['to']} "
              f"({hurdle['span_years']}y): {hurdle['cagr_pct']:+.1f}%/yr -- this run's hurdle")
    else:
        print("\nNifty hurdle unavailable (chart fetch failed).")

    if args.fwd_eps_base is not None and args.fwd_eps_bear is not None and valid:
        if low_confidence:
            print(f"\n*** 3-year case built on a LOW CONFIDENCE band ({len(valid)} usable year(s)) -- "
                  f"exit-P/E assumptions below are one data point, not a real range. State that "
                  f"plainly if you quote this case, or override --exit-pe-base/--exit-pe-bear with a "
                  f"peer or sector multiple instead. ***")
        pes = [v for _, v in valid]
        exit_pe_base = args.exit_pe_base or median_of(pes)
        exit_pe_bear = args.exit_pe_bear or min(pes)
        base = three_year_cagr(current_price, args.fwd_eps_base, exit_pe_base, args.div_yield_pct)
        bear = three_year_cagr(current_price, args.fwd_eps_bear, exit_pe_bear, args.div_yield_pct)
        base_div_note = (f", + {args.div_yield_pct:.1f}% div = total ~{base['total_cagr_pct']:+.1f}%/yr"
                          if args.div_yield_pct else "")
        bear_div_note = (f", + {args.div_yield_pct:.1f}% div = total ~{bear['total_cagr_pct']:+.1f}%/yr"
                          if args.div_yield_pct else "")
        print(f"\n3-year case (current price {current_price:.2f}):")
        print(f"  Base: fwd EPS {args.fwd_eps_base:.2f} x exit {exit_pe_base:.1f}x "
              f"= exit price {base['exit_price']:.0f}, price CAGR {base['price_cagr_pct']:+.1f}%/yr"
              f"{base_div_note}")
        print(f"  Bear: fwd EPS {args.fwd_eps_bear:.2f} x exit {exit_pe_bear:.1f}x "
              f"= exit price {bear['exit_price']:.0f}, price CAGR {bear['price_cagr_pct']:+.1f}%/yr"
              f"{bear_div_note}")
        if hurdle:
            hc = hurdle["cagr_pct"]
            base_clears, base_margin = clears_hurdle(base["total_cagr_pct"], hc)
            bear_clears, bear_margin = clears_hurdle(bear["total_cagr_pct"], hc)
            print(f"  vs Nifty hurdle {hc:+.1f}%/yr: base {'clears' if base_clears else 'does not clear'} it "
                  f"by {base_margin:+.1f}pp, bear {'clears' if bear_clears else 'does not clear'} it "
                  f"by {bear_margin:+.1f}pp")
    elif args.fwd_eps_base is not None or args.fwd_eps_bear is not None:
        sys.exit("Pass both --fwd-eps-base and --fwd-eps-bear, or neither.")


if __name__ == "__main__":
    main()
