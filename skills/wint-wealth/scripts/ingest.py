#!/usr/bin/env python3
"""Turn what the user brings from Wint Wealth into the normalised files every
other script reads.

    python3 scripts/ingest.py reports  [--file REPORT.xlsx] [--root PATH] [--date YYYY-MM-DD]
    python3 scripts/ingest.py listings [--file CAPTURE.json] [--root PATH] [--no-checksum]

`listings` reads the file capture-listings.js saved from the listings page,
checks its SHA-256 against the rows, and writes data/skill-data/listings-<time>.json.

`reports` reads the Master Report workbook (Reports and documents -> Master
Report on the portal) and writes data/skill-data/snapshot-<date>.json.

Both commands read what the user put in data/ (the newest *.xlsx, the newest
wint-listings-*.json) unless --file says otherwise. Save the report there as
wint-master-report-<date>.xlsx: the name Wint gives it carries a phone number.

Columns are found by the header names in config.json's `report_columns`, never
by position. A missing or renamed header stops the run and says which one; an
unknown extra column is a warning. The identity rows at the top of each sheet
are never copied into a snapshot.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import zipfile

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


def extract_table(rows, column_map, sheet, required=False):
    """Read every row of `rows` that sits under a header row containing all the
    mapped headers and carries an ISIN. A sheet may repeat its header (one
    block per financial year); each header re-reads the column positions. Rows
    without an ISIN (titles, totals, spacers, the disclaimer) are skipped, not
    treated as the end of the table. Returns (records as text, warnings)."""
    wanted = list(column_map.values())
    records, warnings, headers_seen, index = [], [], 0, None
    for row in rows:
        block = _main_block(row)
        if all(h in block for h in wanted):
            headers_seen += 1
            if headers_seen == 1:
                unknown = [h for h in block if h not in wanted]
                if unknown:
                    warnings.append(f"{sheet}: unmapped column(s) {unknown}")
            index = {field: block.index(source) for field, source in column_map.items()}
            continue
        if index is None:
            continue
        cells = {f: (row[j].strip() if j < len(row) else "") for f, j in index.items()}
        if ISIN.match(cells.get("isin", "")):
            records.append(cells)
    if headers_seen == 0 and not _has_table(rows) and required:
        raise IngestError(f"{sheet}: no header row found starting in column A. "
                          f"Expected column(s) {wanted}.")
    if headers_seen == 0 and _has_table(rows):
        best = max((_main_block(r) for r in rows), key=lambda b: len(set(b) & set(wanted)))
        if not set(best) & set(wanted):
            best = max((_main_block(r) for r in rows), key=len)
        missing = [h for h in wanted if h not in best]
        raise IngestError(
            f"{sheet}: expected column(s) {missing} not found. Headers found: {best}. "
            "If Wint renamed a column, update report_columns in config.json.")
    return records, warnings


def _typed(record, sheet):
    out = {}
    for field, text in record.items():
        try:
            if field in NUM_FIELDS:
                out[field] = common.parse_num(text)
            elif field in DATE_FIELDS:
                out[field] = common.parse_date(text)
            else:
                out[field] = text or None
        except ValueError:
            raise IngestError(f"{sheet}: cannot read {field} from {text!r} "
                              f"(bond {record.get('isin')})") from None
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
        records, table_warnings = extract_table(rows, spec["columns"], spec["sheet"],
                                                required=bool(spec.get("required")))
        if spec.get("required") and not records:
            warnings.append(f"{spec['sheet']} has no rows")
        warnings.extend(table_warnings)
        content[key] = [_typed(r, spec["sheet"]) for r in records]
    content["warnings"] = warnings
    content["source"] = {"report_sha256": report_sha256}
    content["snapshot_hash"] = common.sha256_text(common.canonical(content))
    return content


LISTING_KEYS = ["href", "issuer", "rating", "min", "sold", "ytm_label", "ytm", "ytm_alt",
                "maturity_left", "interest", "principal", "tags"]
MONEY = re.compile(r"₹\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|cr|crores?)?\s*$", re.IGNORECASE)
MULTIPLIER = {"": 1, "k": 1_000, "lakh": 100_000, "lakhs": 100_000, "cr": 10_000_000,
              "crore": 10_000_000, "crores": 10_000_000}
SITE = "https://www.wintwealth.com"


def rows_checksum(rows):
    """SHA-256 of the rows serialised the way the browser's JSON.stringify does."""
    return common.sha256_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=False))


