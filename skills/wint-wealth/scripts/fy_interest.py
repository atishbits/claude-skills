#!/usr/bin/env python3
"""Bond interest for one Indian financial year, for the advance-tax estimate:
what the report says was already paid in the year, what it schedules for the
rest of it, and the TDS on both.

    python3 scripts/fy_interest.py [--fy-start YYYY-04-01] [--out PATH] [--root PATH]

The year defaults to the one the newest snapshot falls in. Interest is gross
(before TDS), which is the figure that is taxed; principal is not income and
is left out. --out also writes the result to PATH, for example the advance-tax
skill's data folder. Amounts are the Master Report's own, summed."""
import argparse
import json
import sys

import common


def _sum(rows):
    return {"interest_gross": round(sum(r.get("interest_gross") or 0 for r in rows), 2),
            "tds": round(sum(r.get("tds") or 0 for r in rows), 2)}


def fy_interest(snapshot, fy_start=None):
    start = fy_start or common.financial_year_start(snapshot["as_of"])
    end = f"{int(start[:4]) + 1}-03-31"
    in_year = lambda r: bool(r.get("date")) and start <= r["date"] <= end  # noqa: E731
    received = [r for r in snapshot["received_cashflows"] if in_year(r)]
    scheduled = [r for r in snapshot["expected_cashflows"] if in_year(r)]
    got, due = _sum(received), _sum(scheduled)
    paying = [r for r in received + scheduled if (r.get("interest_gross") or 0) > 0]
    return {
        "financial_year": f"{start[:4]}-{str(int(start[:4]) + 1)[2:]}", "from": start, "to": end,
        "as_of": snapshot["as_of"], "received": got, "scheduled": due,
        "total": {k: round(got[k] + due[k], 2) for k in got},
        "issuers_without_tds": sorted({r["issuer"] for r in paying}
                                      - {r["issuer"] for r in paying if r.get("tds")}),
        "basis": "interest before TDS, from the Master Report; scheduled interest assumes every "
                 "payment arrives. Bonds bought after the report are not in it.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fy-start")
    parser.add_argument("--out")
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    snapshots = common.dated_files(common.skill_data_dir(root), "snapshot-")
    if not snapshots:
        print("No snapshot yet. Run ingest.py reports first.", file=sys.stderr)
        return 1
    result = fy_interest(common.load_json(snapshots[-1]), args.fy_start)
    if args.out:
        common.write_json(args.out, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
