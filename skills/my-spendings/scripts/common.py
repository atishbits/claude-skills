#!/usr/bin/env python3
"""Helpers every my-spendings script shares: where the user's data lives, and
parsing the date and amount formats bank and card statements use. No network.

    python3 scripts/common.py --where [--root PATH]
"""
import datetime as dt
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_ENV = "SPENDINGS_ROOT"


def resolve_root(arg=None):
    """--root, then $SPENDINGS_ROOT, then the working directory. The skill's own
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
        "accounts": os.path.join(data, "accounts.json"),
        "rules": os.path.join(data, "rules.csv"),
        "notes": os.path.join(data, "notes.md"),
        "holdings": os.path.join(data, "holdings.csv"),
        "offers": os.path.join(data, "offers"),
        "cards": os.path.join(data, "cards"),
        "vendor": os.path.join(data, "vendor"),
        "skill_data": sd,
        "ledger": os.path.join(sd, "ledger.csv"),
        "coverage": os.path.join(sd, "coverage.json"),
    }


DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%y",
                "%d %B %Y", "%d-%b-%y", "%d %b %y"]


def parse_date(s, fmt=None):
    """ISO date string; ValueError when no format fits."""
    s = (s or "").strip()
    for f in ([fmt] if fmt else []) + DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date: {s!r}")


def parse_amount(s):
    """Signed float from a statement amount. A trailing or leading Dr makes it
    negative, Cr positive; blank is 0.0."""
    s = str(s or "").strip()
    if not s:
        return 0.0
    u = s.upper()
    sign = 1.0
    if re.search(r"\bDR\b", u):
        sign = -1.0
    if u.startswith("(") and u.endswith(")"):
        sign = -1.0
    num = re.sub(r"[^0-9.\-]", "", u.replace("DR", "").replace("CR", ""))
    if num in ("", "-", ".", "-."):
        return 0.0
    v = float(num)
    return -abs(v) if sign < 0 else v


_CHANNEL = {"UPI", "NEFT", "IMPS", "MMT", "BIL", "ACH", "NACH", "ECS", "RTGS", "POS", "TRF", "TO",
            "FROM", "PAYMENT", "PAY", "NA", "REF"}


def payee_key(desc):
    """A short, stable name for who a transaction was with: the first token of
    the description that is not a channel word, a reference number or noise."""
    for tok in re.split(r"[/\-*\s]+", (desc or "").upper()):
        if len(tok) < 3 or tok in _CHANNEL:
            continue
        digits = sum(c.isdigit() for c in tok)
        if digits * 2 >= len(tok):
            continue
        return tok[:20]
    return "UNKNOWN"


def load_json(path, default=None):
    """The JSON in path, or default when the file does not exist."""
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mask(acct):
    """Only the last four characters of an account or card number."""
    acct = re.sub(r"\s", "", str(acct or ""))
    return "XX" + acct[-4:] if acct else ""


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", action="store_true")
    ap.add_argument("--root")
    a = ap.parse_args()
    r = resolve_root(a.root)
    print(r, "(data/ exists)" if os.path.isdir(os.path.join(r, "data")) else "(no data/ yet)")