def verify_capture(capture, check_sum=True):
    for key in ("schema", "captured_at", "rows"):
        if key not in capture:
            raise IngestError(f"capture is missing {key!r}; recapture the listings page")
    for row in capture["rows"]:
        extra = [k for k in row if k not in LISTING_KEYS]
        missing = [k for k in LISTING_KEYS if k not in row]
        if extra or missing:
            raise IngestError(f"capture row has unexpected field(s) {extra} / missing {missing}")
        for key in LISTING_KEYS:
            value = row[key]
            ok = (isinstance(value, list) and all(isinstance(t, str) for t in value)
                  if key == "tags" else isinstance(value, str))
            if not ok:
                raise IngestError(
                    f"capture row for {row.get('issuer')!r}: {key} must be "
                    f"{'a list of strings' if key == 'tags' else 'a string'}, got {value!r}")
    if check_sum and rows_checksum(capture["rows"]) != capture.get("sha256"):
        raise IngestError("capture checksum mismatch: the file changed after it was saved. "
                          "Recapture the listings page.")


def _money(text):
    match = MONEY.search(text or "")
    if not match:
        return None
    return int(round(float(match.group(1).replace(",", "")) *
                     MULTIPLIER[(match.group(2) or "").lower()]))


def _tenure_months(text):
    match = re.match(r"([\d.]+)\s*(day|month|year)s?$", (text or "").strip(), re.IGNORECASE)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).lower()
    if unit == "day":
        return round(value / 30.4375, 1)
    return value * 12 if unit == "year" else value


def _percent(text):
    text = (text or "").strip()
    return common.parse_num(text) if text.endswith("%") else None


def normalise_listing(row):
    warnings = []
    href = row["href"]
    bond = re.search(r"-(\d+)/?(?:\?|$)", href)
    tenure = re.search(r"productTenureId=(\d+)", href)
    sold = re.match(r"([\d.]+)% Sold$", row["sold"])
    units = re.match(r"(\d+) units? left$", row["sold"])
    tags = row["tags"]
    upper = [t.upper() for t in tags]
    item = {
        "key": href,
        "bond_id": bond.group(1) if bond else None,
        "tenure_id": tenure.group(1) if tenure else None,
        "url": SITE + href,
        "issuer": row["issuer"],
        "rating": re.sub(r"\s*\(.*\)", "", row["rating"]).strip() or None,
        "rating_raw": row["rating"],
        "min_investment": _money(row["min"]),
        "sold_pct": float(sold.group(1)) if sold else None,
        "units_left": int(units.group(1)) if units else None,
        "ytm": _percent(row["ytm"]),
        "ytm_is_upper_bound": row["ytm_label"] == "YTM up to",
        "ytm_alt": _percent(row["ytm_alt"]),
        "tenure_months": _tenure_months(row["maturity_left"]),
        "interest_frequency": row["interest"] or None,
        "principal_type": row["principal"] or None,
        "seniority": "subordinated" if any("SUB DEBT" in t for t in upper) else None,
        "secured": False if any("UNSECURED" in t for t in upper) else None,
        "collateral": next((t for t in tags if "BACKED" in t.upper()), None),
        "guarantee": next((t for t in tags if "GUARANTEED" in t.upper()), None),
        "rating_action": ("upgrade" if any(t.startswith("RATING UPGRADED") for t in upper) else
                          "downgrade" if any(t.startswith("RATING DOWNGRADED") for t in upper)
                          else None),
        "held": any(re.match(r"₹.* Invested$", t) for t in tags),
        "tags": tags,
    }
    for field, source in (("min_investment", "min"), ("ytm", "ytm"),
                          ("tenure_months", "maturity_left")):
        if item[field] is None:
            warnings.append(f"{row['issuer']} ({href}): could not read {field} "
                            f"from {row[source]!r}")
    return item, warnings


