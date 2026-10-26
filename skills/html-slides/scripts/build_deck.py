#!/usr/bin/env python3
"""Build a deck: resolve data references, check it, render one self-contained
HTML file, and record it in the deck index.

    python3 scripts/build_deck.py DECK.json [--root WORKROOT] [--data name=path ...]
                                  [--check] [--out-dir DIR]

DECK.json follows references/deck_format.md. Data sources come from --data
and from the deck's own "data" mapping (paths relative to the deck file).
Writes data/skill-data/decks/<id>.html and <id>.json (the deck with every
reference resolved, so it rebuilds without the data files), records both and
DECK.json in data/skill-data/decks.json, and prints a JSON
summary: ok, id, html, json, slides, errors, warnings. Exit 1 on errors;
--check stops after the checks and writes nothing.
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402
import deckdata as dd  # noqa: E402
import lint  # noqa: E402
import render  # noqa: E402


def deck_id(deck):
    if deck.get("id"):
        return common.slugify(deck["id"], 64)
    return f"{deck.get('date') or common.today()}-{common.slugify(deck.get('title'))}"


def update_index(index_path, entry):
    idx = common.load_json(index_path, {"decks": []}) or {"decks": []}
    decks = idx.setdefault("decks", [])
    for d in decks:
        if d.get("id") == entry["id"]:
            url = d.get("url")
            d.update(entry)
            if url and not entry.get("url"):
                d["url"] = url
            break
    else:
        decks.append(entry)
    decks.sort(key=lambda d: (d.get("date") or "", d.get("id")), reverse=True)
    common.write_json(index_path, idx)
    return idx


def build(deck, sources, profile, template, check_only=False, out_dir=None, index_path=None,
          source_path=None):
    """Returns the summary dict. Pure apart from the files it writes."""
    deck = copy.deepcopy(deck)
    deck.setdefault("date", common.today())
    deck, errors = dd.resolve(deck, sources)
    warnings = []
    if not errors:
        e, w = lint.check_deck(deck, profile.get("max_slides", 16))
        errors += e
        warnings += w
    did = deck_id(deck)
    summary = {"ok": not errors, "id": did, "slides": len(deck.get("slides") or []),
               "errors": errors, "warnings": warnings}
    if errors or check_only:
        return summary
    html = render.render_deck(deck, template, profile)
    os.makedirs(out_dir, exist_ok=True)
    hp = os.path.join(out_dir, did + ".html")
    jp = os.path.join(out_dir, did + ".json")
    if source_path and os.path.abspath(source_path) == os.path.abspath(jp):
        jp = os.path.join(out_dir, did + ".resolved.json")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(html)
    common.write_json(jp, deck)
    summary.update({"html": hp, "json": jp, "bytes": len(html.encode("utf-8"))})
    if index_path:
        rel = lambda x: os.path.relpath(os.path.abspath(x), os.path.dirname(index_path))  # noqa: E731
        entry = {"id": did, "title": deck["title"], "date": deck["date"],
                 "slides": summary["slides"], "html": rel(hp), "json": rel(jp)}
        if source_path:
            entry["source"] = rel(source_path)
        update_index(index_path, entry)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck")
    ap.add_argument("--root")
    ap.add_argument("--data", action="append", default=[], help="name=path to a JSON or CSV file")
    ap.add_argument("--check", action="store_true", help="check only, write nothing")
    ap.add_argument("--out-dir", help="default: WORKROOT/data/skill-data/decks")
    a = ap.parse_args(argv)

    with open(a.deck, encoding="utf-8") as f:
        deck = json.load(f)
    root = None if (a.out_dir and not a.root and not os.environ.get(common.ROOT_ENV)) \
        else common.resolve_root(a.root)
    profile = common.load_profile(root)
    base = os.path.dirname(os.path.abspath(a.deck))
    try:
        sources = dd.parse_data_args([f"{k}={v}" for k, v in (deck.get("data") or {}).items()], base)
        sources.update(dd.parse_data_args(a.data))
    except (dd.RefError, OSError, ValueError) as e:
        print(json.dumps({"ok": False, "errors": [f"data source: {e}"], "warnings": []}, indent=1))
        return 1
    with open(common.TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    p = common.paths(root) if root else None
    out_dir = a.out_dir or p["decks"]
    index = p["index"] if p and not a.out_dir else None
    summary = build(deck, sources, profile, template, a.check, out_dir, index, a.deck)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
