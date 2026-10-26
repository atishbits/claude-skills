#!/usr/bin/env python3
"""The deck index, data/skill-data/decks.json: what decks exist, when they
were made, and the private link each was published at.

    python3 scripts/decks.py [--root WORKROOT] list
    python3 scripts/decks.py [--root WORKROOT] link ID URL
    python3 scripts/decks.py [--root WORKROOT] show ID
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402


def load(index_path):
    return common.load_json(index_path, {"decks": []}) or {"decks": []}


def find(idx, did):
    """The entry whose id is did, or the only one starting with it."""
    exact = [d for d in idx["decks"] if d.get("id") == did]
    if exact:
        return exact[0]
    pre = [d for d in idx["decks"] if str(d.get("id", "")).startswith(did)]
    return pre[0] if len(pre) == 1 else None


def link(index_path, did, url):
    if not url.startswith("https://"):
        raise ValueError("the link must start with https://")
    idx = load(index_path)
    d = find(idx, did)
    if not d:
        raise KeyError(f"no deck {did!r} in the index")
    d["url"] = url
    common.write_json(index_path, idx)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    lp = sub.add_parser("link")
    lp.add_argument("id")
    lp.add_argument("url")
    sp = sub.add_parser("show")
    sp.add_argument("id")
    a = ap.parse_args(argv)
    p = common.paths(common.resolve_root(a.root))
    if a.cmd == "list":
        for d in load(p["index"])["decks"]:
            print(f"{d.get('date')}  {d.get('id')}  {d.get('slides')} slides  {d.get('url') or '(not published)'}")
            print(f"    {d.get('title')}")
        return 0
    if a.cmd == "link":
        try:
            d = link(p["index"], a.id, a.url)
        except (KeyError, ValueError) as e:
            print(e, file=sys.stderr)
            return 1
        print(json.dumps(d, indent=1, ensure_ascii=False))
        return 0
    d = find(load(p["index"]), a.id)
    if not d:
        print(f"no deck {a.id!r}", file=sys.stderr)
        return 1
    print(json.dumps(dict(d, html_path=os.path.join(p["skill_data"], d["html"]),
                          json_path=os.path.join(p["skill_data"], d["json"])), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
