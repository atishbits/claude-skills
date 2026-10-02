#!/usr/bin/env python3
"""Turn what the user brings from Wint Wealth into the normalised files every
other script reads.

    python3 scripts/ingest.py reports  [--file REPORT.xlsx] [--root PATH] [--date YYYY-MM-DD]
    python3 scripts/ingest.py listings [--file CAPTURE.json] [--root PATH] [--no-checksum]

`reports` reads the Master Report workbook (Reports and documents -> Master
Report on the portal) and writes data/skill-data/snapshot-<date>.json.

Columns are found by the header names in config.json's `report_columns`, never
by position. A missing or renamed header stops the run and says which one; an
unknown extra column is a warning. The identity rows at the top of each sheet
and the workbook's file name (it carries a phone number) are never copied.
"""
import argparse
import datetime as dt
import glob
import os
import re
import sys

import common
import xlsx_reader

ISIN = re.compile(r"^IN[A-Z0-9]{10}$")
NUM_FIELDS = {"units", "ytm", "current_value", "upcoming_sell_value", "upcoming_interest",
              "upcoming_principal", "invested", "sold", "principal_repaid", "interest_gross_paid",
              "interest_net_paid", "tds_paid", "amount", "principal", "interest_net",
              "interest_gross", "tds", "sell_value", "face_value", "acquisition_cost", "xirr"}
DATE_FIELDS = {"date", "maturity_date"}


class IngestError(Exception):
    pass


def _main_block(row):
    """Header cells from column A up to the first empty one. The cashflow sheet
    has a second table further right, after a gap; this stops before it."""
    block = []
    for cell in row:
        text = cell.strip()
        if not text:
            break
        block.append(text)
    return block


def _has_table(rows):
    return any(len(_main_block(row)) >= 4 for row in rows)


def extract_table(rows, column_map, sheet):
    """Read every block of `rows` that sits under a header row containing all
    the mapped headers. Returns (records as text, warnings)."""
    wanted = list(column_map.values())
    records, warnings, headers_seen = [], [], 0
    i = 0
    while i < len(rows):
        block = _main_block(rows[i])
        if not all(h in block for h in wanted):
            i += 1
            continue
        headers_seen += 1
        if headers_seen == 1:
            unknown = [h for h in block if h not in wanted]
            if unknown:
                warnings.append(f"{sheet}: unmapped column(s) {unknown}")
        index = {field: block.index(source) for field, source in column_map.items()}
        i += 1
        while i < len(rows):
            row = rows[i]
            cells = {f: (row[j].strip() if j < len(row) else "") for f, j in index.items()}
            if not ISIN.match(cells.get("isin", "")):
                break
            records.append(cells)
            i += 1
    if headers_seen == 0 and _has_table(rows):
        best = max((_main_block(r) for r in rows), key=lambda b: len(set(b) & set(wanted)))
        if not set(best) & set(wanted):
            best = max((_main_block(r) for r in rows), key=len)
        missing = [h for h in wanted if h not in best]
        raise IngestError(
            f"{sheet}: expected column(s) {missing} not found. Headers found: {best}. "
            "If Wint renamed a column, update report_columns in config.json.")
    return records, warnings


def _typed(record):
    out = {}
    for field, text in record.items():
        if field in NUM_FIELDS:
            out[field] = common.parse_num(text)
        elif field in DATE_FIELDS:
            out[field] = common.parse_date(text)
        else:
            out[field] = text or None
    return out


def build_snapshot(workbook, config, as_of, report_sha256):
    content = {"schema": 1, "as_of": as_of}
    warnings = []
    for key, spec in config["report_columns"].items():
        rows = workbook.get(spec["sheet"])
        if rows is None:
            if spec.get("required"):
                raise IngestError(
                    f"sheet {spec['sheet']!r} not found. Sheets present: {list(workbook)}")
            warnings.append(f"sheet {spec['sheet']!r} not found; {key} left empty")
            content[key] = []
            continue
        if spec["columns"] is None:
            if _has_table(rows):
                warnings.append(
                    f"{spec['sheet']} has data but no column map; add one to config.json "
                    f"report_columns.{key}")
            content[key] = []
            continue
        records, table_warnings = extract_table(rows, spec["columns"], spec["sheet"])
        if spec.get("required") and not records and not _has_table(rows):
            warnings.append(f"{spec['sheet']} has no rows")
        warnings.extend(table_warnings)
        content[key] = [_typed(r) for r in records]
    content["warnings"] = warnings
    content["source"] = {"report_sha256": report_sha256}
    content["snapshot_hash"] = common.sha256_text(common.canonical(content))
    return content


def _find_report(root):
    for pattern in (os.path.join(root, "data", "reports", "*.xlsx"),
                    os.path.expanduser("~/Downloads/WintWealth_Master_Report_*.xlsx")):
        found = sorted(glob.glob(pattern), key=os.path.getmtime)
        if found:
            return found[-1]
    raise IngestError(
        "No Master Report found in data/reports/ or ~/Downloads. Download it from "
        "Reports and documents -> Master Report, or pass --file.")


def cmd_reports(args):
    root = common.resolve_root(args.root)
    path = args.file or _find_report(root)
    as_of = args.date or dt.date.today().isoformat()
    snapshot = build_snapshot(xlsx_reader.read_workbook(path), common.load_config(), as_of,
                              common.sha256_file(path))
    out = os.path.join(common.skill_data_dir(root), f"snapshot-{as_of}.json")
    common.write_json(out, snapshot)
    held = snapshot["holdings"]
    print(f"snapshot: {out}")
    print(f"holdings: {len(held)}  invested: {sum(h['invested'] or 0 for h in held):.2f}  "
          f"current value: {sum(h['current_value'] or 0 for h in held):.2f}")
    print(f"expected cashflows: {len(snapshot['expected_cashflows'])}  "
          f"received: {len(snapshot['received_cashflows'])}  "
          f"purchases: {len(snapshot['purchases'])}")
    for warning in snapshot["warnings"]:
        print(f"warning: {warning}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reports = sub.add_parser("reports")
    reports.add_argument("--file")
    reports.add_argument("--root")
    reports.add_argument("--date")
    reports.set_defaults(func=cmd_reports)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except IngestError as err:
        print(f"ingest failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
