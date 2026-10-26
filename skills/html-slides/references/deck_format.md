# Deck format

A deck is one JSON file. `scripts/build_deck.py` checks it and renders it. Everything in this file
uses invented names and round numbers.

```json
{
  "title": "Where the money went",
  "subtitle": "Six months of spending",
  "author": "",
  "date": "2026-10-25",
  "id": "optional-fixed-id",
  "accent": "#2f6fde",
  "format": {"style": "in"},
  "data": {"spend": "/path/to/analysis.json"},
  "slides": [ ... ]
}
```

- `id`: if omitted, `<date>-<slug of title>`. Rebuilding the same id replaces the files and keeps
  the published link in the index.
- `format`: defaults for every number: `style` (`in`, `intl`, `lakh`, `compact`, `plain`),
  `decimals`, `prefix`, `suffix`. A slide's own `format` overrides it, and so does a stat item's.
  `"money": true` on a slide or stat item adds the profile's currency as the prefix.
- `data`: named data files (JSON or CSV). A relative path is relative to the deck file.
  `--data name=path` on the command line adds more.

## Fields every slide can have

| Field | Shown as |
|---|---|
| `type` | required: one of the types below |
| `title` | the heading. Write it as the insight ("Delivery doubled since June"), not a label ("Delivery"). Max 14 words |
| `kicker` | small caps label above the title, max 5 words |
| `subtitle` | one line under the title, max 32 words |
| `takeaway` | a highlighted line under the visual, max 22 words: the "so what" |
| `source` | small "Source:" footer. **Required** on `stats`, `bars`, `columns`, `share` and `table` |
| `notes` | speaker notes, hidden until N is pressed. Not counted against word limits |
| `format`, `money` | number formatting for this slide |
| `highlight` | `bars`, `columns`: labels or 0-based indexes drawn in the second colour |

Text fields accept `**bold**` and `==accent colour==`.

## Slide types

| Type | Use it for | Content |
|---|---|---|
| `title` | the opening slide | `title`, `subtitle`, `kicker`; shows the deck's author and date |
| `section` | a divider between parts | `title`, `subtitle` |
| `statement` | one big insight or number in words | `title` (large), `subtitle` |
| `bullets` | last resort for a list | `items`: up to 6 strings of up to 16 words |
| `stats` | 1–4 headline numbers | `items`: `{label, value \| value_from, delta, delta_from, tone}`. `tone` is `good`, `bad` or `neutral` and colours the delta |
| `bars` | comparing sizes across categories | `items`: `{label, value}` up to 10, or `items_from` |
| `columns` | one value over time | `items` up to 16, or `values_from` |
| `share` | parts of a whole | `items` up to 7, or `items_from`. Shares are computed to add up to 100%. `pct_decimals`, `show_values` |
| `blocks` | 2–6 concepts, options or findings | `items`: `{title, text, icon, tone}` (`tone`: good, bad, warn) |
| `flow` | a process or pipeline, left to right (top to bottom on a phone) | `steps`: `{title, text}` up to 6 |
| `layers` | an architecture stack | `layers`: `{title, text, items: [chip, ...]}` up to 6, 8 chips each |
| `compare` | 2–3 options side by side | `sides`: `{title, tag, points: [...]}`; `pick`: index or title of the recommended one |
| `timeline` | dates and milestones | `events`: `{when, title, text}` up to 7 |
| `table` | when exact figures matter | `columns`: names or `{label, num}`; `rows` up to 8 × 5, or `rows_from` |
| `quote` | a line from a source | `quote`, `by` |
| `svg` | any diagram the types above cannot draw | `svg`: one inline `<svg>` with a `viewBox`; `alt`. No scripts, event handlers, embedded HTML or remote images. Use `currentColor` and `var(--accent)`, `var(--ink-2)`, `var(--c2)`… so it follows light and dark |
| `sources` | the closing reference list | `items`: `{title, url, note}` |

## Taking figures from a data file

Never copy numbers from a file into the deck by hand. Point at them:

```json
{"type": "bars", "title": "Delivery is the second-biggest category", "money": true,
 "source": "spending check-up, Oct 2026",
 "items_from": {"ref": "spend:by_category", "sort": "desc", "top": 6, "other": "Other"}}
```

- `ref` is `name:path.to.value`; a number in the path indexes a list. Run
  `python3 scripts/inspect_data.py FILE --name NAME` to list the paths a file has.
- The target may be `{label: number}`, `{label: {...}}` with `value` naming the field,
  `[{...}]` with `label` and `value` naming the fields, or `[[label, number], ...]`.
- Options: `sort` (`desc`/`asc`), `top` (keep N), `other` (sum the rest under this label),
  `only` / `exclude` (lists of labels), `abs` (absolute values).
- `values_from` is the same thing for `columns`.
- On a stat item, `value_from` / `delta_from` take one number.
- On a table, `rows_from`: `{"ref", "columns": [{"key", "label", "num"}], "sort_by", "desc", "top"}`.

The built `<id>.json` keeps the deck with every reference replaced by its figures, so it rebuilds
anywhere without the data file.

For a figure in a sentence ("up 23%", "a third of"), run `scripts/calc.py` and use its `phrase`.

## Example

```json
{"title": "How the example skill works", "slides": [
  {"type": "title", "kicker": "Design", "title": "How the example skill works"},
  {"type": "layers", "title": "Four layers, one direction of flow", "layers": [
    {"title": "Inputs", "items": ["Export file", "Notes"]},
    {"title": "Scripts", "items": ["parse.py", "score.py"]},
    {"title": "Judgment", "items": ["Reading sources"]},
    {"title": "Output", "items": ["Report", "Ledger"]}]},
  {"type": "flow", "title": "A run in four steps", "steps": [
    {"title": "Load", "text": "Read the export"}, {"title": "Score", "text": "Script rates each row"},
    {"title": "Review", "text": "Model reads sources"}, {"title": "Write", "text": "One note per item"}]},
  {"type": "stats", "title": "Small and tested", "source": "repo file counts",
   "items": [{"label": "scripts", "value": 6}, {"label": "unit tests", "value": 40}]}
]}
```
