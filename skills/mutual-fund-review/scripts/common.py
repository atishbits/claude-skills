#!/usr/bin/env python3
"""Helpers every mutual-fund-review script shares: where the user's data lives,
loading the profile and tax rules, parsing the date and number formats that
portals and statements use, and hiding folio numbers. No network access here.

    python3 scripts/common.py --where [--root PATH]
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_ENV = "MF_ROOT"
TEMPLATE = os.path.join(SKILL_DIR, "profile-template.json")
TAX_RULES = os.path.join(SKILL_DIR, "references", "cg-rates.json")
BENCHMARKS = os.path.join(SKILL_DIR, "references", "benchmarks.json")


def resolve_root(arg=None):
    """--root, then $MF_ROOT, then the working directory. The skill's own
    folder is a root only if its data/ already exists (a checkout, where data/
    is gitignored): an installed plugin folder is replaced on update."""
    root = os.path.abspath(arg or os.environ.get(ROOT_ENV) or os.getcwd())
    if (os.path.realpath(root) == os.path.realpath(SKILL_DIR)
            and not os.path.isdir(os.path.join(root, "data"))):
        sys.exit(f"No working folder: {root} is the skill's own folder and has no data/. "
                 f"Pass --root with the folder that holds data/, or set ${ROOT_ENV}.")
    return root


def paths(root):
    data = os.path.join(root, "data")
    sd = os.path.join(data, "skill-data")
    return {
        "data": data,
        "raw": os.path.join(data, "raw"),
        "adapters": os.path.join(data, "adapters"),
        "profile": os.path.join(data, "profile.json"),
        "notes": os.path.join(data, "notes.md"),
        "fds": os.path.join(data, "fds.csv"),
        "skill_data": sd,
        "nav_cache": os.path.join(sd, "nav"),
        "transactions": os.path.join(sd, "transactions.csv"),
        "fund_meta": os.path.join(sd, "fund-meta.json"),
    }


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(s):
    """ISO date from the formats portals and statements use; None for blank or
    a dash; ValueError for anything else."""
    s = (s or "").strip()
    if s in ("", "-", "--"):
        return None
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[ \-]([A-Za-z]{3})[A-Za-z]*[ \-,]+(\d{4})", s)
    if m and m.group(2).lower() in _MONTHS:
        return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
    if m:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", s)
    if m:
        return dt.date(*map(int, m.groups())).isoformat()
    raise ValueError(f"unrecognised date: {s!r}")


def parse_num(s):
    """Float from '₹2,49,987.87', '-7.13%', '(1,000.50)', 'INR 94.07'; None for blank/dash."""
    if isinstance(s, (int, float)):
        return float(s)
    s = (s or "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"(?i)inr|rs\.?|₹|%|,|\(|\)|\s", "", s)
    if s in ("", "-", "--"):
        return None
    v = float(s)
    return -v if neg else v


def folio_ref(folio):
    """Last four characters plus a short hash: enough to tell folios apart,
    never enough to recover the folio number."""
    folio = (folio or "").strip() if folio is not None else ""
    if not folio:
        return None
    return f"{folio[-4:]}-{hashlib.sha256(folio.encode()).hexdigest()[:8]}"


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def load_profile(root):
    profile = dict(_read_json(TEMPLATE, {}))
    profile.update(_read_json(paths(root)["profile"], {}))
    return profile


def load_tax_rules():
    return _read_json(TAX_RULES, {})


def load_benchmarks():
    return _read_json(BENCHMARKS, {})


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", action="store_true")
    ap.add_argument("--root")
    a = ap.parse_args(argv)
    if a.where:
        root = resolve_root(a.root)
        p = paths(root)
        print(json.dumps({"root": root, "data_exists": os.path.isdir(p["data"])}, indent=1))


if __name__ == "__main__":
    main()
