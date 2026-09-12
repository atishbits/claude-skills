#!/usr/bin/env python3
"""Fetch fundamentals from screener.in for every holding in the latest Zerodha export.

Emits data/snapshot-<date>.json with ratios, quarterly trend, a signal-row
classification and a technical read (DMAs, RSI, momentum, volume). Deliberately
does NOT emit a buy/hold/sell rating -- that stays a judgement call made in the
/portfolio-review command. Technicals are a secondary input there: they sharpen
the re-look price, they do not drive the rating.

The company page carries more than the ratios: cash flow, the yearly ratio
history, 10/5/3-year growth ranges, the quarterly shareholding pattern and dated
concall links are all in the same HTML, already cached. They are parsed here
because each answers a question the top ratios cannot -- whether profit turns
into cash, whether returns are rising or fading, whether current earnings sit
above the company's own trend, and whether promoters and institutions are adding
or leaving. Promoter pledge and insider dealing come from NSE, in
nse_disclosures.py.
"""

import csv
import glob
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime

import requests

import nse_disclosures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", ".cache")
DATA_DIR = os.path.join(ROOT, "data")
CACHE_KEEP_DAYS = 2  # today + yesterday; older days are never read again

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REQUEST_DELAY = 1.2
BACKOFF = [5, 15, 45]

# Zerodha symbol -> screener slug, where they disagree.
SLUG_OVERRIDES = {
    "EMBASSY-RR": "EMBASSY",
}

# Lenders: ROCE is structurally low by the nature of the business, so quality is
# judged on ROE alone. Screener's own sector tags are checked too, this list is
# the belt to that braces.
FINANCIAL_TICKERS = {
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "PNB", "MAHABANK",
    "BAJFINANCE", "BAJAJFINSV", "JIOFIN", "LICI",
}
FINANCIAL_SECTOR_WORDS = ("bank", "finance", "financial", "insurance", "nbfc")

# P/E is only meaningful against the sector. Keyed on screener's sector/industry
# breadcrumb, matched as a substring, first hit wins.
SECTOR_PE_BANDS = {
    "bank": (12, 25),
    "finance": (12, 25),
    "insurance": (15, 35),
    "software": (20, 35),
    "it ": (20, 35),
    "technology": (20, 35),
    "fmcg": (35, 60),
    "consumer": (30, 55),
    "household": (35, 60),
    "food": (30, 55),
    "metal": (8, 18),
    "mining": (8, 18),
    "oil": (8, 18),
    "gas": (10, 22),
    "petroleum": (8, 18),
    "power": (12, 25),
    "utilities": (12, 25),  # not "utilit" -- that matches "Utility Vehicles"
    "pharma": (22, 40),
    "healthcare": (22, 40),
    "chemical": (20, 35),
    "automobile": (18, 35),
    "auto": (18, 35),
    # Screener files CV makers under Capital Goods; they trade like autos.
    "commercial vehicle": (18, 35),
    "tyre": (12, 25),
    "realty": (20, 40),
    "construction": (18, 35),
    "cement": (18, 35),
    "capital goods": (25, 45),
    "engineering": (25, 45),
    "telecom": (20, 40),
    "textile": (12, 25),
    "retail": (35, 60),
}
DEFAULT_PE_BAND = (18, 30)

# Screener's own chart API, the one that draws the DMA overlays on the company
# page. Same host as the ratios, so it reuses the throttle and the daily cache.
CHART_DAYS = 365
CHART_METRICS = "Price-DMA50-DMA200-Volume"

# Listed companies must file within 45 days of a quarter end (60 for the year's
# last), so the newest quarter should never be more than ~3 months + 60 days old.
STALE_QUARTER_DAYS = 150

# Nippon India ETF Nifty 50 BeES, on screener's own chart API. An ETF that
# tracks the index is the benchmark that can be fetched the same way every
# holding is, so beta needs no second data source.
BENCHMARK = {"ticker": "NIFTYBEES", "company_id": "1272632", "name": "Nifty 50 (NIFTYBEES)"}

# Earnings sitting far above a company's own long-run return usually means the
# trailing P/E is resting on profits it will not repeat -- the Lupin case in
# new-ideas.md, where last year's ROE was 29% against 10% over ten years.
ROE_ABOVE_TREND = 1.4
ROE_BELOW_TREND = 0.6
# Profit that does not become cash. Five years of CFO against five of PAT, so a
# single working-capital year does not trip it.
CFO_TO_PAT_WEAK = 0.6

# Every note must carry these, so a rewrite on an old template shows up in PORTFOLIO.md.
NOTE_REQUIRED = {
    "Action": r"\*\*Action:\*\*",
    "Balance sheet": r"\*\*Balance sheet:\*\*",
    "Guidance": r"\*\*Guidance:\*\*",
    "Portfolio context": r"\*\*Portfolio context:\*\*",
    "disclaimer footer": r"Not investment advice",
}

ROW_TEXT = {
    1: "Low P/E + high ROE/ROCE - potentially undervalued quality business",
    2: "High P/E + high ROE/ROCE - great business, but priced richly",
    3: "High P/E + low ROE/ROCE - expensive with weak fundamentals, caution",
    4: "Low P/E + low ROE/ROCE - cheap for a reason, possible value trap",
}


# --------------------------------------------------------------------------- io

def latest_holdings_csv(required=True):
    """The newest broker export in the project root. Zerodha's own filename is
    the common case, but any *holdings*.csv with the same columns works.

    Returns None when there is none and the caller can live without it: a
    --screen run rates stocks nobody owns, so it should not need a portfolio."""
    files = (glob.glob(os.path.join(ROOT, "zerodha_holdings_*.csv"))
             + glob.glob(os.path.join(ROOT, "*holdings*.csv")))
    files = [f for f in set(files) if not os.path.basename(f).startswith("holdings-template")]
    if not files:
        if required:
            sys.exit(f"No holdings CSV found in {ROOT}.\n"
                     "Put a broker export there as zerodha_holdings_<date>.csv (columns: "
                     "Instrument, Qty., Avg. cost, LTP, Invested, Cur. val, P&L, Net chg.),\n"
                     "or rate a stock without holding it: "
                     "fetch_fundamentals.py --screen TICKER")
        return None
    return max(files, key=os.path.getmtime)


def holdings_date(path):
    """The export date is in the filename (zerodha_holdings_6September2026.csv);
    the CSV's LTP column is that day's price, not a live one."""
    m = re.search(r"(\d{1,2})([A-Za-z]+)(\d{4})", os.path.basename(path))
    if m:
        for fmt_ in ("%d%B%Y", "%d%b%Y"):
            try:
                return datetime.strptime("".join(m.groups()), fmt_).date().isoformat()
            except ValueError:
                pass
    return date.fromtimestamp(os.path.getmtime(path)).isoformat()


def read_holdings(path):
    holdings = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("Instrument") or "").strip()
            if not sym:
                continue
            holdings.append({
                "ticker": sym,
                "qty": num(row.get("Qty.")),
                "avg_cost": num(row.get("Avg. cost")),
                "ltp": num(row.get("LTP")),
                "invested": num(row.get("Invested")),
                "current_value": num(row.get("Cur. val")),
                "pnl": num(row.get("P&L")),
                "pnl_pct": num(row.get("Net chg.")),
            })
    return holdings


