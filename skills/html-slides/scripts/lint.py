#!/usr/bin/env python3
"""Checks a deck before it is built. Errors stop the build; warnings are
reported and the deck is still built.

- each slide type has the fields it needs, and data slides have numbers;
- text stays slide-sized: word limits per field and per slide, item counts;
- every slide that shows figures says where they came from (`source`);
- no identifiers on a slide: card numbers (full, passing the Luhn check, or
  masked), PAN, Aadhaar, or long digit runs that look like account numbers;
- an svg diagram carries no script.
"""
import re

TYPES = {"title", "section", "statement", "bullets", "stats", "bars", "columns", "share",
         "blocks", "flow", "layers", "compare", "timeline", "table", "quote", "svg", "sources"}
DATA_TYPES = {"stats", "bars", "columns", "share", "table"}

LIMITS = {
    "title_words": 14, "sub_words": 32, "takeaway_words": 22, "kicker_words": 5,
    "bullets": 6, "bullet_words": 16,
    "stats": 4, "stat_label_words": 8,
    "bars": 10, "columns": 16, "share": 7, "item_label_words": 6,
    "blocks": 6, "block_words": 28,
    "steps": 6, "step_words": 20,
    "layers": 6, "chips": 8,
    "sides": 3, "side_points": 5, "point_words": 14,
    "events": 7, "event_words": 16,
    "table_rows": 8, "table_cols": 5,
    "quote_words": 40, "notes_words": 200,
    "slide_words_warn": 70, "slide_words_max": 110,
}

REQUIRED = {
    "title": ["title"], "section": ["title"], "statement": ["title"],
    "bullets": ["title", "items"], "stats": ["title", "items"], "bars": ["title", "items"],
    "columns": ["title", "items"], "share": ["title", "items"], "blocks": ["title", "items"],
    "flow": ["title", "steps"], "layers": ["title", "layers"], "compare": ["title", "sides"],
    "timeline": ["title", "events"], "table": ["title", "columns", "rows"],
    "quote": ["quote"], "svg": ["title", "svg"], "sources": ["title", "items"],
}


def words(text):
    if not isinstance(text, str):
        return 0
    return len(re.findall(r"[^\s*=]+", text))