def build_listings(capture, check_sum=True, allow_partial=False):
    verify_capture(capture, check_sum)
    stated = capture.get("stated_live_count")
    ratio = common.load_config()["min_capture_ratio"]
    partial = bool(stated) and len(capture["rows"]) < ratio * stated
    if partial and not allow_partial:
        raise IngestError(
            f"only {len(capture['rows'])} cards were captured but the page says {stated} bonds "
            "are live. The page probably had not finished loading, or its layout changed. "
            "Recapture, or pass --allow-partial to use it anyway.")
    listings, warnings = [], []
    for row in capture["rows"]:
        item, row_warnings = normalise_listing(row)
        listings.append(item)
        warnings.extend(row_warnings)
    if stated is not None and stated != len(listings):
        warnings.append(f"page says {stated} live bonds but {len(listings)} cards were captured")
    return {"schema": 1, "captured_at": capture["captured_at"],
            "capture_sha256": rows_checksum(capture["rows"]), "verified": bool(check_sum),
            "partial": partial, "stated_live_count": stated, "warnings": warnings, "listings": listings}


def _find_capture(root):
    found = glob.glob(os.path.join(root, "data", "wint-listings-*.json"))
    if not found:
        raise IngestError("No wint-listings-*.json in data/. Run capture-listings.js on the "
                          "listings page, move the file it saves into data/, or pass --file.")
    return max(found, key=os.path.getmtime)


def cmd_listings(args):
    root = common.resolve_root(args.root)
    path = args.file or _find_capture(root)
    doc = build_listings(common.load_json(path), check_sum=not args.no_checksum,
                         allow_partial=args.allow_partial)
    stamp = doc["captured_at"][:16].replace("-", "").replace(":", "")
    out = os.path.join(common.skill_data_dir(root), f"listings-{stamp}.json")
    common.write_json(out, doc)
    print(f"listings: {out}")
    print(f"bonds: {len(doc['listings'])}  captured at: {doc['captured_at']}  "
          f"verified: {doc['verified']}")
    for warning in doc["warnings"]:
        print(f"warning: {warning}")
    return 0


def _find_report(root):
    """The most recently modified workbook in data/."""
    found = glob.glob(os.path.join(root, "data", "*.xlsx"))
    if not found:
        raise IngestError(
            "No Master Report in data/. Download it from Reports and documents -> Master "
            "Report, move it to data/wint-master-report-<date>.xlsx, or pass --file.")
    return max(found, key=os.path.getmtime)


def cmd_reports(args):
    root = common.resolve_root(args.root)
    path = args.file or _find_report(root)
    as_of = args.date or dt.date.today().isoformat()
    try:
        dt.date.fromisoformat(as_of)
    except ValueError:
        raise IngestError(f"--date must be YYYY-MM-DD, got {as_of!r}") from None
    modified = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    print(f"report: {os.path.basename(path)}, last modified {modified}")
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
    listings = sub.add_parser("listings")
    listings.add_argument("--file")
    listings.add_argument("--root")
    listings.add_argument("--no-checksum", action="store_true",
                          help="for a hand-written file; the output is marked unverified")
    listings.add_argument("--allow-partial", action="store_true",
                          help="accept a capture with far fewer cards than the page says are live")
    listings.set_defaults(func=cmd_listings)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except IngestError as err:
        print(f"ingest failed: {err}", file=sys.stderr)
        return 1
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as err:
        print(f"ingest failed: could not read the file ({type(err).__name__}: {err})",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
