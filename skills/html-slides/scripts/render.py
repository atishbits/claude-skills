#!/usr/bin/env python3
"""Turns a checked deck (see references/deck_format.md) into one
self-contained HTML file, using assets/deck.html. Every length, share and
formatted number is computed here by deckdata; the template only lays out
what it is given."""
import html
import re

import deckdata as dd

ARROW = ('<svg viewBox="0 0 40 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h32M27 5l8 7-8 7"/></svg>')
PALETTE = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)"]


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def inline(s):
    """Escaped text with **strong** and ==accent== marks turned into tags."""
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"==(.+?)==", r'<span class="em">\1</span>', out)
    return out


class Fmt:
    """Number formatting for one slide: the deck's settings overlaid with the
    slide's `format`, and `money: true` as shorthand for the currency prefix."""

    def __init__(self, deck_fmt, slide):
        f = dict(deck_fmt)
        f.update(slide.get("format") or {})
        if slide.get("money") or f.pop("money", False):
            f.setdefault("prefix", f.get("currency", ""))
        self.currency = f.get("currency", "")
        self.style = f.get("style", "in")
        self.decimals = f.get("decimals")
        self.prefix = f.get("prefix", "")
        self.suffix = f.get("suffix", "")

    def __call__(self, v):
        if isinstance(v, str):
            return v
        return dd.fmt_number(v, self.style, self.decimals, self.prefix, self.suffix)


def _hl(slide):
    h = slide.get("highlight")
    if h is None:
        return set()
    return set(h if isinstance(h, list) else [h])


def _is_hl(hl, i, label):
    return i in hl or label in hl


def head(s):
    parts = []
    if s.get("kicker"):
        parts.append(f'<div class="kicker">{inline(s["kicker"])}</div>')
    if s.get("title"):
        parts.append(f'<h2>{inline(s["title"])}</h2>')
    if s.get("subtitle") or s.get("sub"):
        parts.append(f'<div class="sub">{inline(s.get("subtitle") or s.get("sub"))}</div>')
    return "".join(parts)


def foot(s):
    parts = []
    if s.get("takeaway"):
        parts.append(f'<div class="takeaway">{inline(s["takeaway"])}</div>')
    if s.get("notes"):
        parts.append(f'<div class="notes">{inline(s["notes"])}</div>')
    if s.get("source"):
        parts.append(f'<div class="source">Source: {inline(s["source"])}</div>')
    return "".join(parts)


def r_title(s, deck, fmt):
    meta = " · ".join(esc(x) for x in [deck.get("author"), deck.get("date")] if x)
    k = f'<div class="kicker">{inline(s["kicker"])}</div>' if s.get("kicker") else ""
    sub = f'<div class="sub">{inline(s.get("subtitle") or s.get("sub"))}</div>' if (s.get("subtitle") or s.get("sub")) else ""
    m = f'<div class="meta">{meta}</div>' if meta else ""
    return f'<div class="bar"></div>{k}<h1>{inline(s["title"])}</h1>{sub}{m}', False


def r_section(s, deck, fmt):
    k = f'<div class="kicker">{inline(s["kicker"])}</div>' if s.get("kicker") else ""
    sub = f'<div class="sub">{inline(s.get("subtitle") or s.get("sub"))}</div>' if (s.get("subtitle") or s.get("sub")) else ""
    return f'<div class="bar"></div>{k}<h1>{inline(s["title"])}</h1>{sub}', False


def r_statement(s, deck, fmt):
    k = f'<div class="kicker">{inline(s["kicker"])}</div>' if s.get("kicker") else ""
    sub = f'<div class="sub">{inline(s.get("subtitle") or s.get("sub"))}</div>' if (s.get("subtitle") or s.get("sub")) else ""
    return f'{k}<h1>{inline(s["title"])}</h1>{sub}', False


def r_bullets(s, deck, fmt):
    lis = "".join(f"<li><span>{inline(b)}</span></li>" for b in s["items"])
    return f'<ul class="bullets">{lis}</ul>', True


def r_stats(s, deck, fmt):
    out = []
    for it in s["items"]:
        f = Fmt(_fmt_dict(fmt), it) if (it.get("format") or it.get("money")) else fmt
        delta = ""
        if it.get("delta") or "delta_value" in it:
            d = it.get("delta")
            if d is None:
                dv = it["delta_value"]
                d = ("+" if dv > 0 else "") + Fmt(_fmt_dict(fmt), {"format": it.get("delta_format") or {}})(dv)
            tone = it.get("tone") or "neutral"
            delta = f'<div class="delta {tone}">{inline(d)}</div>'
        out.append(f'<div class="stat"><div class="value">{esc(f(it["value"]))}</div>'
                   f'<div class="label">{inline(it["label"])}</div>{delta}</div>')
    return f'<div class="stats">{"".join(out)}</div>', True


