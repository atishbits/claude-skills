#!/usr/bin/env python3
"""Mechanical multibagger pre-filter: narrow a whole-index scan (or the
user's own holdings) down to the stocks worth spending research effort on,
before any judgment call is made.

Reads a `screen-*.json` (default) or `snapshot-*.json` file already on disk
under `data/skill-data/` -- this script never fetches anything itself, that
is `nse_index.py` / `fetch_fundamentals.py`'s job -- and applies five fixed
pass/fail checks (ROCE quality, profit growth, PE-vs-growth, leverage,
cash conversion) plus an independent "near a local low" boolean to every
stock record. A stock that passes all five checks AND is near a local low is
a "survivor"; a stock that fails exactly one of the four margin-eligible
checks by 10% or less is "borderline" -- worth a future re-look once its
numbers move a little. Everything else is a clear fail and is only counted,
not printed individually, to keep a large scan's output readable.

    python3 scripts/multibagger_screen.py [--source screen|snapshot] [TICKER ...]
        [--roce-min 18.0] [--profit-growth-min 15.0] [--pe-growth-multiple 2.5]
        [--cfo-to-pat-min 0.6] [--pct52-max 20.0] [--pct200dma-max 0.0]

Writes `data/skill-data/multibagger-shortlist-<today>.json` with every
screened stock's verdict and a mechanical one-line `reason` (not just
survivors), so `scan_history.py record-shortlist FILE` can log the full
record in one call.

Before screening, prints a (non-fatal) warning if the source file is an
incomplete `--scan` (scan_meta.complete is False) or lists tickers that
failed to fetch -- either way the universe being screened is partial.
"""
import argparse
import glob
import json
import os
import sys
from datetime import date, datetime

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")

DEFAULT_THRESHOLDS = {
    "roce_min": 18.0,
    "profit_growth_min": 15.0,
    "pe_growth_multiple": 2.5,
    "cfo_to_pat_min": 0.6,
    "pct52_max": 20.0,
    "pct200dma_max": 0.0,
}

# The four checks whose margin can put a stock into "borderline". Leverage
# (check 4 in the plan) is deliberately excluded -- it is boolean-only and
# never borderline-eligible.
BORDERLINE_ELIGIBLE = ("roce", "growth", "pe_growth", "cash_conversion")


def _get(record, path):
    """Dotted-path lookup into a possibly-nested stock record. Returns None
    for any missing key or non-dict intermediate, instead of raising --
    every field this script reads may legitimately be absent."""
    node = record
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def profit_growth(record):
    """max of 5y/3y profit growth, ignoring whichever is None; None if both
    are missing."""
    values = [v for v in (
        _get(record, "growth_ranges.profit_growth.5_years"),
        _get(record, "growth_ranges.profit_growth.3_years"),
    ) if v is not None]
    return max(values) if values else None


def check_roce(record, thresholds):
    """Check 1. Fails if ROCE is fading, missing, or below the floor. Only
    the plain "below the floor" case gets a margin -- fading/missing are
    never borderline-eligible."""
    roce_fading = bool(_get(record, "ratio_history.roce_fading"))
    roce = _get(record, "roce")
    if roce_fading:
        return {"passed": False, "margin": None, "why": "fading"}
    if roce is None:
        return {"passed": False, "margin": None, "why": "missing"}
    if roce < thresholds["roce_min"]:
        margin = (thresholds["roce_min"] - roce) / thresholds["roce_min"]
        return {"passed": False, "margin": margin}
    return {"passed": True, "margin": None}


def check_growth(record, thresholds, prof_growth):
    """Check 2. Fails if profit growth is missing or below the floor."""
    if prof_growth is None:
        return {"passed": False, "margin": None, "why": "missing"}
    if prof_growth < thresholds["profit_growth_min"]:
        margin = (thresholds["profit_growth_min"] - prof_growth) / thresholds["profit_growth_min"]
        return {"passed": False, "margin": margin}
    return {"passed": True, "margin": None}


