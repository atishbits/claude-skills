#!/usr/bin/env python3
"""The arithmetic behind an insight line, so a slide never carries a figure
the model worked out in its head ("up 40%", "two-thirds of", "3x").

    python3 scripts/calc.py [--data name=path ...] change OLD NEW
    python3 scripts/calc.py [--data ...] share PART TOTAL
    python3 scripts/calc.py [--data ...] ratio A B
    python3 scripts/calc.py [--data ...] cagr START END YEARS
    python3 scripts/calc.py [--data ...] sum A B [C ...]
    python3 scripts/calc.py [--data ...] annual MONTHLY

Each operand is a number or a data ref (name:path.to.value) into a --data
file. Prints JSON with the inputs, the result and a ready phrase.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deckdata as dd  # noqa: E402


def change(old, new):
    diff = new - old
    pct = None if old == 0 else diff / abs(old) * 100
    if pct is None:
        phrase = "new (no earlier value)"
    else:
        word = "up" if diff > 0 else "down" if diff < 0 else "flat"
        phrase = f"{word} {dd._trim(dd.fmt_number(abs(pct), 'plain', 0 if abs(pct) >= 10 else 1))}%"
    return {"old": old, "new": new, "diff": diff, "pct": None if pct is None else round(pct, 2),
            "phrase": phrase}


def share(part, total):
    if total == 0:
        raise ValueError("total is zero")
    pct = part / total * 100
    p = dd.fmt_number(pct, "plain", 0) + "%"
    words = fraction_words(pct)
    return {"part": part, "total": total, "pct": round(pct, 2),
            "phrase": f"{words} ({p})" if words else p}


def fraction_words(pct):
    """A plain-words fraction when the share is within 1.5 points of a
    familiar one, else None."""
    for f, words in [(10, "a tenth"), (20, "a fifth"), (100 / 4, "a quarter"), (100 / 3, "a third"),
                     (50, "half"), (200 / 3, "two-thirds"), (75, "three-quarters"), (100, "all")]:
        if abs(pct - f) <= 1.5:
            return words
    return None


def ratio(a, b):
    if b == 0:
        raise ValueError("divisor is zero")
    r = a / b
    return {"a": a, "b": b, "ratio": round(r, 3), "phrase": dd._trim(dd.fmt_number(r, 'plain', 1)) + "x"}


def cagr(start, end, years):
    if start <= 0 or end <= 0 or years <= 0:
        raise ValueError("cagr needs positive start, end and years")
    r = ((end / start) ** (1 / years) - 1) * 100
    return {"start": start, "end": end, "years": years, "cagr_pct": round(r, 2),
            "phrase": f"{dd._trim(dd.fmt_number(r, 'plain', 1))}% a year"}


def total(values):
    return {"values": values, "sum": sum(values)}


def annual(monthly):
    return {"monthly": monthly, "annual": monthly * 12}


def operand(sources, text):
    try:
        return float(text)
    except ValueError:
        v = dd.lookup(sources, text)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"{text} is not a number ({v!r})")
        return float(v)


OPS = {"change": (change, 2), "share": (share, 2), "ratio": (ratio, 2), "cagr": (cagr, 3),
       "annual": (annual, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="append", default=[])
    ap.add_argument("op", choices=sorted(list(OPS) + ["sum"]))
    ap.add_argument("args", nargs="+")
    a = ap.parse_args(argv)
    try:
        sources = dd.parse_data_args(a.data)
        vals = [operand(sources, x) for x in a.args]
        if a.op == "sum":
            out = total(vals)
        else:
            fn, n = OPS[a.op]
            if len(vals) != n:
                raise ValueError(f"{a.op} takes {n} values")
            out = fn(*vals)
    except (ValueError, dd.RefError, OSError) as e:
        print(json.dumps({"error": str(e)}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