def num(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ---------------------------------------------------------------------- fetching

def get(url, session):
    """GET with backoff on 429. Returns the body, or None on 404."""
    for attempt in range(len(BACKOFF) + 1):
        try:
            r = session.get(url, timeout=25)
        except requests.RequestException as exc:
            if attempt == len(BACKOFF):
                raise RuntimeError(f"network error: {exc}")
            time.sleep(BACKOFF[attempt])
            continue
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            if attempt == len(BACKOFF):
                raise RuntimeError("rate limited (429) after retries")
            print(f"    429, backing off {BACKOFF[attempt]}s", file=sys.stderr)
            time.sleep(BACKOFF[attempt])
            continue
        raise RuntimeError(f"HTTP {r.status_code}")
    raise RuntimeError("exhausted retries")


def resolve_slug(ticker, session):
    """Ask screener's own search to map a symbol we can't guess."""
    body = get(f"https://www.screener.in/api/company/search/?q={ticker}", session)
    time.sleep(REQUEST_DELAY)
    if not body:
        return None
    try:
        hits = json.loads(body)
    except ValueError:
        return None
    for hit in hits:
        m = re.match(r"/company/([^/]+)/", hit.get("url", ""))
        if m:
            return m.group(1)
    return None


def has_ratios(doc):
    """A company with no consolidated accounts still returns 200 for
    /consolidated/, but with every value blank -- so 200 is not enough."""
    r = parse_ratios(doc)
    return to_float(r.get("Current Price", "")) is not None


def quarter_age_days(doc):
    dates, _ = parse_table(doc, "quarters")
    try:
        return (date.today() - date.fromisoformat(dates[-1])).days
    except (IndexError, ValueError):
        return None


def fetch(ticker, session, stats, force=False):
    cache = os.path.join(CACHE_DIR, f"{ticker}-{date.today().isoformat()}.html")
    if os.path.exists(cache) and not force:
        stats["cached"] += 1
        with open(cache, encoding="utf-8") as fh:
            return fh.read()

    slugs = [SLUG_OVERRIDES.get(ticker, ticker)]
    tried_search = False
    while slugs:
        slug = slugs.pop(0)
        # A company that loses its last subsidiary (Sanofi India after the 2024
        # demerger) keeps a consolidated page with live ratios but financials frozen
        # at the last consolidated filing. So a stale consolidated page is not
        # accepted until standalone has been checked for something newer.
        candidates = []
        for url in (f"https://www.screener.in/company/{slug}/consolidated/",
                    f"https://www.screener.in/company/{slug}/"):
            doc = get(url, session)
            time.sleep(REQUEST_DELAY)
            if doc and has_ratios(doc):
                age = quarter_age_days(doc)
                candidates.append((10**6 if age is None else age, doc))
                if age is not None and age <= STALE_QUARTER_DAYS:
                    break
        if candidates:
            doc = min(candidates, key=lambda c: c[0])[1]
            with open(cache, "w", encoding="utf-8") as fh:
                fh.write(doc)
            stats["fetched"] += 1
            return doc
        if not tried_search:
            tried_search = True
            found = resolve_slug(ticker, session)
            if found and found != slug:
                slugs.append(found)
    raise RuntimeError("no usable page on screener")


def fetch_chart(ticker, company_id, session, stats, force=False):
    """Daily closes + screener's own DMA50/DMA200 + volume. Cached per day like
    the ratios page. Returns None rather than raising -- a missing chart costs a
    technical read, it should never sink the whole ticker."""
    if not company_id:
        return None
    cache = os.path.join(CACHE_DIR, f"{ticker}-chart-{date.today().isoformat()}.json")
    if os.path.exists(cache) and not force:
        stats["chart_cached"] += 1
        try:
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            pass
    url = (f"https://www.screener.in/api/company/{company_id}/chart/"
           f"?q={CHART_METRICS}&days={CHART_DAYS}&consolidated=true")
    try:
        body = get(url, session)
        time.sleep(REQUEST_DELAY)
        if not body:
            return None
        data = json.loads(body)
    except (RuntimeError, ValueError, requests.RequestException):
        return None
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    stats["chart_fetched"] += 1
    return data


# ----------------------------------------------------------------------- parsing

def clean(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def to_float(s):
    s = re.sub(r"[₹,%]|Cr\.?|\s", "", s or "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_ratios(doc):
    """The value span carries class 'nowrap value', not 'value'."""
    block = re.search(r'<ul id="top-ratios">(.*?)</ul>', doc, re.S)
    if not block:
        return {}
    out = {}
    for li in re.findall(r"<li[^>]*>(.*?)</li>", block.group(1), re.S):
        name = re.search(r'<span class="name">(.*?)</span>', li, re.S)
        value = re.search(r'<span class="nowrap value">(.*?)</span>\s*$', li, re.S)
        if not value:
            value = re.search(r'<span class="nowrap value">(.*)', li, re.S)
        if name and value:
            out[clean(name.group(1))] = clean(value.group(1))
    return out


def parse_sector(doc):
    tags = {}
    for m in re.finditer(r'<a href="/market/[^"]*"\s+target="_blank"\s+title="([^"]+)">(.*?)</a>',
                         doc, re.S):
        tags[m.group(1).strip().lower()] = clean(m.group(2))
    return {
        "broad_sector": tags.get("broad sector"),
        "sector": tags.get("sector"),
        "industry": tags.get("industry"),
    }


def parse_table(doc, section_id):
    """One of screener's statement tables (quarters, profit-loss, balance-sheet):
    the period keys and {row label: values}. The trailing '+' on a label only
    marks an expandable schedule, so it is dropped."""
    sec = re.search(r'id="%s".*?<table[^>]*>(.*?)</table>' % section_id, doc, re.S)
    if not sec:
        return [], {}
    table = sec.group(1)
    dates = re.findall(r'data-date-key="([^"]+)"', table)
    rows = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 2:
            continue
        label = clean(cells[0]).rstrip("+").strip()
        rows.setdefault(label, [to_float(clean(c)) for c in cells[1:]])
    return dates, rows


def parse_quarters(doc):
    dates, rows = parse_table(doc, "quarters")
    if not dates:
        return {}
    out = {"period_end": dates[-8:]}
    # Lenders label the top line "Revenue" rather than "Sales".
    for labels, key in ((("Sales", "Revenue"), "sales"), (("Net Profit",), "net_profit"),
                        (("Other Income",), "other_income"), (("Profit before tax",), "pbt")):
        for label in labels:
            if label in rows:
                out[key] = rows[label][-8:]
                break
    # Lender-format tables book fee income as Other Income: it is operating there.
    out["lender_format"] = "Revenue" in rows and "Sales" not in rows
    return out


def fiscal_year_end(doc):
    """Month the company closes its books, read from the annual P&L columns.
    Most Indian companies close in March; MNC subsidiaries often follow the
    parent's calendar year."""
    dates, _ = parse_table(doc, "profit-loss")
    for d in reversed(dates):
        try:
            return date.fromisoformat(d).strftime("%b")
        except ValueError:
            continue
    return None


def leverage(doc, financial):
    """Gross borrowings against net worth and TTM operating profit. Cash is not
    netted -- screener's summary balance sheet does not break it out -- and the
    balance sheet is the last annual (or half-year) one, so it lags the quarter."""
    if financial:
        return {"applicable": False,
                "note": "lender: borrowings are the raw material, judge on ROE and asset quality"}
    dates, bs = parse_table(doc, "balance-sheet")
    borrow, eq, res = bs.get("Borrowings"), bs.get("Equity Capital"), bs.get("Reserves")
    if not (dates and borrow and eq and res) or None in (borrow[-1], eq[-1], res[-1]):
        return None
    net_worth = eq[-1] + res[-1]
    _, q = parse_table(doc, "quarters")
    op = [v for v in (q.get("Operating Profit") or [])[-4:] if v is not None]
    ebitda_ttm = sum(op) if len(op) == 4 else None

    prev = borrow[-2] if len(borrow) > 1 else None
    change = pct_above(borrow[-1], prev) if prev else None
    de = round(borrow[-1] / net_worth, 2) if net_worth > 0 else None
    d_ebitda = round(borrow[-1] / ebitda_ttm, 2) if ebitda_ttm and ebitda_ttm > 0 else None
    # Borrowings include lease liabilities, so a cash-rich IT firm shows "debt"
    # that grows with its office leases. Below these levels direction is noise.
    if (de is not None and de < 0.1) or (d_ebitda is not None and d_ebitda < 0.5):
        trend = "low"
    elif change is None:
        trend = None
    elif change > 10:
        trend = "rising"
    elif change < -10:
        trend = "falling"
    else:
        trend = "flat"
    return {
        "applicable": True,
        "as_of": dates[-1],
        "borrowings_cr": borrow[-1],
        "borrowings_prev_cr": prev,
        "borrowings_change_pct": change,
        "trend": trend,
        "net_worth_cr": round(net_worth, 1),
        "debt_to_equity": de,
        "ebitda_ttm_cr": ebitda_ttm,
        "debt_to_ebitda": d_ebitda,
    }


def parse_company_id(doc):
    m = re.search(r'company-id="(\d+)"', doc)
    return m.group(1) if m else None


def annual_series(doc, section_id, labels):
    """A statement row keyed by its year end, so two tables can be lined up.
    The annual P&L carries a trailing TTM column the cash flow does not, which
    is exactly the mismatch that would silently shift CFO against the wrong
    year's profit."""
    dates, rows = parse_table(doc, section_id)
    for label in labels:
        if label in rows:
            return {d: v for d, v in zip(dates, rows[label]) if re.match(r"\d{4}-", d)}
    return {}


def parse_cash_flow(doc, financial):
    """Whether reported profit turns into cash. Meaningless for lenders, whose
    operating cash flow is really deposit and loan flow, so it is not computed
    for them rather than computed and quietly misread."""
    cfo = annual_series(doc, "cash-flow", ("Cash from Operating Activity",))
    if not cfo:
        return None
    years = sorted(cfo)[-5:]
    out = {"years": years,
           "cfo_cr": [cfo[y] for y in years],
           "fcf_cr": [annual_series(doc, "cash-flow", ("Free Cash Flow",)).get(y) for y in years],
           "years_cfo_negative": sum(1 for y in years if (cfo[y] or 0) < 0),
           "applicable": not financial}
    if financial:
        out["note"] = "lender: operating cash flow is deposit and loan flow, not a quality signal"
        return out
    pat = annual_series(doc, "profit-loss", ("Net Profit",))
    pairs = [(cfo[y], pat[y]) for y in years if pat.get(y) is not None and cfo.get(y) is not None]
    if len(pairs) >= 3:
        c, p = sum(x for x, _ in pairs), sum(y for _, y in pairs)
        out["cfo_to_pat"] = round(c / p, 2) if p > 0 else None
        out["cfo_to_pat_years"] = len(pairs)
        out["cfo_weak"] = bool(out["cfo_to_pat"] is not None
                               and out["cfo_to_pat"] < CFO_TO_PAT_WEAK)
    return out


def parse_ratio_history(doc):
    """Five years of ROCE and the working-capital cycle. A falling ROCE says the
    business is getting worse at converting capital into profit, which the
    current-year ratio alone cannot show; stretching debtor days is how a
    revenue line keeps growing while the cash does not."""
    dates, rows = parse_table(doc, "ratios")
    years = [d for d in dates if re.match(r"\d{4}-", d)][-5:]
    if not years:
        return None
    out = {"years": years}
    for label, key in (("ROCE %", "roce"), ("ROE %", "roe"),
                       ("Debtor Days", "debtor_days"),
                       ("Inventory Days", "inventory_days"),
                       ("Working Capital Days", "working_capital_days"),
                       ("Cash Conversion Cycle", "cash_conversion_cycle")):
        if label in rows:
            out[key] = rows[label][-len(years):]
    roce = [v for v in (out.get("roce") or []) if v is not None]
    if len(roce) >= 3 and max(roce) > 0:
        out["roce_peak_5y"] = max(roce)
        out["roce_latest"] = roce[-1]
        out["roce_fading"] = bool(roce[-1] < 0.6 * max(roce))
    dd = [v for v in (out.get("debtor_days") or []) if v is not None]
    if len(dd) >= 3:
        typical = _median(dd[:-1])
        out["debtor_days_latest"] = dd[-1]
        out["debtor_days_typical"] = typical
        out["debtor_days_stretching"] = bool(typical and dd[-1] > 1.5 * typical and dd[-1] > 45)
    return out


def parse_growth_ranges(doc):
    """The four 10/5/3-year tables under the chart. The ROE one is the useful
    one: last year against the ten-year average says whether the earnings the
    P/E is resting on are normal for this business."""
    keys = {"Compounded Sales Growth": "sales_growth",
            "Compounded Profit Growth": "profit_growth",
            "Stock Price CAGR": "price_cagr", "Return on Equity": "roe"}
    out = {}
    for m in re.finditer(r'<table class="ranges-table">(.*?)</table>', doc, re.S):
        cells = [clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", m.group(1), re.S)]
        if not cells or cells[0] not in keys:
            continue
        out[keys[cells[0]]] = {lbl.rstrip(":").strip().lower().replace(" ", "_"): to_float(val)
                               for lbl, val in zip(cells[1::2], cells[2::2])}
    if not out:
        return None
    roe = out.get("roe") or {}
    last = roe.get("last_year")
    basis = "5_years" if roe.get("5_years") else ("10_years" if roe.get("10_years") else None)
    trend = roe.get(basis) if basis else None
    if last is not None and trend and trend > 0:
        ratio = round(last / trend, 2)
        out["roe_vs_trend"] = ratio
        out["roe_trend_pct"] = trend
        out["roe_trend_basis"] = basis.replace("_", " ")
        out["earnings_above_trend"] = bool(ratio >= ROE_ABOVE_TREND)
        out["earnings_below_trend"] = bool(ratio <= ROE_BELOW_TREND)
    return out


def parse_shareholding(doc):
    """Quarterly shareholding. Promoters cutting a stake, or institutions
    leaving over several quarters, is the part of the value-trap question the
    ratios never answer. This table has no data-date-key, so its periods come
    from the header cells."""
    t = re.search(r'id="quarterly-shp".*?<table[^>]*>(.*?)</table>', doc, re.S)
    if not t:
        return None
    table = t.group(1)
    periods = [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
    periods = [p for p in periods if re.match(r"[A-Z][a-z]{2} \d{4}$", p)]
    rows = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 2:
            continue
        rows.setdefault(clean(cells[0]).rstrip("+").strip(),
                        [to_float(clean(c)) for c in cells[1:]])
    if not periods or not rows:
        return None
    keep = 8
    out = {"period_end": periods[-keep:]}
    for label, key in (("Promoters", "promoters"), ("FIIs", "fiis"), ("DIIs", "diis"),
                       ("Public", "public"), ("No. of Shareholders", "shareholders")):
        if label in rows:
            out[key] = rows[label][-keep:]
    out["window"] = f"{out['period_end'][0]} to {out['period_end'][-1]}"
    for key in ("promoters", "fiis", "diis"):
        s = [v for v in (out.get(key) or []) if v is not None]
        if len(s) >= 2:
            out[f"{key}_latest"] = s[-1]
            out[f"{key}_change_pp"] = round(s[-1] - s[0], 2)
    return out


def parse_concalls(doc):
    """Dated links to the earnings-call transcript and investor presentation.
    These are the primary source for guidance, which otherwise gets taken from a
    search summary -- the mistake that produced a fabricated broker target."""
    block = re.search(r">Concalls</h3>(.*?)</section>", doc, re.S)
    if not block:
        return None
    items = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", block.group(1), re.S):
        month = re.search(r'style="width: 74px">([^<]+)<', li)
        if not month:
            continue
        links = {}
        for href, text in re.findall(r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", li, re.S):
            label = clean(text).lower()
            if label in ("transcript", "ppt", "notes") and label not in links:
                links[label] = href
        if links:
            items.append(dict(month=clean(month.group(1)), **links))
    return items[:3] or None


def parse_pros_cons(doc):
    out = {}
    for kind in ("pros", "cons"):
        m = re.search(r'<div class="%s"[^>]*>(.*?)</div>' % kind, doc, re.S)
        out[kind] = [clean(li) for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S)] if m else []
    return out


# -------------------------------------------------------------------- technicals

def rsi(closes, period=14):
    """Wilder's RSI. Needs period+1 closes; returns None below that."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for prev, cur in zip(closes[:period], closes[1:period + 1]):
        diff = cur - prev
        gains += max(diff, 0.0)
        losses += max(-diff, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    for prev, cur in zip(closes[period:-1], closes[period + 1:]):
        diff = cur - prev
        avg_gain = (avg_gain * (period - 1) + max(diff, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0.0)) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def pct_above(price, level):
    if price is None or not level:
        return None
    return round((price - level) / level * 100, 1)


def chart_closes(chart):
    """(dates, closes) from screener's chart payload."""
    dates, closes = [], []
    for ds in (chart or {}).get("datasets", []):
        if ds.get("metric") != "Price":
            continue
        for row in ds.get("values") or []:
            v = to_float(str(row[1])) if len(row) > 1 else None
            if v is not None:
                dates.append(row[0])
                closes.append(v)
    return dates, closes


def max_drawdown(closes):
    """Worst peak-to-trough fall over the window, as a negative percent."""
    peak, worst = None, 0.0
    for c in closes:
        peak = c if peak is None else max(peak, c)
        if peak:
            worst = min(worst, (c - peak) / peak * 100)
    return round(worst, 1)


def market_risk(chart, bench):
    """Beta against the Nifty, and how much of the move the index explains.

    Beta is computed on the daily closes both series already have, aligned by
    date so a trading holiday in one cannot shift the other. r2 is reported
    alongside because a beta from a stock that barely tracks the index is a
    number without a meaning."""
    if not bench:
        return None
    dates, closes = chart_closes(chart)
    by_date = dict(zip(dates, closes))
    common = [d for d in bench["dates"] if d in by_date]
    if len(common) < 120:
        return None
    bench_by_date = dict(zip(bench["dates"], bench["closes"]))
    sr, br = [], []
    for prev, cur in zip(common, common[1:]):
        if by_date[prev] and bench_by_date[prev]:
            sr.append(by_date[cur] / by_date[prev] - 1)
            br.append(bench_by_date[cur] / bench_by_date[prev] - 1)
    n = len(sr)
    if n < 100:
        return None
    ms, mb = sum(sr) / n, sum(br) / n
    cov = sum((a - ms) * (b - mb) for a, b in zip(sr, br)) / n
    var_b = sum((b - mb) ** 2 for b in br) / n
    var_s = sum((a - ms) ** 2 for a in sr) / n
    if not var_b or not var_s:
        return None
    beta = cov / var_b
    return {"beta": round(beta, 2),
            "r2": round(cov ** 2 / (var_b * var_s), 2),
            "days": n,
            "benchmark": BENCHMARK["name"]}


def compute_technicals(chart, price):
    """Turn screener's chart series into the handful of readings that actually
    inform a long-term entry: where price sits against its own trend, whether
    it is stretched, and whether volume is confirming."""
    if not chart:
        return None
    series = {}
    for ds in chart.get("datasets", []):
        series[ds.get("metric")] = ds.get("values") or []
    price_rows = series.get("Price") or []
    closes, dates = [], []
    for row in price_rows:
        v = to_float(str(row[1])) if len(row) > 1 else None
        if v is not None:
            closes.append(v)
            dates.append(row[0])
    if len(closes) < 30:
        return None

    def last_val(metric):
        for row in reversed(series.get(metric) or []):
            v = to_float(str(row[1])) if len(row) > 1 else None
            if v is not None:
                return round(v, 2)
        return None

    if price is None:
        price = closes[-1]
    dma50, dma200 = last_val("DMA50"), last_val("DMA200")
    bars = len(closes)

    # Screener ramps the DMA from the first bar it has, so a stock that listed
    # recently (a demerger, an IPO) shows a "200 DMA" built on far less data.
    dma200_reliable = bars >= 200

    def ret_over(n):
        return pct_above(price, closes[-n]) if bars > n else None

    window = closes[-60:]
    vol_rows = series.get("Volume") or []
    vols = [row[1] for row in vol_rows if len(row) > 1 and isinstance(row[1], (int, float))]
    vol_ratio = delivery = None
    if len(vols) >= 40:
        recent = sum(vols[-20:]) / 20
        base = sum(vols) / len(vols)
        if base:
            vol_ratio = round(recent / base, 2)
    for row in reversed(vol_rows):
        if len(row) > 2 and isinstance(row[2], dict) and row[2].get("delivery") is not None:
            delivery = row[2]["delivery"]
            break

    trend = None
    if dma50 and dma200 and dma200_reliable:
        trend = "uptrend (50DMA above 200DMA)" if dma50 > dma200 \
            else "downtrend (50DMA below 200DMA)"

    r = rsi(closes)
    if r is None:
        rsi_note = None
    elif r >= 70:
        rsi_note = "overbought"
    elif r <= 30:
        rsi_note = "oversold"
    else:
        rsi_note = "neutral"

    return {
        "as_of": dates[-1],
        "last_close": closes[-1],
        "close_low_1y": round(min(closes), 2),
        "close_high_1y": round(max(closes), 2),
        "bars": bars,
        "dma50": dma50,
        "dma200": dma200,
        "dma200_reliable": dma200_reliable,
        "pct_vs_dma50": pct_above(price, dma50),
        "pct_vs_dma200": pct_above(price, dma200) if dma200_reliable else None,
        "trend": trend,
        "rsi14": r,
        "rsi_note": rsi_note,
        "return_3m_pct": ret_over(63),
        "return_6m_pct": ret_over(126),
        "return_1y_pct": pct_above(price, closes[0]) if bars >= 200 else None,
        "max_drawdown_1y_pct": max_drawdown(closes),
        "recent_low_60d": round(min(window), 2),
        "recent_high_60d": round(max(window), 2),
        "vol_20d_vs_avg": vol_ratio,
        "delivery_pct": delivery,
    }


# -------------------------------------------------------------------- classifying

def pe_band(sector_info, ticker):
    """Match the most specific classification first. Screener's broad sector is
    coarse -- Apollo Tyres and Maruti both sit under 'Consumer Discretionary',
    which would otherwise hand them an FMCG-style band. Industry wins over
    sector, sector over broad sector, and the longest key wins within each."""
    if ticker in FINANCIAL_TICKERS:
        return SECTOR_PE_BANDS["bank"], "sector:financial"
    for field in ("industry", "sector", "broad_sector"):
        text = (sector_info.get(field) or "").lower()
        if not text:
            continue
        hits = [k for k in SECTOR_PE_BANDS if k in text]
        if hits:
            key = max(hits, key=len)
            return SECTOR_PE_BANDS[key], f"{field}:{key.strip()}"
    return DEFAULT_PE_BAND, "absolute"


def is_financial(sector_info, ticker):
    if ticker in FINANCIAL_TICKERS:
        return True
    haystack = " ".join(filter(None, [
        (sector_info.get("industry") or "").lower(),
        (sector_info.get("sector") or "").lower(),
    ]))
    return any(w in haystack for w in FINANCIAL_SECTOR_WORDS)


def classify(pe, roe, roce, sector_info, ticker):
    """Return signal row 1-4 plus the reasoning behind it."""
    band, basis = pe_band(sector_info, ticker)
    lo, hi = band
    fin = is_financial(sector_info, ticker)

    # No P/E means loss-making: no earnings can justify any price.
    if pe is None:
        pe_level, pe_lean = "none", "high"
    elif pe < lo:
        pe_level = pe_lean = "low"
    elif pe > hi:
        pe_level = pe_lean = "high"
    else:
        pe_level = "mid"
        pe_lean = "low" if pe < (lo + hi) / 2 else "high"

    metrics = [roe] if fin else [m for m in (roe, roce) if m is not None]
    if not metrics or roe is None:
        q_level = q_lean = "unknown"
    elif min(metrics) >= 15:
        q_level = q_lean = "high"
    elif min(metrics) < 10:
        q_level = q_lean = "low"
    else:
        q_level = "mid"
        q_lean = "high" if min(metrics) >= 12.5 else "low"

    if q_lean == "unknown":
        return None, {"pe_level": pe_level, "quality_level": q_level,
                      "pe_basis": basis, "pe_band": band, "financial": fin,
                      "confidence": "none",
                      "note": "insufficient ratio data to place a row"}

    row = {("low", "high"): 1, ("high", "high"): 2,
           ("high", "low"): 3, ("low", "low"): 4}[(pe_lean, q_lean)]

    confidence = "high"
    if pe_level == "mid" or q_level == "mid":
        confidence = "low"
    elif pe_level == "none":
        confidence = "high"
    if basis == "absolute":
        confidence = "low"

    return row, {"pe_level": pe_level, "quality_level": q_level,
                 "pe_basis": basis, "pe_band": band, "financial": fin,
                 "confidence": confidence,
                 "note": "loss-making, no P/E" if pe_level == "none" else None}


def pct_change(series):
    """Latest quarter vs the same quarter a year earlier (4 back)."""
    if not series or len(series) < 5:
        return None
    latest, year_ago = series[-1], series[-5]
    if latest is None or year_ago is None or year_ago == 0:
        return None
    return round((latest - year_ago) / abs(year_ago) * 100, 1)


# ---------------------------------------------------------------------------- main

def week52_check(low, high, tech):
    """Screener's 52-week High/Low against the chart's own daily closes. Screener
    uses intraday extremes, so a few percent of gap is normal; more than that
    means one of the two is wrong and the note should not lean on either."""
    if not tech or not low or not high:
        return None
    cl, ch = tech["close_low_1y"], tech["close_high_1y"]
    return {"chart_low": cl, "chart_high": ch,
            "agrees": abs(low - cl) / cl <= 0.05 and abs(high - ch) / ch <= 0.05}


def runrate_pe(mcap, quarters):
    """Market cap over the latest quarter annualised. Only useful as a tell: when
    it and the trailing P/E are far apart, neither is a usable anchor alone."""
    np_q = [v for v in (quarters.get("net_profit") or []) if v is not None]
    if not mcap or not np_q or np_q[-1] <= 0:
        return None
    return round(mcap / (np_q[-1] * 4), 1)


ONE_OFF_SHARE = 0.15       # excess other income above this share of PBT distorts the quarter
ONE_OFF_SPIKE = 2.0        # ...and only when other income is at least this multiple of its norm
OTHER_INCOME_HEAVY = 0.50  # other income above this share of PBT: profit isn't mostly operating


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def one_off_check(quarters, mcap):
    """Screener folds exceptional gains into Other Income, so a quarter whose
    other income sits well above the company's own norm is carrying a one-off.
    In the latest quarter that flatters the run-rate P/E (ITC, Jun 2026); in the
    year-ago quarter it distorts YoY growth (Hero's Ather gain, Jun 2025).

    The ex-one-off profit is approximate: excess other income is stripped at the
    quarter's own tax rate, and only when the quarter is flagged: lumpy but
    recurring treasury income (Maruti) is not a one-off. It is a prompt to check
    the company's exceptional items, not a replacement for them.

    Skipped for lender-format tables, where Other Income is fee income."""
    if quarters.get("lender_format"):
        return None
    oi, pbt, np_ = (quarters.get(k) or [] for k in ("other_income", "pbt", "net_profit"))
    n = min(len(oi), len(pbt), len(np_))
    if n < 5:
        return None
    oi, pbt, np_ = oi[-n:], pbt[-n:], np_[-n:]

    def quarter(i):
        if None in (oi[i], pbt[i], np_[i]) or pbt[i] <= 0:
            return None
        # Negative quarters are write-offs; leaving them in drags the norm to zero
        # and makes any ordinary positive quarter look like a spike.
        others = [v for j, v in enumerate(oi) if j != i % n and v is not None and v >= 0]
        if len(others) < 2:
            return None
        typical = _median(others)
        excess = max(0.0, oi[i] - typical)
        flag = oi[i] >= ONE_OFF_SPIKE * typical and excess > ONE_OFF_SHARE * pbt[i]
        tax = min(max(1 - np_[i] / pbt[i], 0.0), 0.35)
        return {"other_income": oi[i], "typical": round(typical, 1),
                "excess_pct_of_pbt": round(excess / pbt[i] * 100, 1),
                "flag": flag,
                "net_profit_ex_one_off": round(np_[i] - (excess * (1 - tax) if flag else 0), 1)}

    latest, year_ago = quarter(-1), quarter(-5)
    out = {"latest": latest, "year_ago": year_ago}
    if latest:
        out["other_income_share_of_pbt_pct"] = round(oi[-1] / pbt[-1] * 100, 1)
        out["other_income_heavy"] = oi[-1] > OTHER_INCOME_HEAVY * pbt[-1]
        adj = latest["net_profit_ex_one_off"]
        out["pe_runrate_ex_one_off"] = round(mcap / (adj * 4), 1) if mcap and adj > 0 else None
    if latest and year_ago and year_ago["net_profit_ex_one_off"] > 0:
        out["profit_yoy_ex_one_off_pct"] = round(
            (latest["net_profit_ex_one_off"] / year_ago["net_profit_ex_one_off"] - 1) * 100, 1)
    return out


def build(holding, doc, chart=None, csv_date=None, bench=None, nse=None):
    ratios = parse_ratios(doc)
    sector_info = parse_sector(doc)
    quarters = parse_quarters(doc)

    price = to_float(ratios.get("Current Price", ""))
    pe = to_float(ratios.get("Stock P/E", ""))
    roe = to_float(ratios.get("ROE", ""))
    roce = to_float(ratios.get("ROCE", ""))
    mcap = to_float(ratios.get("Market Cap", ""))

    hl = ratios.get("High / Low", "")
    nums = re.findall(r"[\d,]+\.?\d*", hl.replace("₹", ""))
    high = to_float(nums[0]) if len(nums) > 0 else None
    low = to_float(nums[1]) if len(nums) > 1 else None

    row, detail = classify(pe, roe, roce, sector_info, holding["ticker"])

    pos = None
    if high is not None and low is not None and price is not None and high > low:
        pos = round((price - low) / (high - low) * 100, 1)

    tech = compute_technicals(chart, price)
    pe_rr = runrate_pe(mcap, quarters)
    latest_q = (quarters.get("period_end") or [None])[-1]
    q_age = quarter_age_days(doc)

    rec = dict(holding)
    rec.update({
        "name": clean(re.search(r"<h1[^>]*>(.*?)</h1>", doc, re.S).group(1))
                if re.search(r"<h1[^>]*>(.*?)</h1>", doc, re.S) else holding["ticker"],
        "basis": "consolidated" if "Consolidated Figures" in doc else "standalone",
        "fiscal_year_end": fiscal_year_end(doc),
        "latest_quarter_end": latest_q,
        "results_stale": q_age is not None and q_age > STALE_QUARTER_DAYS,
        "price": price,
        "csv_date": csv_date,
        "price_vs_csv_pct": pct_above(price, holding.get("ltp")),
        "pe": pe,
        "pe_runrate": pe_rr,
        "pe_runrate_diverges": bool(pe and pe_rr and max(pe, pe_rr) / min(pe, pe_rr) > 2),
        "roe": roe,
        "roce": roce,
        "leverage": leverage(doc, detail["financial"]),
        "market_cap_cr": mcap,
        "book_value": to_float(ratios.get("Book Value", "")),
        "dividend_yield": to_float(ratios.get("Dividend Yield", "")),
        "week52_high": high,
        "week52_low": low,
        "week52_check": week52_check(low, high, tech),
        "pct_of_52wk_range": pos,
        "sector": sector_info,
        "signal_row": row,
        "signal_row_text": ROW_TEXT.get(row),
        "classification": detail,
        "quarters": quarters,
        "sales_yoy_pct": pct_change(quarters.get("sales")),
        "profit_yoy_pct": pct_change(quarters.get("net_profit")),
        "one_offs": one_off_check(quarters, mcap),
        "cash_flow": parse_cash_flow(doc, detail["financial"]),
        "ratio_history": parse_ratio_history(doc),
        "growth_ranges": parse_growth_ranges(doc),
        "shareholding": parse_shareholding(doc),
        "concalls": parse_concalls(doc),
        "pros_cons": parse_pros_cons(doc),
        "technicals": tech,
        "market_risk": market_risk(chart, bench),
        "nse": nse,
    })
    if holding["avg_cost"] and price:
        rec["pnl_pct_live"] = round((price - holding["avg_cost"]) / holding["avg_cost"] * 100, 1)
    return rec


def read_stock_note(ticker):
    """Pull the standing rating out of stocks/<T>.md so the summary table can
    carry it forward without Claude having to retype 73 rows."""
    path = os.path.join(ROOT, "stocks", f"{ticker}.md")
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    out = {}
    m = re.search(r"\*\*Rating:\*\*\s*(.+)", text)
    if m:
        # Keep the verdict clause only; the reasoning lives in the stock file.
        r = re.sub(r"[*_]", "", m.group(1))
        r = re.split(r"(?<=[a-z])\.\s|\. |;", r)[0]
        out["rating"] = re.sub(r"\s+", " ", r).strip(" .")
    m = re.search(r"\*\*Last analysis:\*\*\s*([^(\n]+)", text)
    if m:
        out["last_analysis"] = m.group(1).strip()
    out["missing"] = [name for name, pat in NOTE_REQUIRED.items() if not re.search(pat, text)]
    return out


def add_portfolio_context(stocks):
    """Position and sector weight from the CSV's current value, so a note can say
    what an add does to concentration. Recomputed every run, carried-over rows too."""
    total = sum(s.get("current_value") or 0 for s in stocks) or 1
    for s in stocks:
        sec = s.get("sector") or {}
        s["sector_name"] = sec.get("sector") or sec.get("broad_sector") or "Unclassified"
        s["weight_pct"] = round((s.get("current_value") or 0) / total * 100, 2)
    by_sector = {}
    for s in stocks:
        by_sector.setdefault(s["sector_name"], []).append(s)
    for s in stocks:
        peers = by_sector[s["sector_name"]]
        s["sector_weight_pct"] = round(sum(p["weight_pct"] for p in peers), 1)
        s["sector_peers"] = [{"ticker": p["ticker"], "weight_pct": p["weight_pct"]}
                             for p in sorted(peers, key=lambda p: -p["weight_pct"])
                             if p["ticker"] != s["ticker"]]
    return by_sector


def portfolio_risk(stocks, bench):
    """Book-level readings that no single holding shows.

    Beta is weight-weighted, which is the one portfolio statistic that
    aggregates honestly this way. Deliberately absent: portfolio volatility and
    drawdown, which need the daily series of every holding at once -- a subset
    run only refreshes some of them, and a half-computed risk number is worse
    than none. Effective positions is 1/sum(weight^2): 73 holdings concentrated
    in a few names are not 73 bets."""
    covered = [s for s in stocks if (s.get("market_risk") or {}).get("beta") is not None
               and s.get("weight_pct")]
    total_w = sum(s["weight_pct"] for s in covered)
    out = {"benchmark": BENCHMARK["name"],
           "beta_coverage_pct": round(total_w, 1),
           "holdings": len(stocks)}
    if total_w:
        out["portfolio_beta"] = round(
            sum(s["weight_pct"] * s["market_risk"]["beta"] for s in covered) / total_w, 2)
        out["beta_contributors"] = [
            {"ticker": s["ticker"], "beta": s["market_risk"]["beta"],
             "weight_pct": s["weight_pct"]}
            for s in sorted(covered, key=lambda s: -s["weight_pct"] * s["market_risk"]["beta"])[:3]]

    ret = [(s["weight_pct"], (s.get("technicals") or {}).get("return_1y_pct"))
           for s in stocks if s.get("weight_pct")]
    ret = [(w, r) for w, r in ret if r is not None]
    if ret and bench:
        w_sum = sum(w for w, _ in ret)
        out["return_1y_pct"] = round(sum(w * r for w, r in ret) / w_sum, 1)
        out["return_1y_coverage_pct"] = round(w_sum, 1)
        out["benchmark_return_1y_pct"] = bench.get("return_1y_pct")
        out["benchmark_max_drawdown_1y_pct"] = bench.get("max_drawdown_1y_pct")
        out["note_return"] = ("current weights applied to each holding's own 1-year price "
                              "return: it ignores when shares were actually bought")

    weights = [(s.get("weight_pct") or 0) / 100 for s in stocks]
    sq = sum(w * w for w in weights)
    if sq:
        out["effective_positions"] = round(1 / sq, 1)
    tail = [s for s in stocks if 0 < (s.get("weight_pct") or 0) < 0.5]
    out["positions_under_0_5_pct"] = len(tail)
    out["weight_in_those_pct"] = round(sum(s["weight_pct"] for s in tail), 1)
    out["top5_weight_pct"] = round(
        sum(sorted((s.get("weight_pct") or 0) for s in stocks)[-5:]), 1)
    return out


def money(v, dp=2):
    return "-" if v is None else f"{v:,.{dp}f}"


def evidence_flags(s):
    """Mechanical flags from the sections beyond the top ratios: cash
    conversion, the return trend, earnings against the company's own history,
    who is holding the stock, and what promoters have pledged or sold. Each one
    states what the data says, never what its absence might mean."""
    why = []
    cf = s.get("cash_flow") or {}
    if cf.get("applicable") and cf.get("cfo_weak"):
        years = cf["cfo_to_pat_years"]
        why.append(f"operating cash flow below profit over {years} years "
                   f"(CFO {cf['cfo_to_pat']:.2f}x PAT)" if cf["cfo_to_pat"] > 0 else
                   f"{years} years of profit with negative operating cash flow overall")
    if cf.get("applicable") and cf.get("years_cfo_negative", 0) >= 3:
        why.append(f"operating cash flow negative in {cf['years_cfo_negative']} of the last 5 years")
    rh = s.get("ratio_history") or {}
    if rh.get("roce_fading"):
        why.append(f"ROCE {rh['roce_latest']:.0f}% against a 5-year peak of {rh['roce_peak_5y']:.0f}%")
    if rh.get("debtor_days_stretching"):
        why.append(f"debtor days up to {rh['debtor_days_latest']:.0f} "
                   f"from a usual {rh['debtor_days_typical']:.0f}")
    gr = s.get("growth_ranges") or {}
    if gr.get("earnings_above_trend"):
        why.append(f"ROE {(gr.get('roe') or {}).get('last_year'):.0f}% last year against "
                   f"{gr['roe_trend_pct']:.0f}% over {gr['roe_trend_basis']} — check the P/E is "
                   f"not resting on peak earnings")
    sh = s.get("shareholding") or {}
    # Promoters rarely move at all, so two points is a real signal. Institutions
    # move constantly and often for reasons that have nothing to do with the
    # company, so their bar is higher and the flag is context, not a verdict.
    if (sh.get("promoters_change_pp") or 0) <= -2:
        why.append(f"promoter stake {sh['promoters_change_pp']:+.1f} pp ({sh['window']})")
    if (sh.get("fiis_change_pp") or 0) <= -8:
        why.append(f"FIIs {sh['fiis_change_pp']:+.1f} pp ({sh['window']})")
    why.extend(nse_disclosures.flags(s.get("nse")))
    return why


def write_portfolio_md(results, csv_name, full_refresh_at=None, risk=None):
    rows = []
    for s in results:
        note = read_stock_note(s["ticker"])
        rows.append((s, note))

    # Unreviewed and unclassified names sort last.
    rows.sort(key=lambda r: (r[0].get("signal_row") or 9,
                             -(r[0].get("pnl_pct_live") or r[0].get("pnl_pct") or 0)))

    total_inv = sum(s.get("invested") or 0 for s in results)
    total_cur = sum(s.get("current_value") or 0 for s in results)

    L = []
    L.append("# Portfolio Holdings & Notes\n")
    L.append("Long-term strategy: hold quality names, average down on genuinely "
             "undervalued opportunities.\n")
    L.append(f"*Generated {date.today().strftime('%d %B %Y')} from "
             f"`{csv_name}` — {len(results)} holdings.*\n")
    # Per-stock timestamps: a subset run refreshes some rows and carries the rest
    # over, so say plainly how old the oldest row on the table is.
    stamps = sorted(s["fetched_at"] for s in results if s.get("fetched_at"))
    if stamps:
        oldest = stamps[0].replace("T", " ")
        newest = stamps[-1].replace("T", " ")
        full = (full_refresh_at or "").replace("T", " ")
        L.append(f"*Prices fetched {oldest}"
                 + (f" — {newest}" if newest != oldest else "")
                 + (f". Last full refresh {full}.*\n" if full else ".*\n"))
    # A broker export with only Instrument and Qty. still builds a usable table,
    # so the money line must survive having no cost or value columns at all.
    if total_inv:
        L.append(f"**Invested ₹{total_inv:,.0f} · Current ₹{total_cur:,.0f} · "
                 f"P&L ₹{total_cur - total_inv:,.0f} "
                 f"({(total_cur - total_inv) / total_inv * 100:+.1f}%)**\n")
    else:
        L.append("*No cost or value columns in the holdings CSV, so there is no P&L line "
                 "and weights are unavailable.*\n")

    L.append("| Stock | Qty | Wt % | Avg cost | Price | P&L % | P/E | ROE | ROCE | Row | "
             "vs 200DMA | RSI | Rating | Last reviewed |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---|---|")
    for s, note in rows:
        wt = money(s.get("weight_pct"), 1)
        if s.get("fetch_error"):
            L.append(f"| {s['ticker']} | {money(s['qty'], 0)} | {wt} | {money(s['avg_cost'])} | "
                     f"- | - | - | - | - | ? | - | - | fetch failed | - |")
            continue
        pnl = s.get("pnl_pct_live")
        conf = s.get("classification", {}).get("confidence")
        row = s.get("signal_row")
        row_cell = "?" if row is None else (f"{row}?" if conf == "low" else str(row))
        t = s.get("technicals") or {}
        if t.get("pct_vs_dma200") is not None:
            dma_cell = f"{t['pct_vs_dma200']:+.0f}%"
        elif t.get("pct_vs_dma50") is not None:
            dma_cell = f"{t['pct_vs_dma50']:+.0f}%*"
        else:
            dma_cell = "—"
        rsi_cell = "—" if t.get("rsi14") is None else (
            f"{t['rsi14']:.0f}" + {"oversold": " ↓", "overbought": " ↑"}.get(t.get("rsi_note"), ""))
        L.append(
            f"| {s['ticker']} | {money(s['qty'], 0)} | {wt} | {money(s['avg_cost'])} | "
            f"{money(s['price'], 2)} | {'-' if pnl is None else format(pnl, '+.1f') + '%'} | "
            f"{'n/a' if s['pe'] is None else format(s['pe'], 'g')} | "
            f"{money(s['roe'], 1)} | {money(s['roce'], 1)} | {row_cell} | "
            f"{dma_cell} | {rsi_cell} | "
            f"{note.get('rating', '_not yet reviewed_')} | {note.get('last_analysis', '—')} |")

    L.append("\nSignal rows: **1** = low P/E + high ROE/ROCE (undervalued quality) · "
             "**2** = high P/E + high ROE/ROCE (great, pricey) · "
             "**3** = high P/E + low ROE/ROCE (caution) · "
             "**4** = low P/E + low ROE/ROCE (value trap). "
             "A trailing `?` means the ratios sat near a threshold — treat the row as "
             "provisional and re-check it by hand.\n")
    L.append("Technicals are context, not a rating: **vs 200DMA** is price against its "
             "200-day average (a `*` means too little listing history for a real 200DMA, "
             "so the 50DMA is shown instead), **RSI** is 14-day, `↓` below 30 = oversold, "
             "`↑` above 70 = overbought.\n")

    counts = {}
    for s in results:
        counts[s.get("signal_row")] = counts.get(s.get("signal_row"), 0) + 1
    L.append("## Distribution\n")
    for r in (1, 2, 3, 4, None):
        if counts.get(r):
            L.append(f"- Row {r or '?'}: {counts[r]} holdings — "
                     f"{ROW_TEXT.get(r, 'unclassified (missing ratios)')}")

    sectors = {}
    for s in results:
        name = s.get("sector_name") or "Unclassified"
        w, n = sectors.get(name, (0.0, 0))
        sectors[name] = (w + (s.get("weight_pct") or 0), n + 1)
    L.append("\n## Sector exposure\n")
    L.append("Share of current value, from the holdings CSV. Top ten.\n")
    for name, (w, n) in sorted(sectors.items(), key=lambda kv: -kv[1][0])[:10]:
        L.append(f"- {name}: {w:.1f}% ({n} holdings)")

    if risk:
        L.append("\n## Risk and concentration\n")
        if risk.get("portfolio_beta") is not None:
            L.append(f"- Beta vs {risk['benchmark']}: **{risk['portfolio_beta']:.2f}** "
                     f"(covering {risk['beta_coverage_pct']:.0f}% of the book by value)")
            contrib = ", ".join(f"{c['ticker']} {c['beta']:.2f} at {c['weight_pct']:.1f}%"
                                for c in risk.get("beta_contributors", []))
            if contrib:
                L.append(f"  - most of it from {contrib}")
        if risk.get("return_1y_pct") is not None:
            L.append(f"- 1-year price return at today's weights: "
                     f"**{risk['return_1y_pct']:+.1f}%** against "
                     f"{risk['benchmark_return_1y_pct']:+.1f}% for the index "
                     f"({risk['return_1y_coverage_pct']:.0f}% of the book covered). "
                     f"{risk['note_return']}.")
        if risk.get("effective_positions"):
            L.append(f"- {risk['holdings']} holdings, but an effective "
                     f"**{risk['effective_positions']:.0f}** positions once weights are counted "
                     f"(1/Σw²); the top 5 are {risk['top5_weight_pct']:.0f}% of the book")
        L.append(f"- {risk['positions_under_0_5_pct']} positions are under 0.5% of the book and "
                 f"{risk['weight_in_those_pct']:.1f}% of its value between them — too small for a "
                 f"change in any of them to matter")

    flags = []
    for s in results:
        if s.get("fetch_error"):
            continue
        t, why = s["ticker"], []
        if s.get("results_stale"):
            why.append(f"financials stale, latest quarter {s.get('latest_quarter_end')}")
        if s.get("pe") is None and s.get("roe") is not None and s["roe"] < 0:
            why.append("loss-making")
        if (s.get("pct_of_52wk_range") or 50) >= 90:
            why.append("near 52wk high")
        if (s.get("pct_of_52wk_range") or 50) <= 10:
            why.append("near 52wk low")
        if (s.get("pnl_pct_live") or 0) <= -30:
            why.append(f"down {abs(s['pnl_pct_live']):.0f}%")
        if (s.get("profit_yoy_pct") or 0) <= -40:
            why.append(f"profit {s['profit_yoy_pct']:+.0f}% YoY")
        oo = s.get("one_offs") or {}
        if (oo.get("latest") or {}).get("flag"):
            why.append("one-off in latest quarter (run-rate P/E flattered)")
        if (oo.get("year_ago") or {}).get("flag"):
            why.append("one-off in year-ago quarter (YoY not comparable)")
        if oo.get("other_income_heavy"):
            why.append(f"other income {oo['other_income_share_of_pbt_pct']:.0f}% of PBT")
        tech = s.get("technicals") or {}
        if tech.get("rsi_note") in ("oversold", "overbought"):
            why.append(f"RSI {tech['rsi14']:.0f} {tech['rsi_note']}")
        # Quality on sale: a row-1 business trading under its own long-term trend
        # is the setup the strategy is actually looking for.
        if s.get("signal_row") == 1 and (tech.get("pct_vs_dma200") or 0) < -5:
            why.append(f"row 1 but {tech['pct_vs_dma200']:+.0f}% vs 200DMA")
        why.extend(evidence_flags(s))
        if why:
            flags.append(f"- **{t}** — {', '.join(why)}")
    if flags:
        L.append("\n## Worth a look\n")
        L.append("Mechanical flags only, not ratings. Run `/portfolio-review <TICKER>` "
                 "to research any of these.\n")
        L.extend(sorted(flags))

    old = [(s["ticker"], note["missing"]) for s, note in rows if note.get("missing")]
    if old:
        L.append("\n## Notes on an old template\n")
        L.append("These `stocks/*.md` files lack fields the current template requires. "
                 "Re-review them with `/portfolio-review <TICKER>` before relying on them.\n")
        L.extend(f"- **{t}** — missing {', '.join(miss)}" for t, miss in sorted(old))

    L.append("\n---\n\n*Not investment advice — I'm not a financial advisor. "
             "Verify prices and figures before acting.*")

    path = os.path.join(ROOT, "PORTFOLIO.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def prune_cache():
    """The cache is keyed by date, so a file from an earlier day is never read
    again; at ~20 MB a day it would otherwise grow without bound. Yesterday is
    kept so close_on.py still has a chart for a ticker not yet fetched today.
    NSE files are the exception: pledge and shareholding move quarterly, so
    they are kept for a week and re-read rather than re-fetched."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cutoff = date.fromordinal(date.today().toordinal() - (CACHE_KEEP_DAYS - 1)).isoformat()
    nse_cutoff = date.fromordinal(
        date.today().toordinal() - (nse_disclosures.CACHE_DAYS - 1)).isoformat()
    removed = 0
    for path in glob.glob(os.path.join(CACHE_DIR, "*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.(?:html|json)$", path)
        if m and m.group(1) < (nse_cutoff if "-nse-" in os.path.basename(path) else cutoff):
            os.remove(path)
            removed += 1
    if removed:
        print(f"Pruned {removed} cache files older than {cutoff}\n")


def parse_args(argv):
    """`fetch_fundamentals.py [--refresh] [--screen] [--no-nse] [TICKER ...]`

    No tickers  -> full refresh of every holding, rebuilds the day's snapshot.
    Tickers     -> refresh just those and merge them into the day's snapshot.
    --screen    -> the tickers are candidates you don't hold: fetch and classify
                   them into data/screen-<today>.json, leaving the snapshot and
                   PORTFOLIO.md untouched.
    --refresh   -> ignore the per-day cache and re-fetch live, for when a price
                   has moved since the last run today.
    --no-nse    -> skip the NSE pledge/insider/SAST calls. They are cached for a
                   week, so only the first run of the week pays for them, but a
                   cold full run is three extra calls per holding."""
    force, screen, only, nse = False, False, [], True
    for a in argv:
        if a in ("--refresh", "-r"):
            force = True
        elif a == "--screen":
            screen = True
        elif a == "--no-nse":
            nse = False
        elif a.startswith("-"):
            sys.exit(f"Unknown option: {a}\n"
                     "Usage: fetch_fundamentals.py [--refresh] [--screen] [--no-nse] [TICKER ...]")
        else:
            only.append(a.upper())
    if screen and not only:
        sys.exit("--screen needs the candidate tickers to fetch.")
    return force, screen, only, nse


def run_screen(tickers, held, force, use_nse=True):
    """Classify stocks you don't own with the same rows and technicals as the
    holdings, so a "what else is worth buying" answer starts from the same
    evidence. Held tickers are skipped: they belong in the normal run."""
    held_set = {h["ticker"] for h in held}
    skipped = [t for t in tickers if t in held_set]
    if skipped:
        print(f"Already held, skipping (use the normal run): {', '.join(skipped)}\n")
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    prune_cache()
    stats = {"fetched": 0, "cached": 0, "chart_fetched": 0, "chart_cached": 0,
             "nse_fetched": 0, "nse_cached": 0}
    bench = fetch_benchmark(session, stats, force)
    nse_session = nse_disclosures._session() if use_nse else None
    results, failures = [], []
    todo = [t for t in tickers if t not in held_set]
    for i, t in enumerate(todo, 1):
        print(f"[{i:2}/{len(todo)}] {t:<12}", end=" ", flush=True)
        try:
            doc = fetch(t, session, stats, force)
            chart = fetch_chart(t, parse_company_id(doc), session, stats, force)
            rec = build({"ticker": t, "qty": 0, "avg_cost": 0, "ltp": None}, doc, chart,
                        bench=bench, nse=fetch_nse(t, nse_session, stats, use_nse))
            rec["fetched_at"] = datetime.now().isoformat(timespec="seconds")
            results.append(rec)
            pe = "n/a" if rec["pe"] is None else f"{rec['pe']:g}"
            oo = rec.get("one_offs") or {}
            print(f"P/E {pe:>6}  ROE {fmt(rec['roe'])}  ROCE {fmt(rec['roce'])}  "
                  f"-> row {rec['signal_row'] or '?'} ({rec['classification']['confidence']})  "
                  f"{trend_tag(rec.get('technicals') or {})}"
                  + ("  ONE-OFF latest" if (oo.get("latest") or {}).get("flag") else "")
                  + ("  ONE-OFF year-ago" if (oo.get("year_ago") or {}).get("flag") else ""))
        except Exception as exc:
            failures.append({"ticker": t, "error": str(exc)})
            print(f"FAILED: {exc}")
    out = os.path.join(DATA_DIR, f"screen-{date.today().isoformat()}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now().isoformat(timespec="seconds"),
                   "row_definitions": ROW_TEXT, "stocks": results, "failures": failures},
                  fh, indent=2, ensure_ascii=False)
    print(f"\nFetched {stats['fetched']}, from cache {stats['cached']}, failed {len(failures)}")
    print(f"Screen -> {os.path.relpath(out, ROOT)}  (snapshot and PORTFOLIO.md untouched)")


def fetch_benchmark(session, stats, force=False):
    """The Nifty series every beta is measured against, fetched and cached the
    same way a holding's chart is. Returns None rather than raising: without it
    the run simply carries no beta."""
    chart = fetch_chart(BENCHMARK["ticker"], BENCHMARK["company_id"], session, stats, force)
    dates, closes = chart_closes(chart)
    if len(closes) < 120:
        return None
    return {"dates": dates, "closes": closes,
            "return_1y_pct": pct_above(closes[-1], closes[0]),
            "max_drawdown_1y_pct": max_drawdown(closes),
            "as_of": dates[-1]}


def fetch_nse(ticker, session, stats, enabled):
    """Pledge, insider dealing and large-stake filings. Cached for a week, since
    these move quarterly, and never fatal: the fields say unavailable instead."""
    if not enabled:
        return None
    try:
        # Pass this project's cache dir: the module can be imported through a
        # symlink, in which case its own idea of ROOT is the skills repo.
        data = nse_disclosures.fetch(ticker, session, cache_dir=CACHE_DIR)
    except Exception as exc:                       # the module fails soft; this is the belt
        return {"available": False, "error": str(exc)[:120]}
    stats["nse_cached" if data.get("from_cache") else "nse_fetched"] += 1
    return data


def load_snapshot(path):
    """Today's snapshot, or None if there isn't one yet / it is unreadable."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            snap = json.load(fh)
    except (ValueError, OSError):
        return None
    return snap if isinstance(snap.get("stocks"), list) else None


def merge_stocks(base, fresh, held):
    """Fresh rows win; untouched rows carry over at their own `fetched_at`.

    Reconciled against the current holdings CSV so a subset run cannot leave a
    sold stock in PORTFOLIO.md, or invent one that was never fetched."""
    by_ticker = {s["ticker"]: s for s in base}
    for s in fresh:
        # A --no-nse run carries no disclosure block. Letting it overwrite the
        # one already in the snapshot would turn "not fetched this run" into
        # "nothing on file", which is the one reading these fields must never
        # support.
        if s.get("nse") is None:
            s["nse"] = (by_ticker.get(s["ticker"]) or {}).get("nse")
        by_ticker[s["ticker"]] = s
    order = [h["ticker"] for h in held]
    merged = [by_ticker[t] for t in order if t in by_ticker]
    missing = [t for t in order if t not in by_ticker]
    return merged, missing


def main():
    force, screen, only, use_nse = parse_args(sys.argv[1:])
    csv_path = latest_holdings_csv(required=not screen)
    held = read_holdings(csv_path) if csv_path else []
    if screen:
        run_screen(only, held, force, use_nse)
        return
    csv_date = holdings_date(csv_path)
    today = date.today().isoformat()
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, f"snapshot-{today}.json")
    base = load_snapshot(out)

    if only and base is None:
        print("No snapshot for today yet, so a subset run has nothing to merge "
              "into.\nPromoting to a full refresh so PORTFOLIO.md stays complete.\n")
        only = []

    if only:
        known = {h["ticker"] for h in held}
        unknown = [t for t in only if t not in known]
        if unknown:
            print(f"Not in {os.path.basename(csv_path)}, skipping: "
                  f"{', '.join(unknown)}\n")
        holdings = [h for h in held if h["ticker"] in only]
        if not holdings:
            sys.exit("Nothing to fetch.")
    else:
        holdings = held

    print(f"Holdings file : {os.path.basename(csv_path)}")
    print(f"Mode          : {'subset merge' if only else 'full refresh'}"
          f"{', cache bypassed' if force else ''}")
    if only and base.get("full_refresh_at"):
        print(f"Last full run : {base['full_refresh_at']}")
    print(f"Stocks to fetch: {len(holdings)}\n")

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    prune_cache()

    stats = {"fetched": 0, "cached": 0, "chart_fetched": 0, "chart_cached": 0,
             "nse_fetched": 0, "nse_cached": 0}
    bench = fetch_benchmark(session, stats, force)
    if not bench:
        print("Benchmark series unavailable, so this run carries no beta.\n")
    nse_session = nse_disclosures._session() if use_nse else None
    results, failures = [], []
    for i, h in enumerate(holdings, 1):
        t = h["ticker"]
        print(f"[{i:2}/{len(holdings)}] {t:<12}", end=" ", flush=True)
        try:
            doc = fetch(t, session, stats, force)
            chart = fetch_chart(t, parse_company_id(doc), session, stats, force)
            rec = build(h, doc, chart, csv_date, bench,
                        fetch_nse(t, nse_session, stats, use_nse))
            rec["fetched_at"] = datetime.now().isoformat(timespec="seconds")
            results.append(rec)
            row = rec["signal_row"]
            pe = "n/a" if rec["pe"] is None else f"{rec['pe']:g}"
            tech = rec.get("technicals") or {}
            print(f"P/E {pe:>6}  ROE {fmt(rec['roe'])}  ROCE {fmt(rec['roce'])}  "
                  f"-> row {row or '?'}  {trend_tag(tech)}")
        except Exception as exc:
            failures.append({"ticker": t, "error": str(exc)})
            rec = dict(h)
            rec["fetch_error"] = str(exc)
            rec["fetched_at"] = datetime.now().isoformat(timespec="seconds")
            results.append(rec)
            print(f"FAILED: {exc}")

    now = datetime.now().isoformat(timespec="seconds")
    if only:
        stocks, missing = merge_stocks(base["stocks"], results, held)
        full_refresh_at = base.get("full_refresh_at")
    else:
        stocks, missing = merge_stocks([], results, held)
        full_refresh_at = now
    add_portfolio_context(stocks)
    risk = portfolio_risk(stocks, bench)

    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": now,
            "full_refresh_at": full_refresh_at,
            "holdings_file": os.path.basename(csv_path),
            "holdings_date": csv_date,
            "row_definitions": ROW_TEXT,
            "portfolio_risk": risk,
            "stocks": stocks,
        }, fh, indent=2, ensure_ascii=False)

    no_tech = [s["ticker"] for s in results
               if not s.get("fetch_error") and not s.get("technicals")]
    print(f"\nFetched {stats['fetched']}, from cache {stats['cached']}, failed {len(failures)}")
    print(f"Charts fetched {stats['chart_fetched']}, from cache {stats['chart_cached']}"
          + (f", no technicals for {len(no_tech)}: {', '.join(no_tech)}" if no_tech else ""))
    if use_nse:
        print(f"NSE disclosures fetched {stats['nse_fetched']}, from cache "
              f"{stats['nse_cached']} (cached {nse_disclosures.CACHE_DAYS} days)")
    else:
        print("NSE disclosures skipped (--no-nse): no pledge or insider data this run")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  {f['ticker']}: {f['error']}")
    if missing:
        print(f"Held but never fetched today ({len(missing)}), so absent from "
              f"PORTFOLIO.md: {', '.join(missing)}")
        print("  Run with no arguments to fill them in.")
    stale = [s["ticker"] for s in results if s.get("results_stale")]
    if stale:
        print(f"Latest quarter over {STALE_QUARTER_DAYS} days old on screener "
              f"(check the exchange filing): {', '.join(stale)}")
    if only:
        print(f"Merged {len(results)} into {len(stocks)} holdings "
              f"(last full run {full_refresh_at or 'unknown'})")
    print(f"Snapshot  -> {os.path.relpath(out, ROOT)}")
    portfolio = write_portfolio_md(stocks, os.path.basename(csv_path), full_refresh_at, risk)
    print(f"Portfolio -> {os.path.relpath(portfolio, ROOT)}")


def fmt(v):
    return "  n/a" if v is None else f"{v:5.1f}"


def trend_tag(tech):
    """One-glance technical read for the console and the table."""
    if not tech:
        return ""
    if tech.get("dma200_reliable") and tech.get("pct_vs_dma200") is not None:
        arrow = "^" if tech["pct_vs_dma200"] >= 0 else "v"
        base = f"{arrow}200DMA {tech['pct_vs_dma200']:+.0f}%"
    elif tech.get("pct_vs_dma50") is not None:
        base = f"~50DMA {tech['pct_vs_dma50']:+.0f}%"
    else:
        return ""
    note = tech.get("rsi_note")
    if note in ("overbought", "oversold"):
        base += f" RSI {tech['rsi14']:.0f} {note}"
    return base


if __name__ == "__main__":
    main()
