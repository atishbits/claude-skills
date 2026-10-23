"""Sell-side signals: how much of a recent rise is P/E stretch, peak tests, case tier.

Works on plain snapshot stock dicts; deliberately does not import fetch_fundamentals.
Missing or None fields are treated as unknown and never raise.
"""
import math
from datetime import date, timedelta

STRETCH_MIN_RISE_PCT = 15.0   # a window's price rise must be at least this to count as stretched
STRETCH_PE_SHARE = 0.6        # ... and at least this share of it must come from P/E expansion
PE_PCT_HIGH = 80              # own-band percentile at or above this is "P/E high"
RESULT_LAG_DAYS = 45          # a quarter's profit is public about this long after period end
MACHINE_ROCE = 25.0
MACHINE_GROWTH_PCT = 15.0
TIERS = ("none", "watch", "trim_third", "trim_half")


def ttm_profit_asof(quarters, asof, lag_days=RESULT_LAG_DAYS):
    """Sum of the last 4 quarters already public on `asof`; None if <4 or sum <= 0."""
    try:
        ends = quarters["period_end"]
        profits = quarters["net_profit"]
        known = []
        for e, p in zip(ends, profits):
            if date.fromisoformat(e) + timedelta(days=lag_days) <= asof:
                known.append((e, p))
    except (TypeError, KeyError, ValueError):
        return None
    known.sort(key=lambda x: x[0])
    last = known[-4:]
    if len(last) < 4 or any(p is None for _, p in last):
        return None
    total = sum(p for _, p in last)
    return total if total > 0 else None


def rise_split(ret_pct, ttm_now, ttm_then):
    """Split a price rise into profit growth and P/E change: (1+price)=(1+eps)(1+pe)."""
    if ret_pct is None or ttm_now is None or ttm_then is None:
        return None
    if ret_pct <= 0 or ttm_then <= 0 or ttm_now <= 0:
        return None
    r_price = ret_pct / 100.0
    r_eps = ttm_now / ttm_then - 1.0
    r_pe = (1.0 + r_price) / (1.0 + r_eps) - 1.0
    share = math.log1p(r_pe) / math.log1p(r_price)
    share = max(0.0, min(1.0, share))
    return {"rise_pct": ret_pct, "eps_pct": r_eps * 100.0,
            "pe_pct": r_pe * 100.0, "pe_share": share}


def _percentile(stock):
    band = stock.get("own_pe_band")
    return band.get("percentile") if isinstance(band, dict) else None


def peak_tests(stock, consensus_avg):
    pct = _percentile(stock)
    pe_high = None if pct is None else pct >= PE_PCT_HIGH
    gr = stock.get("growth_ranges")
    eat = bool(gr.get("earnings_above_trend")) if isinstance(gr, dict) else False
    price = stock.get("price")
    above = None if consensus_avg is None or price is None else price > consensus_avg
    count = sum(1 for v in (pe_high, eat, above) if v is True)
    return {"pe_high": pe_high, "earnings_above_trend": eat,
            "above_consensus": above, "count": count}


def business_kind(stock):
    rh = stock.get("ratio_history")
    fading = bool(rh.get("roce_fading")) if isinstance(rh, dict) else False
    if stock.get("signal_row") in (3, 4) or fading:
        return "weak"
    gr = stock.get("growth_ranges")
    pg = gr.get("profit_growth") if isinstance(gr, dict) else None
    cagr = pg.get("5_years") if isinstance(pg, dict) else None
    roce = stock.get("roce")
    if roce is not None and cagr is not None and roce >= MACHINE_ROCE and cagr >= MACHINE_GROWTH_PCT:
        return "machine"
    return "ordinary"


def _stretched(split):
    return bool(split) and split["rise_pct"] >= STRETCH_MIN_RISE_PCT \
        and split["pe_share"] >= STRETCH_PE_SHARE


def case_tier(split, tests, kind):
    stretched = _stretched(split)
    if not stretched and tests["count"] == 0:
        return "none"
    strong = (stretched and bool(tests["pe_high"])) or tests["count"] >= 2
    if not strong:
        return "watch"
    return "trim_half" if kind == "weak" else "trim_third"


def evaluate(stock, today, consensus_avg=None):
    q = stock.get("quarters")
    tech = stock.get("technicals") or {}
    now = ttm_profit_asof(q, today)
    split_3m = rise_split(tech.get("return_3m_pct"), now,
                          ttm_profit_asof(q, today - timedelta(days=91)))
    split_6m = rise_split(tech.get("return_6m_pct"), now,
                          ttm_profit_asof(q, today - timedelta(days=182)))
    window, chosen = None, None
    for name, sp in (("3m", split_3m), ("6m", split_6m)):
        if _stretched(sp) and (chosen is None or sp["pe_share"] > chosen["pe_share"]):
            window, chosen = name, sp
    tests = peak_tests(stock, consensus_avg)
    kind = business_kind(stock)
    band = stock.get("own_pe_band")
    return {"tier": case_tier(chosen, tests, kind), "kind": kind,
            "split_3m": split_3m, "split_6m": split_6m, "window": window,
            "tests": tests, "pe_percentile": _percentile(stock),
            "pe_years": band.get("years") if isinstance(band, dict) else None}


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def flag_text(ticker, ev):
    if ev.get("tier", "none") == "none":
        return None
    parts = []
    window = ev.get("window")
    split = ev.get("split_" + window) if window else None
    if split:
        eps = split["eps_pct"]
        profit = "profit flat" if abs(eps) < 2 else f"profit {eps:+.0f}%"
        parts.append(f"+{split['rise_pct']:.0f}% in {window}, "
                     f"~{split['pe_share'] * 100:.0f}% from P/E stretch ({profit})")
    tests = ev.get("tests") or {}
    pct = ev.get("pe_percentile")
    if tests.get("pe_high") and pct is not None:
        years = ev.get("pe_years")
        band = f"own {years}y band" if years else "own band"
        parts.append(f"P/E at {_ordinal(int(pct))} pct of {band}")
    if tests.get("earnings_above_trend"):
        parts.append("profit above trend")
    if tests.get("above_consensus"):
        parts.append("price above consensus target")
    tier = ev["tier"]
    verdict = "watch" if tier == "watch" else f"{tier} candidate"
    parts.append(f"{ev.get('kind', 'ordinary')} business - {verdict}")
    return f"{ticker}: " + "; ".join(parts)