def luhn_ok(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


CARD_RUN = re.compile(r"(?<![\d.])(?:\d[ -]?){12,18}\d(?![\d.])")
MASKED = re.compile(r"(?:\d{0,6}[ -]?)?(?:[xX*\u2022]{4}[ -]?){1,3}\d{4}(?!\d)|\bXX\d{4}(?!\d)")
PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR = re.compile(r"\b[2-9][0-9]{3}[ -][0-9]{4}[ -][0-9]{4}\b")
LONG_DIGITS = re.compile(r"(?<![\d.,])\d{9,18}(?![\d.,])")


def identifier_problems(text):
    """(errors, warnings) for one string. URLs are skipped for the long-digit
    warning, since IDs in links are common and harmless."""
    errs, warns = [], []
    if not isinstance(text, str) or not text:
        return errs, warns
    for m in CARD_RUN.finditer(text):
        d = re.sub(r"\D", "", m.group(0))
        if 13 <= len(d) <= 19 and luhn_ok(d):
            errs.append(f"a card number (ending {d[-4:]})")
    if MASKED.search(text):
        errs.append("a masked card or account number")
    if PAN.search(text):
        errs.append("a PAN")
    if AADHAAR.search(text):
        errs.append("an Aadhaar number")
    plain = re.sub(r"https?://\S+", "", text)
    for m in LONG_DIGITS.finditer(plain):
        if not errs:
            warns.append(f"a {len(m.group(0))}-digit number that may be an account number")
    return errs, warns


def walk_strings(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "svg":
                continue
            yield from walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


SKIP_KEYS = {"notes", "source", "type", "id", "format", "url", "tone", "icon", "_from",
             "highlight", "pick", "num"}


def slide_words(s):
    """Words a viewer reads on the slide: everything but notes, the source line
    and settings."""
    total = 0
    for path, text in walk_strings(s):
        last = re.sub(r"\[\d+\]$", "", path.rsplit(".", 1)[-1])
        first = re.sub(r"\[\d+\]$", "", path.split(".", 1)[0])
        if last in SKIP_KEYS or first in SKIP_KEYS:
            continue
        total += words(text)
    return total


def check_slide(n, s):
    e, w = [], []
    where = f"slide {n}"
    t = s.get("type")
    if t not in TYPES:
        return [f"{where}: unknown type {t!r} (use one of {', '.join(sorted(TYPES))})"], []
    for f in REQUIRED[t]:
        if s.get(f) in (None, "", []):
            e.append(f"{where} ({t}): needs {f!r}")
    if e:
        return e, w
    L = LIMITS

    def cap(field_words, limit, label):
        if field_words > limit:
            e.append(f"{where}: {label} has {field_words} words (max {limit}) — cut it")

    def count(seq, limit, label):
        if len(seq) > limit:
            e.append(f"{where}: {len(seq)} {label} (max {limit}) — split the slide or group the rest")

    cap(words(s.get("title")), L["title_words"], "the title")
    cap(words(s.get("subtitle") or s.get("sub")), L["sub_words"], "the subtitle")
    cap(words(s.get("takeaway")), L["takeaway_words"], "the takeaway")
    cap(words(s.get("kicker")), L["kicker_words"], "the kicker")
    cap(words(s.get("notes")), L["notes_words"], "the notes")
    items = s.get("items") if isinstance(s.get("items"), list) else []

    if t == "bullets":
        count(items, L["bullets"], "bullets")
        for it in items:
            cap(words(it if isinstance(it, str) else ""), L["bullet_words"], f"bullet {it!r:.40}")
            if not isinstance(it, str):
                e.append(f"{where}: each bullet is a string")
    elif t == "stats":
        count(items, L["stats"], "stats")
        for it in items:
            if not isinstance(it, dict) or "value" not in it or not it.get("label"):
                e.append(f"{where}: each stat needs a value (or value_from) and a label")
                continue
            if not (_is_num(it["value"]) or isinstance(it["value"], str)):
                e.append(f"{where}: stat {it.get('label')!r} value must be a number or text")
            cap(words(it.get("label")), L["stat_label_words"], f"stat label {it.get('label')!r}")
            if it.get("tone") not in (None, "good", "bad", "neutral"):
                e.append(f"{where}: tone is good, bad or neutral")
    elif t in ("bars", "columns", "share"):
        count(items, L[t], f"{t} items")
        for it in items:
            if not isinstance(it, dict) or not _is_num(it.get("value")) or "label" not in it:
                e.append(f"{where}: each item needs a label and a numeric value "
                         f"(use items_from to take them from a data file)")
                break
            if it["value"] < 0:
                e.append(f"{where}: {it['label']!r} is negative; {t} slides show sizes, so show "
                         f"the change on a stats slide or plot the absolute value")
                break
            cap(words(str(it["label"])), L["item_label_words"], f"label {it['label']!r}")
    elif t == "blocks":
        count(items, L["blocks"], "blocks")
        for it in items:
            if not isinstance(it, dict) or not it.get("title"):
                e.append(f"{where}: each block needs a title")
                continue
            cap(words(it.get("title")) + words(it.get("text")), L["block_words"],
                f"block {it.get('title')!r}")
    elif t == "flow":
        count(s["steps"], L["steps"], "steps")
        for it in s["steps"]:
            if not isinstance(it, dict) or not it.get("title"):
                e.append(f"{where}: each step needs a title")
                continue
            cap(words(it.get("title")) + words(it.get("text")), L["step_words"],
                f"step {it.get('title')!r}")
    elif t == "layers":
        count(s["layers"], L["layers"], "layers")
        for it in s["layers"]:
            if not isinstance(it, dict) or not it.get("title"):
                e.append(f"{where}: each layer needs a title")
                continue
            count(it.get("items") or [], L["chips"], f"items in layer {it.get('title')!r}")
    elif t == "compare":
        count(s["sides"], L["sides"], "sides")
        if len(s["sides"]) < 2:
            e.append(f"{where}: compare needs at least 2 sides")
        for it in s["sides"]:
            if not isinstance(it, dict) or not it.get("title"):
                e.append(f"{where}: each side needs a title")
                continue
            pts = it.get("points") or []
            count(pts, L["side_points"], f"points in {it.get('title')!r}")
            for p in pts:
                cap(words(p), L["point_words"], f"point {p!r:.40}")
    elif t == "timeline":
        count(s["events"], L["events"], "events")
        for it in s["events"]:
            if not isinstance(it, dict) or not it.get("when") or not it.get("title"):
                e.append(f"{where}: each event needs when and title")
                continue
            cap(words(it.get("title")) + words(it.get("text")), L["event_words"],
                f"event {it.get('title')!r}")
    elif t == "table":
        cols, rows = s["columns"], s["rows"]
        if len(cols) > L["table_cols"]:
            e.append(f"{where}: {len(cols)} columns (max {L['table_cols']})")
        count(rows, L["table_rows"], "rows")
        for r in rows:
            if not isinstance(r, list) or len(r) != len(cols):
                e.append(f"{where}: every row needs {len(cols)} cells")
                break
    elif t == "quote":
        cap(words(s.get("quote")), L["quote_words"], "the quote")
    elif t == "svg":
        svg = s["svg"]
        if not isinstance(svg, str) or not svg.lstrip().lower().startswith("<svg"):
            e.append(f"{where}: svg must be one <svg>...</svg> element")
        elif re.search(r"(?i)<script|<foreignobject|\son\w+\s*=|javascript:|<iframe|<image[^>]+href=\s*['\"]?https?:", svg):
            e.append(f"{where}: svg may not contain scripts, event handlers, embedded HTML or remote images")
    elif t == "sources":
        for it in items:
            if not isinstance(it, dict) or not it.get("title"):
                e.append(f"{where}: each source needs a title (and a url when it has one)")
                break
            if it.get("url") and not re.match(r"https?://", it["url"]):
                e.append(f"{where}: source url must start with http(s)://")

    if t in DATA_TYPES and not str(s.get("source") or "").strip():
        e.append(f"{where} ({t}): says where its figures come from — add a short 'source'")

    total = slide_words(s)
    if total > L["slide_words_max"]:
        e.append(f"{where}: {total} words on one slide (max {L['slide_words_max']})")
    elif total > L["slide_words_warn"]:
        w.append(f"{where}: {total} words — a slide reads best under {L['slide_words_warn']}")
    return e, w


def check_deck(deck, max_slides=16):
    errors, warnings = [], []
    if not isinstance(deck, dict) or not isinstance(deck.get("slides"), list) or not deck["slides"]:
        return ["the deck needs a non-empty 'slides' list"], []
    if not str(deck.get("title") or "").strip():
        errors.append("the deck needs a 'title'")
    acc = deck.get("accent")
    if acc is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(acc)):
        errors.append("accent must be a #rrggbb colour")
    slides = deck["slides"]
    for n, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            errors.append(f"slide {n}: must be an object")
            continue
        e, w = check_slide(n, s)
        errors += e
        warnings += w
    if len(slides) > max_slides:
        warnings.append(f"{len(slides)} slides; the profile's limit is {max_slides}. Cut or merge.")
    if isinstance(slides[0], dict) and slides[0].get("type") != "title":
        warnings.append("slide 1 is not a title slide")
    seen = {}
    for n, s in enumerate(slides, 1):
        if isinstance(s, dict) and s.get("title"):
            seen.setdefault(s["title"].strip().lower(), []).append(n)
    for t, ns in seen.items():
        if len(ns) > 1:
            warnings.append(f"slides {', '.join(map(str, ns))} share the title {t!r}")
    for path, text in walk_strings(deck):
        e, w = identifier_problems(text)
        errors += [f"{path}: {x} — never put an identifier on a slide" for x in e]
        warnings += [f"{path}: {x}" for x in w]
    return errors, warnings
