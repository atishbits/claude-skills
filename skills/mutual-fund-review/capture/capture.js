// mutual-fund-review portal capture. Read-only.
//
// Paste the adapter JSON for this portal (from the user's data/adapters/) as
// ADAPTER below, then run the whole snippet in the logged-in portal tab. It
// reads the holdings rows already rendered on the page, optionally clicks each
// row's own expander to reveal its transactions (a UI click, nothing else),
// and saves one JSON file through the browser's own download.
//
// Guarantees: makes no network request (no fetch, XHR or beacon), reads no
// cookie, token, localStorage or sessionStorage, fills no field and presses no
// button other than a row expander named by the adapter. Folio numbers it
// reads are hashed away by ingest_capture.py before anything is stored.
//
// Adapter format (see adapter-example.json):
//   source, transactions_complete, row_selector, expand ("click" | null),
//   detail ("next_sibling" | CSS selector inside the row | null),
//   holding:     {field: spec}   fields: scheme isin folio plan option units invested current_value nav
//   transaction: {row_selector, fields: {field: spec}}   fields: date amount units nav type
//   A spec is one of: {"line": n} n-th non-empty text line of the scope,
//   {"label": "Units"} the line after that label, {"selector": css, "attr"?: name},
//   any of them with "regex" (first capture group kept).
(async () => {
  const ADAPTER = /* paste adapter JSON here */ null;
  if (!ADAPTER) throw new Error('paste the adapter JSON into ADAPTER first');
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const linesOf = (el) => (el ? el.innerText.split('\n').map(clean).filter(Boolean) : []);
  const pick = (scope, spec) => {
    if (!scope || !spec) return '';
    let v = '';
    if ('line' in spec) v = linesOf(scope)[spec.line] || '';
    else if ('label' in spec) {
      const ls = linesOf(scope);
      const i = ls.indexOf(spec.label);
      v = i >= 0 ? ls[i + 1] || '' : '';
    } else if ('selector' in spec) {
      const el = scope.querySelector(spec.selector);
      v = el ? (spec.attr ? el.getAttribute(spec.attr) || '' : clean(el.innerText)) : '';
    }
    if (spec.regex) {
      const m = new RegExp(spec.regex).exec(v);
      v = m ? m[1] : '';
    }
    return v;
  };
  const read = (scope, specs) =>
    Object.fromEntries(Object.entries(specs || {}).map(([k, s]) => [k, pick(scope, s)]));

  const holdings = [];
  const transactions = [];
  const rows = [...document.querySelectorAll(ADAPTER.row_selector)];
  for (const row of rows) {
    const h = read(row, ADAPTER.holding);
    let detail = null;
    if (ADAPTER.expand === 'click') {
      row.click();
      await sleep(ADAPTER.wait_ms || 2000);
    }
    if (ADAPTER.detail === 'next_sibling') detail = row.nextElementSibling;
    else if (ADAPTER.detail) detail = row.querySelector(ADAPTER.detail);
    if (detail) Object.assign(h, Object.fromEntries(
      Object.entries(read(detail, ADAPTER.holding_detail)).filter(([, v]) => v)));
    holdings.push(h);
    if (detail && ADAPTER.transaction) {
      for (const tr of detail.querySelectorAll(ADAPTER.transaction.row_selector)) {
        const t = read(tr, ADAPTER.transaction.fields);
        if (!t.date) continue;
        transactions.push({ ...t, scheme: h.scheme, isin: h.isin, folio: h.folio,
                            raw: linesOf(tr).join('\t') });
      }
    }
    if (ADAPTER.expand === 'click') {
      row.click(); // collapse again
      await sleep(500);
    }
  }
  const doc = { source: ADAPTER.source, captured_at: new Date().toISOString(),
                transactions_complete: !!ADAPTER.transactions_complete, holdings, transactions };
  const blob = new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${ADAPTER.source}-capture-${doc.captured_at.replace(/[:.]/g, '-')}.json`;
  a.click();
  return `${holdings.length} holdings, ${transactions.length} transactions saved to ${a.download}`;
})();
