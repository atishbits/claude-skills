#!/usr/bin/env python3
"""The arithmetic and data plumbing behind a deck, so no number on a slide is
worked out or retyped by hand:

- number formatting (Indian or international grouping, lakh/crore or K/M/B
  compact forms, a currency prefix);
- shares of a whole that add up to exactly 100 (largest remainder);
- bar and column lengths relative to the largest value;
- data references: a slide can take its figures straight from a JSON or CSV
  file another tool wrote (`"items_from": {"ref": "spend:by_category"}`),
  instead of the model copying the numbers across.
"""
import csv
import math
import os

# ---------------------------------------------------------------- numbers


def _group_in(digits):
    """'1234567' -> '12,34,567' (Indian grouping: 3, then 2s)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def _group_intl(digits):
    out = []
    while len(digits) > 3:
        out.insert(0, digits[-3:])
        digits = digits[:-3]
    out.insert(0, digits)
    return ",".join(out)


def _fixed(v, decimals):
    """Round half away from zero, so 2.5 -> 3 and 0.125 at 2 places -> 0.13 as
    people expect, not Python's banker's rounding."""
    q = 10 ** decimals
    r = math.floor(abs(v) * q + 0.5 + 1e-9) / q
    return f"{r:.{decimals}f}"


def _trim(s):
    return s.rstrip("0").rstrip(".") if "." in s else s


COMPACT = {
    "lakh": [(1e7, "Cr"), (1e5, "L"), (1e3, "K")],
    "compact": [(1e9, "B"), (1e6, "M"), (1e3, "K")],
}


def fmt_number(value, style="in", decimals=None, prefix="", suffix=""):
    """A number as a slide shows it.

    style: "in" (12,34,567), "intl" (1,234,567), "plain" (1234567),
    "lakh" (12.3L, 4.5Cr), "compact" (1.2K, 3.4M). decimals: fixed places;
    None means 0 for whole numbers and large values, 1 for small fractions
    (and 1, trimmed, in the compact styles). A negative value gets a leading
    minus before the prefix: -₹1,200.
    """
    if value is None:
        return ""
    v = float(value)
    neg = v < 0
    a = abs(v)
    unit = ""
    if style in COMPACT:
        for size, mark in COMPACT[style]:
            if a >= size:
                a, unit = a / size, mark
                break
        if unit:
            body = _trim(_fixed(a, 1)) if decimals is None else _fixed(a, decimals)
        elif decimals is None:
            body = _trim(_fixed(a, 1)) if a < 10 else _fixed(a, 0)
        else:
            body = _fixed(a, decimals)
    else:
        if decimals is None:
            decimals = 0 if (a == int(a) or a >= 100) else 1
        s = _fixed(a, decimals)
        whole, _, frac = s.partition(".")
        if style == "in":
            whole = _group_in(whole)
        elif style == "intl":
            whole = _group_intl(whole)
        body = whole + ("." + frac if frac else "")
    if neg and float(body.replace(",", "") or 0) == 0:
        neg = False
    return ("-" if neg else "") + prefix + body + unit + suffix


def shares(values, decimals=0):
    """Each value's share of the total, in percent, rounded so the shares add
    up to exactly 100 (largest remainder). All zero -> all zero."""
    vals = [max(0.0, float(v)) for v in values]
    total = sum(vals)
    if total <= 0:
        return [0.0 for _ in vals]
    q = 10 ** decimals
    raw = [v / total * 100 * q for v in vals]
    floors = [math.floor(r) for r in raw]
    left = int(round(100 * q - sum(floors)))
    order = sorted(range(len(vals)), key=lambda i: (-(raw[i] - floors[i]), i))
    for i in order[:left]:
        floors[i] += 1
    return [f / q for f in floors]


def lengths(values):
    """Bar lengths in percent of the largest value (one decimal place)."""
    vals = [max(0.0, float(v)) for v in values]
    top = max(vals) if vals else 0
    if top <= 0:
        return [0.0 for _ in vals]
    return [round(v / top * 100, 1) for v in vals]


# ---------------------------------------------------------------- data refs


class RefError(ValueError):
    pass


def _num(text):
    """A CSV cell as a number when it reads as one (commas and a currency mark
    allowed), else the text unchanged."""
    if not isinstance(text, str):
        return text
    t = text.strip().replace(",", "").lstrip("₹$€£").strip()
    try:
        return float(t) if t else text
    except ValueError:
        return text


def load_source(path):
    """A data file as Python data: JSON as is, CSV as a list of row dicts with
    numeric cells converted."""
    import json
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return [{k: _num(v) for k, v in row.items()} for row in csv.DictReader(f)]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lookup(sources, ref):
    """'name:a.b.0.c' -> the value at that path in source `name`. A path
    segment that is all digits indexes a list."""
    if not isinstance(ref, str) or ":" not in ref:
        raise RefError(f"data ref {ref!r} must look like 'name:path.to.value'")
    name, _, path = ref.partition(":")
    if name not in sources:
        raise RefError(f"data ref {ref!r}: no data source named {name!r} "
                       f"(have: {', '.join(sorted(sources)) or 'none'})")
    cur = sources[name]
    for seg in [s for s in path.split(".") if s != ""]:
        if isinstance(cur, list):
            if not seg.lstrip("-").isdigit():
                raise RefError(f"data ref {ref!r}: {seg!r} is not a list index")
            i = int(seg)
            if not -len(cur) <= i < len(cur):
                raise RefError(f"data ref {ref!r}: index {i} out of range")
            cur = cur[i]
        elif isinstance(cur, dict):
            if seg not in cur:
                keys = ", ".join(list(cur)[:12])
                raise RefError(f"data ref {ref!r}: no key {seg!r} (keys: {keys})")
            cur = cur[seg]
        else:
            raise RefError(f"data ref {ref!r}: cannot go into {type(cur).__name__} at {seg!r}")
    return cur


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def items_from(sources, spec):
    """Label/value pairs for a bars, columns or share slide, from a data ref.

    spec: a ref string, or {"ref", "label": key, "value": key, "sort": "desc"|
    "asc", "top": N, "other": "Other", "abs": true, "only": [labels],
    "exclude": [labels]}. The target may be {label: number}, {label: {...}},
    [{...}] or [[label, number]].
    """
    if isinstance(spec, str):
        spec = {"ref": spec}
    data = lookup(sources, spec.get("ref"))
    lk, vk = spec.get("label", "label"), spec.get("value", "value")
    pairs = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                if vk not in v:
                    raise RefError(f"{spec['ref']}: entry {k!r} has no {vk!r}")
                v = v[vk]
            pairs.append((str(k), v))
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                if lk not in row or vk not in row:
                    raise RefError(f"{spec['ref']}: a row lacks {lk!r} or {vk!r} "
                                   f"(row keys: {', '.join(row)})")
                pairs.append((str(row[lk]), row[vk]))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                pairs.append((str(row[0]), row[1]))
            else:
                raise RefError(f"{spec['ref']}: cannot read a label and value from {row!r}")
    else:
        raise RefError(f"{spec['ref']}: expected a mapping or a list, got {type(data).__name__}")
    for label, v in pairs:
        if not _is_num(v):
            raise RefError(f"{spec['ref']}: value for {label!r} is not a number ({v!r})")
    if spec.get("abs"):
        pairs = [(lab, abs(v)) for lab, v in pairs]
    if spec.get("only"):
        keep = set(spec["only"])
        pairs = [p for p in pairs if p[0] in keep]
    if spec.get("exclude"):
        drop = set(spec["exclude"])
        pairs = [p for p in pairs if p[0] not in drop]
    if spec.get("sort") in ("desc", "asc"):
        pairs.sort(key=lambda p: p[1], reverse=spec["sort"] == "desc")
    top = spec.get("top")
    if top and len(pairs) > top:
        rest = pairs[top:]
        pairs = pairs[:top]
        if spec.get("other"):
            pairs.append((spec["other"], sum(v for _, v in rest)))
    return [{"label": lab, "value": v} for lab, v in pairs]


def rows_from(sources, spec):
    """Table rows from a list of row dicts: spec {"ref", "columns": [{"key",
    "label", "num"}], "sort_by", "desc", "top"}."""
    data = lookup(sources, spec.get("ref"))
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise RefError(f"{spec.get('ref')}: a table needs a list of rows")
    cols = spec.get("columns") or []
    if not cols:
        raise RefError("rows_from needs columns: [{\"key\": ..., \"label\": ...}]")
    rows = list(data)
    if spec.get("sort_by"):
        k = spec["sort_by"]
        rows.sort(key=lambda r: (r.get(k) is None, r.get(k)), reverse=bool(spec.get("desc")))
    if spec.get("top"):
        rows = rows[:spec["top"]]
    out = []
    for r in rows:
        missing = [c["key"] for c in cols if c["key"] not in r]
        if missing:
            raise RefError(f"{spec.get('ref')}: a row lacks {', '.join(missing)}")
        out.append([r[c["key"]] for c in cols])
    header = [{"label": c.get("label", c["key"]), "num": bool(c.get("num"))} for c in cols]
    return header, out


def resolve(deck, sources):
    """Replace every *_from reference in the deck with the figures it points
    to. Returns (deck, errors); the deck is changed in place and each resolved
    slide keeps a `_from` note saying where its numbers came from."""
    errors = []
    for n, s in enumerate(deck.get("slides", []), 1):
        try:
            if "items_from" in s:
                s["items"] = items_from(sources, s.pop("items_from"))
                s["_from"] = "data ref"
            if "values_from" in s:  # columns
                s["items"] = items_from(sources, s.pop("values_from"))
                s["_from"] = "data ref"
            if "rows_from" in s:
                spec = s.pop("rows_from")
                s["columns"], s["rows"] = rows_from(sources, spec)
                s["_from"] = spec.get("ref")
            for it in s.get("items", []) if isinstance(s.get("items"), list) else []:
                if isinstance(it, dict) and "value_from" in it:
                    v = lookup(sources, it.pop("value_from"))
                    if not _is_num(v):
                        raise RefError(f"value_from on {it.get('label')!r} is not a number ({v!r})")
                    it["value"] = v
                    s["_from"] = "data ref"
                if isinstance(it, dict) and "delta_from" in it:
                    v = lookup(sources, it.pop("delta_from"))
                    if not _is_num(v):
                        raise RefError(f"delta_from on {it.get('label')!r} is not a number ({v!r})")
                    it["delta_value"] = v
        except RefError as e:
            errors.append(f"slide {n}: {e}")
    return deck, errors


def parse_data_args(pairs, base_dir=None):
    """['spend=path/to/a.json', ...] -> {'spend': loaded data}."""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise RefError(f"--data {p!r} must be name=path")
        name, path = p.split("=", 1)
        if base_dir and not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        out[name] = load_source(path)
    return out