def check_pe_growth(record, thresholds, prof_growth):
    """Check 3. pe_runrate takes priority over pe when present. Fails if
    either input is missing, growth is non-positive, or PE runs ahead of
    growth by more than the allowed multiple."""
    pe_runrate = _get(record, "pe_runrate")
    pe = _get(record, "pe")
    pe_use = pe_runrate if pe_runrate is not None else pe
    if pe_use is None:
        return {"passed": False, "margin": None, "why": "pe missing"}
    if prof_growth is None:
        return {"passed": False, "margin": None, "why": "growth missing"}
    if prof_growth <= 0:
        return {"passed": False, "margin": None, "why": "growth not positive"}
    allowed = thresholds["pe_growth_multiple"] * prof_growth
    if pe_use > allowed:
        margin = (pe_use - allowed) / allowed
        return {"passed": False, "margin": margin}
    return {"passed": True, "margin": None}


def check_leverage(record):
    """Check 4. Boolean only, never borderline-eligible. Fails only when
    leverage applies, is rising, AND ROCE is fading or below 15."""
    applicable = bool(_get(record, "leverage.applicable"))
    trend = _get(record, "leverage.trend")
    roce_fading = bool(_get(record, "ratio_history.roce_fading"))
    roce = _get(record, "roce")
    if applicable and trend == "rising" and (roce_fading or (roce is not None and roce < 15)):
        return {"passed": False, "margin": None, "why": "rising with weak roce"}
    return {"passed": True, "margin": None}


def check_cash_conversion(record, thresholds):
    """Check 5. A lender (cash_flow.applicable is exactly False) passes
    automatically. Otherwise fails if CFO/PAT is missing or below the
    floor."""
    if _get(record, "cash_flow.applicable") is False:
        return {"passed": True, "margin": None}
    cfo_to_pat = _get(record, "cash_flow.cfo_to_pat")
    if cfo_to_pat is None:
        return {"passed": False, "margin": None, "why": "missing"}
    if cfo_to_pat < thresholds["cfo_to_pat_min"]:
        margin = (thresholds["cfo_to_pat_min"] - cfo_to_pat) / thresholds["cfo_to_pat_min"]
        return {"passed": False, "margin": margin}
    return {"passed": True, "margin": None}


def classify_quality(record, thresholds):
    """Runs all five checks and returns (verdict, checks) where verdict is
    one of "pass"/"borderline"/"fail" and checks is a dict of the five
    per-check {"passed", "margin"} results, keyed by name. A failed check
    whose margin is None also carries a short "why" label (e.g. "fading",
    "missing") so describe_reason can name the cause without re-reading
    the record.

    Rule: all pass -> pass. Leverage fails -> fail, always (never
    borderline). Otherwise, exactly one of the four margin-eligible checks
    failing, with a margin <= 10%, -> borderline. Everything else -> fail.
    """
    growth = profit_growth(record)
    checks = {
        "roce": check_roce(record, thresholds),
        "growth": check_growth(record, thresholds, growth),
        "pe_growth": check_pe_growth(record, thresholds, growth),
        "leverage": check_leverage(record),
        "cash_conversion": check_cash_conversion(record, thresholds),
    }
    if all(c["passed"] for c in checks.values()):
        return "pass", checks
    if not checks["leverage"]["passed"]:
        return "fail", checks
    failing = [name for name in BORDERLINE_ELIGIBLE if not checks[name]["passed"]]
    if len(failing) == 1:
        margin = checks[failing[0]]["margin"]
        if margin is not None and margin <= 0.10:
            return "borderline", checks
    return "fail", checks


def is_near_local_low(record, thresholds):
    """Independent of the quality verdict: both the 52-week-range position
    and the 200-DMA gap must be present and within the caps."""
    pct52 = _get(record, "pct_of_52wk_range")
    pct200 = _get(record, "technicals.pct_vs_dma200")
    return (
        pct52 is not None and pct52 <= thresholds["pct52_max"]
        and pct200 is not None and pct200 <= thresholds["pct200dma_max"]
    )


def rsi_tag(rsi14):
    """Informational only -- never gates near_local_low or the verdict."""
    if rsi14 is not None and rsi14 <= 45:
        return "oversold"
    return "neutral/n/a"


CHECK_ORDER = ("roce", "growth", "pe_growth", "leverage", "cash_conversion")


def describe_check_failure(name, check):
    """One failed check as a short phrase: "roce short 8.9%", "pe_growth
    over by 12.0%" (PE runs ahead of growth, so the miss is an overshoot),
    or "roce fading" / "cash_conversion missing" when there is no margin."""
    margin = check.get("margin")
    if margin is not None:
        word = "over by" if name == "pe_growth" else "short"
        return f"{name} {word} {margin * 100:.1f}%"
    return f"{name} {check.get('why') or 'failed'}"