def _fmt_dict(fmt):
    return {"style": fmt.style, "decimals": fmt.decimals, "prefix": fmt.prefix,
            "suffix": fmt.suffix, "currency": fmt.currency}


def r_bars(s, deck, fmt):
    items = s["items"]
    lens = dd.lengths([it["value"] for it in items])
    hl = _hl(s)
    rows = []
    for i, (it, ln) in enumerate(zip(items, lens)):
        cls = "bar-row hl" if _is_hl(hl, i, it["label"]) else "bar-row"
        rows.append(f'<div class="{cls}"><div class="lab" title="{esc(it["label"])}">{inline(it["label"])}</div>'
                    f'<div class="track"><div class="fill" style="width:{ln}%"></div></div>'
                    f'<div class="val">{esc(fmt(it["value"]))}</div></div>')
    return f'<div class="bars">{"".join(rows)}</div>', True


def r_columns(s, deck, fmt):
    items = s["items"]
    lens = dd.lengths([it["value"] for it in items])
    hl = _hl(s)
    cols, labs = [], []
    for i, (it, ln) in enumerate(zip(items, lens)):
        cls = "col hl" if _is_hl(hl, i, it["label"]) else "col"
        cols.append(f'<div class="{cls}"><div class="cv">{esc(fmt(it["value"]))}</div>'
                    f'<div class="cb" style="height:{ln}%"></div></div>')
        labs.append(f'<span title="{esc(it["label"])}">{inline(it["label"])}</span>')
    return (f'<div><div class="cols">{"".join(cols)}</div>'
            f'<div class="col-labels">{"".join(labs)}</div></div>'), True


def r_share(s, deck, fmt):
    items = s["items"]
    pct = dd.shares([it["value"] for it in items], s.get("pct_decimals", 0))
    segs, leg = [], []
    for i, (it, p) in enumerate(zip(items, pct)):
        c = "var(--c6)" if str(it["label"]).lower() in ("other", "others", "rest") else PALETTE[i % 5]
        segs.append(f'<div style="width:{p}%;background:{c}" title="{esc(it["label"])}"></div>')
        p_txt = dd.fmt_number(p, "plain", s.get("pct_decimals", 0)) + "%"
        val = f' <span class="neutral">· {esc(fmt(it["value"]))}</span>' if s.get("show_values", True) else ""
        leg.append(f'<div><i style="background:{c}"></i><span>{inline(it["label"])}{val}</span><b>{p_txt}</b></div>')
    return f'<div class="share-bar">{"".join(segs)}</div><div class="legend">{"".join(leg)}</div>', True


def r_blocks(s, deck, fmt):
    out = []
    for i, it in enumerate(s["items"]):
        tone = it.get("tone")
        color = {"good": "var(--good)", "bad": "var(--bad)", "warn": "var(--warn)"}.get(tone, PALETTE[i % 5])
        icon = f'<div class="bi" aria-hidden="true">{esc(it["icon"])}</div>' if it.get("icon") else ""
        text = f'<p>{inline(it["text"])}</p>' if it.get("text") else ""
        out.append(f'<div class="block" style="--bc:{color}">{icon}<h3>{inline(it["title"])}</h3>{text}</div>')
    return f'<div class="blocks">{"".join(out)}</div>', True


def r_flow(s, deck, fmt):
    out = []
    for i, st in enumerate(s["steps"]):
        if i:
            out.append(f'<div class="arrow" aria-hidden="true">{ARROW}</div>')
        text = f'<p>{inline(st["text"])}</p>' if st.get("text") else ""
        out.append(f'<div class="step"><div class="n">{i + 1}</div><h3>{inline(st["title"])}</h3>{text}</div>')
    return f'<div class="flow">{"".join(out)}</div>', True


def r_layers(s, deck, fmt):
    out = []
    for i, ly in enumerate(s["layers"]):
        chips = "".join(f'<span class="chip">{inline(c)}</span>' for c in ly.get("items") or [])
        note = f'<div class="neutral" style="font-size:.78em">{inline(ly["text"])}</div>' if ly.get("text") else ""
        out.append(f'<div class="layer" style="--lc:{PALETTE[i % 5]}"><h3>{inline(ly["title"])}</h3>'
                   f'<div>{note}<div class="chips">{chips}</div></div></div>')
    return f'<div class="layers">{"".join(out)}</div>', True


