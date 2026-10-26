#!/usr/bin/env python3
"""Helpers every html-slides script shares: where the user's decks live, and
loading JSON. No network.

    python3 scripts/common.py --where [--root PATH]
"""
import datetime as dt
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_ENV = "SLIDES_ROOT"
TEMPLATE = os.path.join(SKILL_DIR, "assets", "deck.html")

DEFAULT_PROFILE = {
    "accent": "#2f6fde",
    "number_style": "in",
    "currency": "₹",
    "max_slides": 16,
    "research": "quick",
}


def resolve_root(arg=None):
    """--root, then $SLIDES_ROOT, then the working directory. The skill's own
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
        "notes": os.path.join(data, "notes.md"),
        "profile": os.path.join(data, "profile.json"),
        "skill_data": sd,
        "decks": os.path.join(sd, "decks"),
        "research": os.path.join(sd, "research"),
        "index": os.path.join(sd, "decks.json"),
    }


def load_json(path, default=None):
    """The JSON in path, or default when the file does not exist."""
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_profile(root):
    """The defaults overlaid with data/profile.json, if there is one."""
    prof = dict(DEFAULT_PROFILE)
    if root:
        prof.update({k: v for k, v in (load_json(paths(root)["profile"], {}) or {}).items()
                     if not k.startswith("_")})
    return prof


def slugify(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = s[:limit].rstrip("-")
    return s or "deck"


def today():
    return dt.date.today().isoformat()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", action="store_true")
    ap.add_argument("--root")
    a = ap.parse_args()
    r = resolve_root(a.root)
    print(r, "(data/ exists)" if os.path.isdir(os.path.join(r, "data")) else "(no data/ yet)")
