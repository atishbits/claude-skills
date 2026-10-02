// Read-only: on a bond's detail page (/bonds/listing/<name>-<id>), opens the
// "Other bond details" panel and returns its Overview text: collateral, rating
// with outlook, rating agency and date, listed or not, seniority, maturity,
// coupon and ISIN. Clicks nothing else and makes no request of its own.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let row;
for (let i = 0; i < 20 && !row; i++) {
  row = [...document.querySelectorAll('p,span,div,h3,h4')].find(
    (e) => e.childElementCount === 0 && e.textContent.trim() === 'Other bond details');
  if (!row) await sleep(500);
}
if (row) { row.click(); await sleep(1500); }
const text = document.body.innerText;
const at = text.indexOf('Collateral Type');
(at < 0 ? 'NO PANEL ' : '') + location.pathname + ' :: ' +
  text.slice(Math.max(0, at), at + 900).replace(/\n+/g, ' | ');