def describe_reason(verdict, checks, near_local_low):
    """Deterministic one-line reason for the shortlist and scan_history:
    "quality pass; near local low" for a pass, otherwise every failed check
    in CHECK_ORDER with its margin, "; "-joined, followed by the
    near-local-low state. Pure naming of already-computed results -- no
    judgment."""
    low = "near local low" if near_local_low else "not near a local low"
    if verdict == "pass":
        return f"quality pass; {low}"
    parts = [describe_check_failure(n, checks[n]) for n in CHECK_ORDER
             if n in checks and not checks[n]["passed"]]
    return "; ".join(parts + [low])


def screen_stock(record, thresholds):
    """One stock's full result: verdict, checks, near_local_low, a
    mechanical one-line reason (see describe_reason), and the key metrics
    the printed sections and shortlist file both need."""
    verdict, checks = classify_quality(record, thresholds)
    near_low = is_near_local_low(record, thresholds)
    rsi14 = _get(record, "technicals.rsi14")
    return {
        "ticker": _get(record, "ticker"),
        "quality_verdict": verdict,
        "near_local_low": near_low,
        "reason": describe_reason(verdict, checks, near_low),
        "checks": checks,
        "metrics": {
            "roce": _get(record, "roce"),
            "pe": _get(record, "pe"),
            "pe_runrate": _get(record, "pe_runrate"),
            "profit_growth": profit_growth(record),
            "pct_of_52wk_range": _get(record, "pct_of_52wk_range"),
            "pct_vs_dma200": _get(record, "technicals.pct_vs_dma200"),
            "rsi14": rsi14,
            "rsi_tag": rsi_tag(rsi14),
        },
    }


def find_source_file(source, data_dir=None):
    """Newest screen-*.json or snapshot-*.json in data_dir, glob-sorted --
    same convention as rating_ledger.latest_snapshot_prices. None if there
    is no match."""
    data_dir = data_dir or DATA_DIR
    pattern = "screen-*.json" if source == "screen" else "snapshot-*.json"
    files = sorted(glob.glob(os.path.join(data_dir, pattern)))
    return files[-1] if files else None


def format_metric(value, fmt="{:.1f}"):
    return fmt.format(value) if value is not None else "n/a"


def format_survivor_line(result):
    m = result["metrics"]
    pe_str = format_metric(m["pe_runrate"]) if m["pe_runrate"] is not None else format_metric(m["pe"])
    return (
        f"{result['ticker']:<12} ROCE {format_metric(m['roce'])}  PE {pe_str}  "
        f"growth {format_metric(m['profit_growth'])}  pct52 {format_metric(m['pct_of_52wk_range'])}  "
        f"vs200dma {format_metric(m['pct_vs_dma200'])}  RSI {m['rsi_tag']}"
    )


def format_borderline_line(result):
    failing = [name for name in BORDERLINE_ELIGIBLE if not result["checks"][name]["passed"]]
    detail = describe_check_failure(failing[0], result["checks"][failing[0]]) if failing else "n/a"
    return f"{result['ticker']:<12} {detail}  near_local_low={result['near_local_low']}"


def build_shortlist(results, source_file, thresholds):
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": os.path.basename(source_file),
        "thresholds": thresholds,
        "screened": len(results),
        "stocks": results,
    }


def screen_all(stocks, tickers, thresholds):
    """Pure: takes the raw stock records already loaded from a source file
    and an optional ticker filter, returns the list of screen_stock results
    in source order."""
    if tickers:
        wanted = {t.strip().upper() for t in tickers}
        stocks = [s for s in stocks if (s.get("ticker") or "").strip().upper() in wanted]
    return [screen_stock(s, thresholds) for s in stocks]


