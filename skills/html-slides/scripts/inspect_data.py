#!/usr/bin/env python3
"""Show what a JSON or CSV data file holds, as the paths a deck's data refs
use, so a slide can point at the right figures without reading the whole
file into the conversation.

    python3 scripts/inspect_data.py FILE [--depth 3] [--name NAME]

Prints one line per path: `name:path  type  sample`. A list shows its first
item's shape once (as path.0) and its length; a mapping of numbers is shown
as a ready items_from source.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deckdata as dd  # noqa: E402


def _sample(v):
    s = repr(v)
    return s if len(s) <= 40 else s[:37] + "..."


def describe(obj, prefix, depth, out):
    if isinstance(obj, dict):
        nums = [k for k, v in obj.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        tag = "  <- items_from ready" if len(nums) >= 2 and len(nums) == len(obj) else ""
        out.append(f"{prefix}  mapping[{len(obj)}]{tag}")
        if depth <= 0:
            return out
        for k, v in list(obj.items())[:40]:
            describe(v, f"{prefix}.{k}" if not prefix.endswith(":") else f"{prefix}{k}", depth - 1, out)
        if len(obj) > 40:
            out.append(f"{prefix}.…  ({len(obj) - 40} more keys)")
    elif isinstance(obj, list):
        out.append(f"{prefix}  list[{len(obj)}]")
        if obj and depth > 0:
            describe(obj[0], f"{prefix}.0" if not prefix.endswith(":") else f"{prefix}0", depth - 1, out)
    else:
        out.append(f"{prefix}  {type(obj).__name__}  {_sample(obj)}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--name", default="src")
    a = ap.parse_args(argv)
    data = dd.load_source(a.file)
    print("\n".join(describe(data, a.name + ":", a.depth, [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
