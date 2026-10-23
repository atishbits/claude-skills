"""Sell-side signals: how much of a recent rise is P/E stretch, peak tests, case tier.

Works on plain snapshot stock dicts; deliberately does not import fetch_fundamentals.
Missing or None fields are treated as unknown and never raise.
"""
import math
import re
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


# ---------------------------------------------------------------- sell plan
import argparse
import json
import os

import freshness
import tax_lots

STEP2_OFF_PEAK_PCT = 12.0
TRIM_FRACTION = {"trim_third": 1 / 3, "trim_half": 0.5}
CORE_FRACTION = {"weak": 0.0, "machine": 0.5, "ordinary": 1 / 3}
NEAR_LT_DAYS = 60
PLANS_PATH = os.path.join(tax_lots.SKILL_DATA_DIR, "sell-plans.json")
NO_LOG_NOTE = "no gains log yet — assuming the full exemption is unused"


def trim_plan(qty, tier, kind, full_exit=False):
    """Split a position into step 1 (sell now), step 2 (sell on a trigger) and a
    core held on. Floored; the three always add up to qty."""
    qty = int(qty)
    if full_exit:
        step1 = qty // 2
        return {"step1_qty": step1, "step2_qty": qty - step1, "core_qty": 0}
    if tier not in TRIM_FRACTION:
        return {"step1_qty": 0, "step2_qty": 0, "core_qty": qty}
    core = int(math.floor(qty * CORE_FRACTION.get(kind, CORE_FRACTION["ordinary"]) + 1e-9))
    step1 = min(int(math.floor(qty * TRIM_FRACTION[tier] + 1e-9)), qty - core)
    return {"step1_qty": step1, "step2_qty": qty - step1 - core, "core_qty": core}


def step2_triggers(price, technicals):
    technicals = technicals or {}
    high = technicals.get("recent_high_60d")
    peak = max(price, high) if high is not None else price
    return {"off_peak_price": peak * (1 - STEP2_OFF_PEAK_PCT / 100),
            "dma50": technicals.get("dma50"), "peak": peak}


def _default_stocks_dir():
    return os.path.join(tax_lots.SKILL_DATA_DIR, "stocks")


def consensus_avg(ticker, stocks_dir=None, today=None):
    """Average target price from the note's Research block, only if fresh."""
    path = os.path.join(stocks_dir or _default_stocks_dir(), f"{ticker.upper()}.md")
    try:
        with open(path, encoding="utf-8") as fh:
            research = freshness.parse_research(fh.read())
    except OSError:
        return None
    item = research.get("consensus")
    if not item:
        return None
    age = ((today or date.today()) - date.fromisoformat(item["as_of"])).days
    if age > freshness.WINDOW_DAYS["consensus"]:
        return None
    m = re.search(r"avg TP\s*₹\s*([\d,]+(?:\.\d+)?)", item["value"])
    return float(m.group(1).replace(",", "")) if m else None