def source_warnings(data):
    """Non-fatal warnings about the source file itself, as printable lines:
    a --scan file whose scan_meta.complete is False (an interrupted or
    still-running scan, so the universe is partial), and a non-empty
    top-level "failures" list (tickers that failed to fetch and so are not
    in "stocks" at all). Returns [] for a complete, failure-free file, or
    one carrying neither key (e.g. a snapshot)."""
    warnings = []
    meta = data.get("scan_meta")
    if isinstance(meta, dict) and meta.get("complete") is False:
        fetched = meta.get("fetched_so_far")
        total = meta.get("total_constituents")
        skipped = meta.get("already_held_skipped")
        if isinstance(total, int) and isinstance(skipped, int):
            total -= skipped  # held tickers are never fetched in a scan
        progress = (f" ({fetched}/{total} constituents fetched so far)"
                    if fetched is not None and total is not None else "")
        index = f" of {meta['index']}" if meta.get("index") else ""
        warnings.append(f"Warning: this scan{index} is incomplete{progress} -- "
                        "results may be a partial universe.")
    failures = data.get("failures")
    if isinstance(failures, list) and failures:
        names = [f.get("ticker") if isinstance(f, dict) else str(f) for f in failures]
        names = [n for n in names if n]
        warnings.append(f"Warning: {len(failures)} tickers failed to fetch and are excluded "
                        f"from this screen: {', '.join(names)}")
    return warnings


def print_report(results):
    counts = {"pass": 0, "borderline": 0, "fail": 0}
    for r in results:
        counts[r["quality_verdict"]] += 1
    print(f"Screened: {len(results)}")
    print(f"Passed: {counts['pass']}  Borderline: {counts['borderline']}  Failed: {counts['fail']}")
    print()

    survivors = [r for r in results if r["quality_verdict"] == "pass" and r["near_local_low"]]
    survivors.sort(key=lambda r: (r["metrics"]["pct_of_52wk_range"] is None, r["metrics"]["pct_of_52wk_range"]))
    print("--- survivors (pass + near local low) ---")
    if not survivors:
        print("(none)")
    for r in survivors:
        print(format_survivor_line(r))
    print()

    borderline = [r for r in results if r["quality_verdict"] == "borderline"]
    print("--- borderline (near-miss, worth a future re-look) ---")
    if not borderline:
        print("(none)")
    for r in borderline:
        print(format_borderline_line(r))


def cmd_screen(args):
    thresholds = {
        "roce_min": args.roce_min,
        "profit_growth_min": args.profit_growth_min,
        "pe_growth_multiple": args.pe_growth_multiple,
        "cfo_to_pat_min": args.cfo_to_pat_min,
        "pct52_max": args.pct52_max,
        "pct200dma_max": args.pct200dma_max,
    }
    source_file = find_source_file(args.source)
    if not source_file:
        pattern = "screen-*.json" if args.source == "screen" else "snapshot-*.json"
        sys.exit(f"No {pattern} file found in {DATA_DIR} -- run nse_index.py / fetch_fundamentals.py first.")

    with open(source_file, encoding="utf-8") as fh:
        data = json.load(fh)
    stocks = data.get("stocks", [])

    warnings = source_warnings(data)
    for warning in warnings:
        print(warning)
    if warnings:
        print()

    results = screen_all(stocks, args.tickers, thresholds)
    print_report(results)

    shortlist = build_shortlist(results, source_file, thresholds)
    out_path = os.path.join(DATA_DIR, f"multibagger-shortlist-{date.today().isoformat()}.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(shortlist, fh, indent=2)
    print(f"\nWrote {out_path}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*", metavar="TICKER",
                    help="restrict the run to these tickers (default: every stock in the source file)")
    p.add_argument("--source", choices=("screen", "snapshot"), default="screen",
                    help="read the newest screen-*.json (default) or snapshot-*.json")
    p.add_argument("--roce-min", type=float, default=DEFAULT_THRESHOLDS["roce_min"])
    p.add_argument("--profit-growth-min", type=float, default=DEFAULT_THRESHOLDS["profit_growth_min"])
    p.add_argument("--pe-growth-multiple", type=float, default=DEFAULT_THRESHOLDS["pe_growth_multiple"])
    p.add_argument("--cfo-to-pat-min", type=float, default=DEFAULT_THRESHOLDS["cfo_to_pat_min"])
    p.add_argument("--pct52-max", type=float, default=DEFAULT_THRESHOLDS["pct52_max"])
    p.add_argument("--pct200dma-max", type=float, default=DEFAULT_THRESHOLDS["pct200dma_max"])
    args = p.parse_args()
    cmd_screen(args)


if __name__ == "__main__":
    main()
