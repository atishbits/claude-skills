#!/usr/bin/env python3
"""Which research in a note is still fresh enough to reuse.

Each note carries a `**Research:**` block (note-template.md): the consensus
target, management guidance, named peers and the re-check price, each with
the date it was found. A run on any surface reads this first and redoes only
the items that are due, instead of repeating web searches and transcript
reads another session already did.

    python3 scripts/freshness.py TICKER [...]
"""
import json
import os
import re
import sys
from datetime import date

ITEMS = ("consensus", "guidance", "peers", "recheck")
WINDOW_DAYS = {"consensus": 30, "peers": 90, "guidance": 92}

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
STOCKS_DIR = os.path.join(ROOT, "data", "skill-data", "stocks")

LINE = re.compile(r"^- (consensus|guidance|peers|recheck): (.*?)\s*(?:—\s*)?as of (\d{4}-\d{2}-\d{2})"
                  r"(?:, until (\d{4}-\d{2}-\d{2}))?\s*$")


def parse_research(text):
    out = {}
    in_block = False
    for line in text.splitlines():
        if line.startswith("**Research:**"):
            in_block = True
            continue
        if in_block:
            if not line.startswith("- "):
                if line.strip():
                    break
                continue
            m = LINE.match(line.strip())
            if m:
                value = m.group(2).rstrip(" —").strip()
                out[m.group(1)] = {"value": value, "as_of": m.group(3), "until": m.group(4)}
    return out


def assess(research, today):
    result = {}
    for item in ITEMS:
        r = research.get(item)
        if not r:
            result[item] = {"status": "due", "as_of": None, "age_days": None, "value": None}
            continue
        as_of = date.fromisoformat(r["as_of"])
        age = (today - as_of).days
        if item == "recheck":
            status = "info"
        elif item == "guidance" and r.get("until"):
            status = "fresh" if today <= date.fromisoformat(r["until"]) else "due"
        else:
            status = "fresh" if age <= WINDOW_DAYS[item] else "due"
        result[item] = {"status": status, "as_of": r["as_of"], "age_days": age, "value": r["value"]}
    return result


def for_ticker(ticker, today=None, stocks_dir=None):
    path = os.path.join(stocks_dir or STOCKS_DIR, f"{ticker.upper()}.md")
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    return assess(parse_research(text), today or date.today())


def main(argv=None):
    tickers = (argv if argv is not None else sys.argv[1:])
    if not tickers:
        sys.exit("usage: freshness.py TICKER [...]")
    print(json.dumps({t.upper(): for_ticker(t) for t in tickers}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
