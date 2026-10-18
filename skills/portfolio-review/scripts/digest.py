#!/usr/bin/env python3
"""A small per-ticker summary of everything the skill remembers.

Routing, triage ("not analysed in 30 days") and calendar questions read
skill-data/digest.json instead of opening every note, so a session that has
to pull notes from cloud storage pulls only the ones it will re-rate.

    python3 scripts/digest.py          # writes data/skill-data/digest.json
"""
import json
import os
import re
from datetime import date, datetime

import freshness
import rating_ledger

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
SKILL_DATA = os.path.join(ROOT, "data", "skill-data")


def _note_fields(text, today):
    fields = {"rating": None, "last_analysis": None, "days_since_analysis": None, "signal_row": None}
    m = re.search(r"\*\*Last analysis:\*\*\s*(\d{1,2} \w{3} \d{4})", text)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%d %b %Y").date()
            fields["last_analysis"] = d.isoformat()
            fields["days_since_analysis"] = (today - d).days
        except ValueError:
            pass
    m = re.search(r"\*\*Rating:\*\*\s*(BUY|HOLD|SELL)", text)
    if m:
        fields["rating"] = m.group(1)
    m = re.search(r"\*\*Signal row:\*\*\s*Row\s*(\d)", text)
    if m:
        fields["signal_row"] = int(m.group(1))
    return fields


def _calendar(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] not in ("Ticker", "") and not set(cells[0]) <= set("-"):
                rows.setdefault(cells[0].upper(), []).append(f"{cells[1]} | {cells[2]}")
    return rows


def build(skill_data_dir, today):
    stocks = os.path.join(skill_data_dir, "stocks")
    budgets_path = os.path.join(skill_data_dir, "entry-budgets.json")
    budgets = {}
    if os.path.exists(budgets_path):
        with open(budgets_path, encoding="utf-8") as fh:
            budgets = json.load(fh)
    calendar = _calendar(os.path.join(skill_data_dir, "calendar.md"))
    ledger = rating_ledger.load_ledger(ledger_dir=os.path.join(skill_data_dir, "ratings-ledger"))
    out = {"generated_on": today.isoformat(), "tickers": {}, "conflicts": []}
    names = sorted(os.listdir(stocks)) if os.path.isdir(stocks) else []
    for name in names:
        if not name.endswith(".md"):
            continue
        if ".conflict-" in name:
            out["conflicts"].append(f"stocks/{name}")
            continue
        ticker = name[:-3].upper()
        with open(os.path.join(stocks, name), encoding="utf-8") as fh:
            text = fh.read()
        entry = _note_fields(text, today)
        entry["research"] = freshness.assess(freshness.parse_research(text), today)
        entry["budget"] = budgets.get(ticker)
        entry["calendar"] = calendar.get(ticker, [])
        entry["ledger"] = [{"date": e["date"], "rating": e["rating"], "price": e["price"]}
                           for e in ledger if e["ticker"] == ticker]
        out["tickers"][ticker] = entry
    return out


def main():
    data = build(SKILL_DATA, date.today())
    path = os.path.join(SKILL_DATA, "digest.json")
    os.makedirs(SKILL_DATA, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)
    print(path)


if __name__ == "__main__":
    main()
