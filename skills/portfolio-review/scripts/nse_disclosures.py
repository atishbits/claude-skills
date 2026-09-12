#!/usr/bin/env python3
"""Promoter pledge, insider deals and large-stake (SAST) filings from NSE.

Screener carries none of these, and they are the evidence that separates a
genuinely cheap stock from one the people who know it best are leaving. Three
NSE endpoints answer without a login or cookie priming:

    /api/corporate-pledgedata      shares pledged by promoters
    /api/corporates-pit            insider / promoter dealing (PIT regulations)
    /api/corporate-sast-reg29      large-stake acquisitions and sales

None of this is documented or supported, so every call here fails soft: a
missing answer is recorded as unavailable and never as "no pledge" or "no
insider selling". Coverage is genuinely patchy too -- as of Sep 2026 the PIT
endpoint was current for BAJFINANCE and INFY but had nothing after 2022 for
TCS and nothing at all for PAYTM -- so each block carries the date of the
latest filing it actually saw, and goes `stale` rather than silent when that
date is old.

Pledge and shareholding move quarterly, so the cache here is a week, not a day.
"""

import glob
import json
import os
import re
import time
from datetime import date, datetime, timedelta

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", ".cache")
CACHE_DAYS = 7
WINDOW_DAYS = 365          # how far back a dealing counts as recent
STALE_AFTER_DAYS = 270     # newest filing older than this: treat coverage as unusable
REQUEST_DELAY = 1.0
BASE = "https://www.nseindia.com/api"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

PROMOTER_WORDS = ("promoter",)


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*",
                      "Accept-Language": "en-US,en;q=0.9"})
    return s


def _num(v):
    if v is None:
        return None
    v = re.sub(r"[,\s%]", "", str(v))
    try:
        return float(v)
    except ValueError:
        return None


def _date(v, *fmts):
    if not v or str(v).strip() in ("-", ""):
        return None
    for f in fmts or ("%d-%b-%Y", "%d-%m-%Y", "%d-%b-%Y %H:%M", "%d-%B-%Y"):
        try:
            return datetime.strptime(str(v).strip().split(",")[0], f).date()
        except ValueError:
            continue
    return None


def _get(session, path, params):
    url = f"{BASE}/{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    r = session.get(url, timeout=25)
    time.sleep(REQUEST_DELAY)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


# ------------------------------------------------------------------ summaries

def pledge_summary(payload):
    rows = (payload or {}).get("data") or []
    if not rows:
        return {"available": True, "pledged": False,
                "note": "no pledge disclosure on file"}
    rows = sorted(rows, key=lambda r: _date(r.get("shp")) or date.min)
    r = rows[-1]
    # Two different numbers live in this payload and only one is the one that
    # matters. percSharesPledged counts every encumbered share in the company,
    # including pledges by public shareholders -- Whirlpool shows 2.32% there
    # with promoters having pledged nothing at all. The promoter figure is
    # percPromoterShares: promoter-pledged shares as a share of what promoters
    # hold. Deriving it by hand from numSharesPledged gives nonsense for a
    # company with almost no promoter holding (ITC came out at 8199%).
    promoter_pledge = _num(r.get("percPromoterShares"))
    return {
        "available": True,
        "pledged": bool(promoter_pledge),
        "as_of": str(r.get("shp") or "").strip() or None,
        "promoter_pledge_pct_of_promoter_holding": promoter_pledge,
        "promoter_pledged_shares": _num(r.get("totPromoterShares")),
        "encumbered_pct_of_all_shares": _num(r.get("percSharesPledged")),
        "promoter_holding_pct": _num(r.get("percPromoterHolding")),
    }


def _is_promoter(row, *fields):
    text = " ".join(str(row.get(f) or "") for f in fields).lower()
    return any(w in text for w in PROMOTER_WORDS)


def insider_summary(payload):
    """Net promoter and insider dealing over the last year, by value."""
    rows = (payload or {}).get("data") or []
    dated = []
    for r in rows:
        d = _date(r.get("acqfromDt")) or _date(r.get("intimDt"))
        if d:
            dated.append((d, r))
    if not dated:
        return {"available": True, "filings": 0, "stale": True,
                "note": "no insider filing found on this endpoint -- "
                        "absence here is not evidence of no dealing"}
    latest = max(d for d, _ in dated)
    cutoff = date.today() - timedelta(days=WINDOW_DAYS)
    recent = [(d, r) for d, r in dated if d >= cutoff]

    out = {"available": True, "filings": len(dated),
           "latest_filing": latest.isoformat(),
           "stale": (date.today() - latest).days > STALE_AFTER_DAYS,
           "window_days": WINDOW_DAYS, "filings_in_window": len(recent)}
    if out["stale"]:
        out["note"] = (f"newest filing {latest.isoformat()} -- coverage looks "
                       "incomplete, do not read this as no dealing")
        return out

    buy = sell = promoter_buy = promoter_sell = 0.0
    for d, r in recent:
        kind = str(r.get("tdpTransactionType") or "").lower()
        val = _num(r.get("secVal")) or 0.0
        promoter = _is_promoter(r, "personCategory")
        if kind.startswith("buy"):
            buy += val
            promoter_buy += val if promoter else 0.0
        elif kind.startswith("sell"):
            sell += val
            promoter_sell += val if promoter else 0.0
    cr = lambda v: round(v / 1e7, 2)  # rupees -> crore
    out.update({"buy_cr": cr(buy), "sell_cr": cr(sell),
                "promoter_buy_cr": cr(promoter_buy),
                "promoter_sell_cr": cr(promoter_sell),
                "net_cr": cr(buy - sell),
                "promoter_net_cr": cr(promoter_buy - promoter_sell)})
    return out


