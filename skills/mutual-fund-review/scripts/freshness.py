#!/usr/bin/env python3
"""How old is what we know? Per source: when its holdings were last captured,
whether its transaction history is complete, and whether it is past the
profile's stale_after_days. Also the age of the FD rate and any held fund
missing metadata. Run first on every request; pull fresh data only when this
says so or the user asks.

    python3 scripts/freshness.py [--root R] [--today YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json

import common
import fund_meta
import ledger


def _age(date, today):
    if not date:
        return None
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(date[:10])).days


def check(root, today):
    prof = common.load_profile(root)
    out = {"root": root, "snapshot": None, "sources": {}, "suggest_refresh": [],
           "fd_rate_as_of": prof.get("fd_rate_as_of"),
           "fd_rate_age_days": _age(prof.get("fd_rate_as_of"), today),
           "tax_rates_present": bool(prof.get("tax")), "missing_meta": []}
    snap_path = ledger.latest_snapshot(root)
    if not snap_path:
        return out
    with open(snap_path) as f:
        snap = json.load(f)
    out["snapshot"] = snap_path
    for name, s in sorted(snap.get("sources", {}).items()):
        age = _age(s.get("holdings_as_of"), today)
        stale = age is None or age > prof["stale_after_days"]
        out["sources"][name] = {"holdings_as_of": s.get("holdings_as_of"), "age_days": age,
                                "transactions_complete": s.get("transactions_complete", False),
                                "stale": stale}
        if stale:
            out["suggest_refresh"].append(name)
    out["missing_meta"] = fund_meta.missing(root)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--root")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    print(json.dumps(check(common.resolve_root(a.root), a.today), indent=1))


if __name__ == "__main__":
    main()
