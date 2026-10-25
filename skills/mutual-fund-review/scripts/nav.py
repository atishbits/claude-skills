#!/usr/bin/env python3
"""Fund prices (NAVs): today's from AMFI's daily file, history from mfapi.in,
cached under data/skill-data/nav/. The only script in this skill that uses the
network, always through `fetch` so tests and offline runs can replace it.

    python3 scripts/nav.py latest ISIN... [--root R]
    python3 scripts/nav.py history AMFI_CODE [--root R]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import common

AMFI_NAVALL = "https://portal.amfiindia.com/spages/NAVAll.txt"
MFAPI = "https://api.mfapi.in/mf/{code}"
UA = "Mozilla/5.0 (mutual-fund-review skill)"


def default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_amfi_navall(text):
    """{amfi_code: {amfi_code, isins, scheme, nav, date}} found by column name,
    so a new or reordered column does not shift the values."""
    out, cols = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or ";" not in line:
            continue
        cells = [c.strip() for c in line.split(";")]
        if cells[0] == "Scheme Code":
            cols = {name: i for i, name in enumerate(cells)}
            continue
        if cols is None or not cells[0].isdigit():
            continue

        def get(name):
            i = cols.get(name)
            return cells[i] if i is not None and i < len(cells) else ""

        isins = [x for x in (get("ISIN Div Payout/ ISIN Growth"), get("ISIN Div Reinvestment"))
                 if x and x != "-"]
        try:
            date = common.parse_date(get("Date"))
        except ValueError:
            date = None
        out[cells[0]] = {"amfi_code": cells[0], "isins": isins, "scheme": get("Scheme Name"),
                         "nav": _float(get("Net Asset Value")), "date": date}
    return out


def isin_index(parsed):
    return {isin: code for code, row in parsed.items() for isin in row["isins"]}


def parse_history(doc):
    return {common.parse_date(r["date"]): float(r["nav"]) for r in doc.get("data", [])
            if _float(r.get("nav")) is not None}


def history(amfi_code, root, fetch=default_fetch, max_age_days=1):
    """{iso_date: nav}. Uses the cache when younger than max_age_days, and a
    stale cache when the fetch fails."""
    path = os.path.join(common.paths(root)["nav_cache"], f"{amfi_code}.json")
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_days * 86400
    if not fresh:
        try:
            doc = json.loads(fetch(MFAPI.format(code=amfi_code)))
            series = parse_history(doc)
            if series:
                common.write_json(path, series)
                return series
        except (OSError, ValueError):
            if not os.path.exists(path):
                raise
    with open(path) as f:
        return json.load(f)


def nav_on(series, date, max_back_days=7):
    """NAV on the date, else the latest within max_back_days before it. Never
    a later NAV."""
    d = dt.date.fromisoformat(date)
    for k in range(max_back_days + 1):
        v = series.get((d - dt.timedelta(days=k)).isoformat())
        if v is not None:
            return v
    return None


def latest_date(series):
    return max(series) if series else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("latest")
    a1.add_argument("isins", nargs="+")
    a2 = sub.add_parser("history")
    a2.add_argument("code")
    for p in (a1, a2):
        p.add_argument("--root")
    a = ap.parse_args(argv)
    if a.cmd == "latest":
        parsed = parse_amfi_navall(default_fetch(AMFI_NAVALL))
        idx = isin_index(parsed)
        out = {i: parsed.get(idx.get(i, ""), None) for i in a.isins}
    else:
        root = common.resolve_root(a.root)
        s = history(a.code, root)
        out = {"code": a.code, "points": len(s), "first": min(s), "last": max(s),
               "last_nav": s[max(s)]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