def load_plans(path=None):
    try:
        with open(path or PLANS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _write_plans(plans, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plans, fh, indent=2, sort_keys=True)
        fh.write("\n")


def save_plan(ticker, plan, path=None):
    path = path or PLANS_PATH
    plans = load_plans(path)
    plans[ticker.upper()] = plan
    _write_plans(plans, path)


def close_plan(ticker, path=None):
    path = path or PLANS_PATH
    plans = load_plans(path)
    removed = plans.pop(ticker.upper(), None)
    _write_plans(plans, path)
    return removed


def _gains_log():
    """Task 5's module, or None until it exists. The one place the log is touched."""
    try:
        import gains_log
        return gains_log
    except ImportError:
        return None


def _fy_label(today):
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def lt_headroom(today, snapshot=None, log_dir=None):
    """(unused LTCG exemption this FY, note or None)."""
    gl = _gains_log()
    if gl is None:
        return float(tax_lots.LTCG_EXEMPTION_PER_FY), NO_LOG_NOTE
    run = gl.fy_running(_fy_label(today), snapshot=snapshot, log_dir=log_dir)
    return float(run["fy_tax"]["exempt_left"]), None


def sold_since(ticker, opened, log_dir=None):
    """Quantity of `ticker` sold in the gains log on or after `opened` (ISO
    date); None if no log. `log_dir` defaults to the gains log's own folder."""
    gl = _gains_log()
    if gl is None:
        return None
    total = 0.0
    for e in gl.fold(gl.read_entries(log_dir)):
        if e.get("ticker") == ticker.upper() and e.get("sell_date", "") >= opened:
            total += e.get("qty") or 0
    return total


def advice(tier, days_to_lt_list, breakeven, max_drawdown_1y_pct):
    near = any(d is not None and d <= NEAR_LT_DAYS for d in days_to_lt_list)
    if near and tier == "watch":
        return "wait for that lot: it turns long-term within 60 days"
    if breakeven is None:
        return "no short-term lot in step 1: nothing to wait for"
    dd = abs(max_drawdown_1y_pct or 0)
    if breakeven < dd / 2:
        return "trim now: a typical pullback is larger than the tax saved"
    return (f"close call: waiting saves tax only if the price stays above "
            f"{breakeven:.1f}% below today; a typical pullback is {dd:.0f}%")


def _stock(snap, ticker):
    for s in snap.get("stocks", []):
        if s.get("ticker") == ticker:
            return s
    return None


def _account_split(stock):
    brokers = stock.get("brokers") or {}
    return sorted(brokers.items()) if brokers else [(None, stock.get("qty") or 0)]


def _logged_since(ticker, broker, snap):
    """Units of `ticker` logged as sold from `broker` after its export; 0 without a log."""
    gl = _gains_log()
    if gl is None or broker is None:
        return 0.0
    return float(gl.logged_since_export(ticker, broker, snapshot=snap))


def _report(stock, ev, today, plan, snap=None):
    ticker, price = stock["ticker"], stock["price"]
    tech = stock.get("technicals") or {}
    print(flag_text(ticker, ev) or f"{ticker}: no sell case (tier none)")
    print(f"tier {ev['tier']}, kind {ev['kind']}, tests {ev['tests']}")
    accounts = [(b, bq, _logged_since(ticker, b, snap)) for b, bq in _account_split(stock)]
    gone = sum(g for _, _, g in accounts)
    qty = max(0.0, (stock.get("qty") or 0) - gone)
    if gone:
        print(f"{gone:g} share(s) logged as sold since the export; {qty:g} left")
    tp = ({k: plan[k] for k in ("step1_qty", "step2_qty", "core_qty")} if plan
          else trim_plan(qty, ev["tier"], ev["kind"]))
    trig = step2_triggers(price, tech)
    print(f"plan: step 1 {tp['step1_qty']}, step 2 {tp['step2_qty']}, core {tp['core_qty']}; "
          f"step 2 on close below {trig['off_peak_price']:.2f} (peak {trig['peak']:.2f})"
          + (f" or 50DMA {trig['dma50']:.2f}" if trig["dma50"] else ""))
    headroom, note = lt_headroom(today, snapshot=snap)
    if note:
        print(note)
    step1 = tp["step1_qty"]
    label = "if sold from"
    if plan:
        done = sold_since(ticker, plan["opened"]) or 0
        step1 = max(0, tp["step1_qty"] - done)
        if step1 <= 0:
            step1 = max(0, tp["step2_qty"] - max(0, done - tp["step1_qty"]))
            label = "step 2: if sold from"
    if step1 <= 0:
        step1 = trim_plan(qty, "trim_third", ev["kind"])["step1_qty"]
        label = "preview: if you trimmed a third, if sold from"
    for broker, bq, since in accounts:
        left = max(0.0, bq - since)
        n = min(step1, left)
        name = broker or "(single)"
        after = f", {since:g} logged since the export" if since else ""
        print(f"-- {label} {name} (holds {left:g}{after}): {n:g} share(s)")
        if n <= 0:
            continue
        try:
            matched = tax_lots.fifo_match(stock.get("lots") or [], n, broker, already_sold=since,
                                          fallback_cost=stock.get("avg_cost"))
        except ValueError as exc:
            print(f"   cannot match lots: {exc}")
            continue
        days, gain_sum, tax_sum, net_sum, untaxed = [], 0.0, 0.0, 0.0, 0.0
        for m in matched:
            st = tax_lots.lot_status(m, price, today, NEAR_LT_DAYS, stock.get("avg_cost"))
            if not m["taxable"] or m["cost"] is None or st is None:
                print(f"   {m['date']}: {m['qty']:g} sh - tax not estimated")
                untaxed += m["qty"]
                continue
            tax = tax_lots.sale_tax([m], price, today)["est_tax"]
            term = "LT" if st["is_lt"] else f"ST ({st['days_to_lt']}d to LT)"
            if not st["is_lt"]:
                days.append(st["days_to_lt"])
            net = m["qty"] * price - tax
            gain_sum, tax_sum, net_sum = gain_sum + st["gain"], tax_sum + tax, net_sum + net
            print(f"   {m['date']}: {m['qty']:g} sh gain ₹{st['gain']:,.0f} {term} "
                  f"tax ₹{tax:,.0f} net ₹{net:,.0f}")
        print(f"   total: gain ₹{gain_sum:,.0f}, est. tax ₹{tax_sum:,.0f}, net ₹{net_sum:,.0f}")
        if untaxed > 0:
            print(f"   {untaxed:g} shares tax not estimated (pre-2018/undated), excluded")
        be = tax_lots.breakeven_drop_pct(matched, price, today, headroom)
        print("   " + (f"break-even drop {be:.1f}%; " if be is not None else "")
              + advice(ev["tier"], days, be, tech.get("max_drawdown_1y_pct")))
    if plan:
        sold = sold_since(ticker, plan["opened"])
        done = "unknown (no gains log yet)" if sold is None else f"{sold:g} sold since {plan['opened']}"
        print(f"open plan from {plan['opened']}: \"{plan['deciding_sentence']}\" "
              f"step1 {plan['step1_qty']}, step2 {plan['step2_qty']}, core {plan['core_qty']}; "
              f"steps done: {done}")


def main(argv=None, today=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticker", nargs="?")
    ap.add_argument("--open-plan", metavar="SENTENCE", help="save a sell plan with this deciding sentence")
    ap.add_argument("--full-exit", action="store_true", help="with --open-plan: half now, rest on trigger, no core")
    ap.add_argument("--close-plan", action="store_true")
    ap.add_argument("--flags", action="store_true", help="one line per held stock with a sell case")
    args = ap.parse_args(argv)
    snap, _ = tax_lots.latest_snapshot()
    today = today or date.today()
    if args.flags:
        for s in snap.get("stocks", []):
            line = flag_text(s["ticker"], evaluate(s, today, consensus_avg(s["ticker"], today=today)))
            if line:
                print(line)
        return
    if not args.ticker:
        ap.error("a ticker is required unless --flags is given")
    ticker = args.ticker.upper()
    if args.close_plan:
        print(f"closed plan for {ticker}" if close_plan(ticker) else f"no open plan for {ticker}")
        return
    stock = _stock(snap, ticker)
    if not stock:
        raise SystemExit(f"{ticker} is not in the newest snapshot.")
    ev = evaluate(stock, today, consensus_avg(ticker, today=today))
    if args.open_plan:
        existing = load_plans().get(ticker)
        if existing:
            raise SystemExit(f"{ticker} already has an open plan ({existing['deciding_sentence']!r}, "
                             f"opened {existing['opened']}); run --close-plan first.")
        if ev["tier"] in ("none", "watch") and not args.full_exit:
            raise SystemExit(f"{ticker} is tier {ev['tier']}: step 1 would be 0, no plan opened "
                             f"(use --full-exit for a deliberate exit).")
        tp = trim_plan(stock.get("qty") or 0, ev["tier"], ev["kind"], args.full_exit)
        trig = step2_triggers(stock["price"], stock.get("technicals"))
        save_plan(ticker, {"opened": today.isoformat(), "deciding_sentence": args.open_plan,
                           "qty_at_open": stock.get("qty"), "tier": ev["tier"], "kind": ev["kind"],
                           **tp, "triggers": trig,
                           "core_ends_on": None})
        print(f"saved plan for {ticker}: {tp}")
        return
    _report(stock, ev, today, load_plans().get(ticker), snap)


if __name__ == "__main__":
    main()