def r_compare(s, deck, fmt):
    out = []
    for i, sd in enumerate(s["sides"]):
        pick = s.get("pick") in (i, sd.get("title")) or sd.get("pick")
        tag = f'<span class="tag">{inline(sd["tag"])}</span>' if sd.get("tag") else ""
        pts = "".join(f"<li>{inline(p)}</li>" for p in sd.get("points") or [])
        out.append(f'<div class="side{" pick" if pick else ""}"><h3><span>{inline(sd["title"])}</span>{tag}</h3>'
                   f'<ul>{pts}</ul></div>')
    return f'<div class="compare">{"".join(out)}</div>', True


def r_timeline(s, deck, fmt):
    out = []
    for ev in s["events"]:
        text = f'<p>{inline(ev["text"])}</p>' if ev.get("text") else ""
        out.append(f'<div class="event"><div class="when">{inline(ev["when"])}</div>'
                   f'<h3>{inline(ev["title"])}</h3>{text}</div>')
    return f'<div class="timeline">{"".join(out)}</div>', True


def r_table(s, deck, fmt):
    cols = [c if isinstance(c, dict) else {"label": c} for c in s["columns"]]
    num = [bool(c.get("num")) for c in cols]
    for j in range(len(cols)):
        if "num" not in cols[j]:
            num[j] = all(isinstance(r[j], (int, float)) and not isinstance(r[j], bool) for r in s["rows"])
    th = "".join(f'<th class="num">{inline(c["label"])}</th>' if num[j] else f'<th>{inline(c["label"])}</th>'
                 for j, c in enumerate(cols))
    trs = []
    for r in s["rows"]:
        tds = "".join(f'<td class="num">{esc(fmt(v))}</td>' if num[j] and not isinstance(v, str)
                      else f'<td>{inline(v)}</td>' for j, v in enumerate(r))
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="tbl-wrap"><table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>', True


def r_quote(s, deck, fmt):
    by = f'<div class="by">— {inline(s["by"])}</div>' if s.get("by") else ""
    return f'<blockquote>{inline(s["quote"])}</blockquote>{by}', False


def r_svg(s, deck, fmt):
    label = esc(s.get("alt") or s.get("title"))
    svg = s["svg"].strip()
    if "role=" not in svg[:200]:
        svg = svg.replace("<svg", f'<svg role="img" aria-label="{label}"', 1)
    return f'<div class="diagram">{svg}</div>', True


def r_sources(s, deck, fmt):
    lis = []
    for it in s["items"]:
        t = inline(it["title"])
        if it.get("url"):
            t = f'<a href="{esc(it["url"])}" target="_blank" rel="noopener noreferrer">{t}</a>'
        d = f' <span class="d">— {inline(it["note"])}</span>' if it.get("note") else ""
        lis.append(f"<li>{t}{d}</li>")
    return f'<ol class="srcs">{"".join(lis)}</ol>', True


RENDER = {"title": r_title, "section": r_section, "statement": r_statement, "bullets": r_bullets,
          "stats": r_stats, "bars": r_bars, "columns": r_columns, "share": r_share,
          "blocks": r_blocks, "flow": r_flow, "layers": r_layers, "compare": r_compare,
          "timeline": r_timeline, "table": r_table, "quote": r_quote, "svg": r_svg,
          "sources": r_sources}


def render_slide(n, s, deck, deck_fmt):
    fmt = Fmt(deck_fmt, s)
    body, with_head = RENDER[s["type"]](s, deck, fmt)
    title = s.get("title") or s.get("quote") or f"Slide {n}"
    inner = (head(s) if with_head else "") + body + foot(s)
    return (f'<section class="slide t-{s["type"]}" id="s{n}" data-title="{esc(re.sub(r"[*=]{2}", "", title))}">'
            f'<div class="inner">{inner}</div></section>')


def render_deck(deck, template, profile):
    deck_fmt = {"style": profile.get("number_style", "in"), "currency": profile.get("currency", "")}
    deck_fmt.update(deck.get("format") or {})
    slides = "\n".join(render_slide(n, s, deck, deck_fmt) for n, s in enumerate(deck["slides"], 1))
    accent = deck.get("accent") or profile.get("accent") or "#2f6fde"
    desc = deck.get("description") or deck.get("subtitle") or ""
    return (template.replace("{{TITLE}}", esc(deck["title"]))
            .replace("{{DESCRIPTION}}", esc(desc))
            .replace("{{ACCENT}}", accent)
            .replace("{{SLIDES}}", slides))