def sast_summary(payload):
    """Reg 29 filings: someone crossing a 5% stake, or moving 2% once above it."""
    rows = (payload or {}).get("data") or []
    cutoff = date.today() - timedelta(days=WINDOW_DAYS)
    recent = []
    for r in rows:
        d = _date(r.get("sysTime"), "%d-%b-%Y %H:%M") or _date(str(r.get("timestamp") or "").split(" ")[0])
        if not d or d < cutoff:
            continue
        recent.append({
            "date": d.isoformat(),
            "name": (r.get("acquirerName") or "").strip()[:60],
            "action": (r.get("acqSaleType") or "").strip(),
            "promoter": str(r.get("promoterType") or "").upper() == "Y",
        })
    recent.sort(key=lambda x: x["date"], reverse=True)
    return {"available": True, "filings_in_window": len(recent),
            "window_days": WINDOW_DAYS, "recent": recent[:5],
            "promoter_sales": [x for x in recent if x["promoter"] and x["action"].lower().startswith("sale")]}


# ---------------------------------------------------------------------- fetch

def _cache_path(ticker):
    return os.path.join(CACHE_DIR, f"{ticker}-nse-{date.today().isoformat()}.json")


def _cached(ticker):
    """Any NSE file for this ticker from the last CACHE_DAYS days."""
    newest, newest_day = None, None
    for path in glob.glob(os.path.join(CACHE_DIR, f"{ticker}-nse-*.json")):
        m = re.search(r"-nse-(\d{4}-\d{2}-\d{2})\.json$", path)
        if not m:
            continue
        day = date.fromisoformat(m.group(1))
        if (date.today() - day).days < CACHE_DAYS and (newest_day is None or day > newest_day):
            newest, newest_day = path, day
    if not newest:
        return None
    try:
        with open(newest, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return None


def fetch(ticker, session=None, force=False):
    """Pledge, insider and SAST for one symbol. Never raises: on failure the
    block says it is unavailable, which reads differently from "nothing found"."""
    if not force:
        hit = _cached(ticker)
        if hit is not None:
            hit["from_cache"] = True
            return hit

    session = session or _session()
    today = date.today()
    window = {"from_date": (today - timedelta(days=WINDOW_DAYS * 2)).strftime("%d-%m-%Y"),
              "to_date": today.strftime("%d-%m-%Y")}
    out = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "from_cache": False}

    for key, path, params, summarise in (
            ("pledge", "corporate-pledgedata",
             {"index": "equities", "symbol": ticker}, pledge_summary),
            ("insider", "corporates-pit",
             dict({"index": "equities", "symbol": ticker}, **window), insider_summary),
            ("sast", "corporate-sast-reg29",
             {"index": "equities", "symbol": ticker}, sast_summary)):
        try:
            out[key] = summarise(_get(session, path, params))
        except Exception as exc:                      # network, HTTP, or bad JSON
            out[key] = {"available": False, "error": str(exc)[:120]}

    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(ticker), "w", encoding="utf-8") as fh:
            json.dump(out, fh)
    except OSError:
        pass
    return out


# A flag has to be rare to be worth reading. A 1-2% promoter pledge and a
# routine Reg 29 filing are facts about almost every company, so they stay in
# the snapshot for a review to read and out of the "Worth a look" list.
PLEDGE_FLAG_PCT = 5
SAST_FLAG_DAYS = 180


def flags(nse):
    """Short strings for PORTFOLIO.md's 'Worth a look'. Only states what the
    data actually supports: silence is never turned into a clean bill."""
    if not nse:
        return []
    out = []
    p = nse.get("pledge") or {}
    pct = p.get("promoter_pledge_pct_of_promoter_holding")
    if p.get("available") and pct and pct >= PLEDGE_FLAG_PCT:
        out.append(f"promoters have pledged {pct:.0f}% of their holding ({p.get('as_of')})")
    i = nse.get("insider") or {}
    if i.get("available") and not i.get("stale") and i.get("promoter_sell_cr"):
        net = i.get("promoter_net_cr") or 0
        if net < -1:
            out.append(f"promoters net sellers ₹{abs(net):.0f} Cr in the last year")
    s = nse.get("sast") or {}
    cutoff = (date.today() - timedelta(days=SAST_FLAG_DAYS)).isoformat()
    for row in [r for r in (s.get("promoter_sales") or []) if r["date"] >= cutoff][:1]:
        out.append(f"promoter stake sale filed {row['date']} ({row['name']})")
    return out


if __name__ == "__main__":
    import sys
    for t in sys.argv[1:] or ["BAJFINANCE"]:
        print(t, json.dumps(fetch(t.upper(), force="--refresh" in sys.argv), indent=2))
        print("flags:", flags(fetch(t.upper())))
