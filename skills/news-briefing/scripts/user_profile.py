#!/usr/bin/env python3
"""The personal profile a briefing is built from, and the last-run time.

    python3 scripts/user_profile.py [--profile PATH] [--state PATH] COMMAND

    validate       check the profile; prints OK, or one line per problem
    missing        onboarding fields that are neither filled nor declined
    topics         company or issuer names from holdings files, names only
    layout         likely header rows in a holdings file, to choose --sheet and --header-row
    merge-state    record the latest of several last-run times
    export         the profile plus the last-run time, for the shared copy

The profile may hold only the fields listed here. That is deliberate: it is
what keeps quantities, cost, values and account identifiers out of a file that
is copied to a shared drive."""
import argparse
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

from common import data_dir, format_ts, now_utc, parse_ts, read_last_run

ONBOARDING = ("home.country", "home.city", "work.employer", "work.industry", "work.role",
              "interest_topics")
GROUPS = {"home": ("country", "city"), "work": ("employer", "industry", "role")}
FEED_SECTIONS = ("global", "home", "markets")
KINDS = ("company", "sector", "issuer")
TOP_KEYS = ("home", "work", "feeds", "portfolio_topics", "interest_topics", "declined",
            "last_run", "updated")
# An amount or an identifier that slipped into a name field looks like this.
DIGITS = re.compile(r"\d{5,}")
# Header names that mean "this column holds what the holding is called".
NAME_HEADERS = ("instrument", "symbol", "ticker", "name", "company", "issuer", "security")
SUMMARY_ROWS = ("total", "grand total", "totals")
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _is_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _text(value, where, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: must be non-empty text")
    elif DIGITS.search(value):
        errors.append(f"{where}: contains a run of 5 or more digits")


def validate(profile):
    """Problems with the profile, one string each. Empty means valid."""
    if not isinstance(profile, dict):
        return ["profile: must be a JSON object"]
    errors = [f"{key}: unknown field" for key in profile if key not in TOP_KEYS]

    for group, fields in GROUPS.items():
        block = profile.get(group, {})
        if not isinstance(block, dict):
            errors.append(f"{group}: must be an object")
            continue
        for key, value in block.items():
            if key not in fields:
                errors.append(f"{group}.{key}: unknown field")
            else:
                _text(value, f"{group}.{key}", errors)

    feeds = profile.get("feeds", {})
    if not isinstance(feeds, dict):
        errors.append("feeds: must be an object")
    else:
        for key, value in feeds.items():
            if key == "search":
                if not _is_url(value) or "{query}" not in value:
                    errors.append("feeds.search: must be one http(s) URL containing {query}")
            elif key in FEED_SECTIONS:
                if not isinstance(value, list) or not all(_is_url(u) for u in value):
                    errors.append(f"feeds.{key}: must be a list of http(s) URLs")
            else:
                errors.append(f"feeds.{key}: unknown field")

    for key, second in (("portfolio_topics", "kind"), ("interest_topics", "why")):
        items = profile.get(key, [])
        if not isinstance(items, list):
            errors.append(f"{key}: must be a list")
            continue
        for i, item in enumerate(items):
            where = f"{key}[{i}]"
            if not isinstance(item, dict) or set(item) != {"name", second}:
                errors.append(f"{where}: must have exactly name and {second}")
                continue
            _text(item["name"], f"{where}.name", errors)
            if second == "kind":
                if item["kind"] not in KINDS:
                    errors.append(f"{where}.kind: must be one of {', '.join(KINDS)}")
            else:
                _text(item["why"], f"{where}.why", errors)

    declined = profile.get("declined", [])
    if not isinstance(declined, list) or any(d not in ONBOARDING for d in declined):
        errors.append("declined: must be a list drawn from " + ", ".join(ONBOARDING))

    for key in ("last_run", "updated"):
        if key in profile:
            try:
                parse_ts(profile[key])
            except ValueError:
                errors.append(f"{key}: not an ISO 8601 timestamp")
    return errors


def missing(profile):
    """Onboarding fields still to ask about, in asking order."""
    declined = profile.get("declined", [])
    out = []
    for field in ONBOARDING:
        if field in declined:
            continue
        if field == "interest_topics":
            filled = bool(profile.get("interest_topics"))
        else:
            group, key = field.split(".")
            filled = bool(str(profile.get(group, {}).get(key, "")).strip())
        if not filled:
            out.append(field)
    return out


def _column_index(ref):
    """A cell reference such as C5 -> 2, the position of column C."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def _workbook(path):
    with zipfile.ZipFile(path) as z:
        targets = {r.get("Id"): r.get("Target")
                   for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(SHEET_NS + "si"):
                strings.append("".join(t.text or "" for t in si.iter(SHEET_NS + "t")))
        out = []
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).iter(SHEET_NS + "sheet"):
            target = targets[sheet.get(REL_ID)].lstrip("/")
            member = target if target.startswith("xl/") else "xl/" + target
            rows = []
            for row in ET.fromstring(z.read(member)).iter(SHEET_NS + "row"):
                number = int(row.get("r") or len(rows) + 1)
                rows.extend([] for _ in range(number - 1 - len(rows)))
                cells = []
                for c in row.iter(SHEET_NS + "c"):
                    idx = _column_index(c.get("r")) if c.get("r") else len(cells)
                    cells.extend("" for _ in range(idx - len(cells)))
                    value = c.find(SHEET_NS + "v")
                    if c.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in c.iter(SHEET_NS + "t"))
                    elif c.get("t") == "s":
                        text = strings[int(value.text)]
                    else:
                        text = (value.text or "") if value is not None else ""
                    cells.append(text)
                rows.append(cells)
            out.append((sheet.get("name") or "", rows))
        return out


def tables(path):
    """Every table in a holdings file as (sheet name, rows of text). A CSV is
    one table with no name. Rows and cells sit where the file has them, so row
    6 of a sheet is item 5 of its list."""
    if path.lower().endswith(".xlsx"):
        try:
            return _workbook(path)
        except (zipfile.BadZipFile, KeyError, IndexError, TypeError, SyntaxError, ValueError):
            raise ValueError(f"{path}: not a readable .xlsx workbook") from None
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [("", list(csv.reader(fh)))]
    except (UnicodeDecodeError, csv.Error):
        raise ValueError(f"{path}: not a CSV or .xlsx table") from None


def _table(path, sheet):
    found = tables(path)
    if sheet is None:
        return found[0][1] if found else []
    for name, rows in found:
        if name.strip().lower() == sheet.strip().lower():
            return rows
    raise ValueError(f"{path}: no sheet named {sheet}; it has: " + ", ".join(n for n, _ in found))


def layout(paths, per_sheet=5, look=50):
    """Rows that could be a table's header, for choosing --sheet and
    --header-row: in each sheet, the first few rows with three or more filled
    cells. Lines about the investor above a table are narrower than that, and
    any cell containing a digit is masked, so this shows the shape of a file
    without its identifiers, amounts or dates."""
    out = []
    for path in paths:
        for name, rows in tables(path):
            shown = 0
            for number, row in enumerate(rows[:look], 1):
                cells = [c.strip() for c in row]
                if sum(1 for c in cells if c) < 3:
                    continue
                out.append({"file": os.path.basename(path), "sheet": name, "row": number,
                            "cells": ["#" if re.search(r"\d", c) else c[:30] for c in cells]})
                shown += 1
                if shown == per_sheet:
                    break
    return out


def topics(paths, kind="company", column=None, sheet=None, header_row=1):
    """Names from holdings files (CSV or .xlsx), and how many rows were skipped
    because the name looked like an identifier. Only the name column is read;
    every other column, whatever it holds, is ignored. The header is taken from
    the row the caller names, never guessed: the lines above a table in a
    statement are about the investor, not the holdings. The table ends at the
    first empty row below the header; what follows is notes."""
    names, skipped = set(), 0
    for path in paths:
        rows = _table(path, sheet)
        if not rows:
            continue
        if not 1 <= header_row <= len(rows):
            raise ValueError(f"{path}: no row {header_row} to use as the header")
        header = [h.strip().lower() for h in rows[header_row - 1]]
        if column:
            if column.strip().lower() not in header:
                raise ValueError(f"{path}: no column named {column}")
            idx = header.index(column.strip().lower())
        else:
            idx = next((header.index(h) for h in NAME_HEADERS if h in header), 0)
        for row in rows[header_row:]:
            if not any(cell.strip() for cell in row):
                break
            name = row[idx].strip() if idx < len(row) else ""
            if not name or name.lower() in SUMMARY_ROWS:
                continue
            if DIGITS.search(name):
                skipped += 1
                continue
            names.add(name)
    return [{"name": n, "kind": kind} for n in sorted(names, key=str.lower)], skipped


def latest(timestamps, now):
    """The latest of the timestamps that is not after now, or None."""
    usable = [t for t in timestamps if t <= now]
    return max(usable) if usable else None


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        if default is not None:
            return default
        sys.exit(f"No profile at {path}. Run the skill's onboarding first.")
    except ValueError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")


def _checked(path):
    profile = load(path)
    errors = validate(profile)
    if errors:
        sys.exit("Profile is not valid:\n  " + "\n  ".join(errors))
    return profile


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=os.path.join(data_dir(), "profile.json"))
    ap.add_argument("--state", default=os.path.join(data_dir(), "state.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("missing")
    sub.add_parser("export")
    t = sub.add_parser("topics")
    t.add_argument("--holdings", nargs="+", required=True)
    t.add_argument("--kind", choices=("company", "issuer"), default="company")
    t.add_argument("--column")
    t.add_argument("--sheet")
    t.add_argument("--header-row", type=int, default=1)
    lay = sub.add_parser("layout")
    lay.add_argument("--holdings", nargs="+", required=True)
    m = sub.add_parser("merge-state")
    m.add_argument("timestamps", nargs="*")
    m.add_argument("--now")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        _checked(args.profile)
        print("OK")
    elif args.cmd == "missing":
        for field in missing(load(args.profile, default={})):
            print(field)
    elif args.cmd == "export":
        profile = _checked(args.profile)
        profile.pop("last_run", None)
        last_run = read_last_run(args.state)
        if last_run:
            profile["last_run"] = format_ts(last_run)
        print(json.dumps(profile, indent=2))
    elif args.cmd == "topics":
        try:
            found, skipped = topics(args.holdings, args.kind, args.column, args.sheet,
                                    args.header_row)
        except (OSError, ValueError) as exc:
            sys.exit(str(exc))
        if skipped:
            print(f"{skipped} row(s) skipped: the name looked like an identifier", file=sys.stderr)
        print(json.dumps(found, indent=2))
    elif args.cmd == "layout":
        try:
            print(json.dumps(layout(args.holdings), indent=2))
        except (OSError, ValueError) as exc:
            sys.exit(str(exc))
    elif args.cmd == "merge-state":
        try:
            given = [parse_ts(t) for t in args.timestamps]
        except ValueError:
            sys.exit("merge-state: every timestamp must be ISO 8601")
        now = parse_ts(args.now) if args.now else now_utc()
        existing = read_last_run(args.state)
        result = latest(given + ([existing] if existing else []), now)
        if result is None:
            print("none")
            return
        os.makedirs(os.path.dirname(os.path.abspath(args.state)), exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump({"last_run": format_ts(result)}, fh)
        print(format_ts(result))


if __name__ == "__main__":
    main()
