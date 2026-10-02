// Read-only: reads the bond cards already rendered on /bonds/listing/ and saves
// them as one JSON file through the browser's own download. Makes no network
// request and reads no token, cookie or account field. Run once per review.
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const rows = [];
for (const card of document.querySelectorAll('a[href^="/bonds/listing/"]')) {
  const lines = card.innerText.split('\n').map(clean).filter(Boolean);
  const at = (label) => lines.findIndex((l) => l === label);
  const iMat = at('Maturity left'), iInt = at('Interest'), iPri = at('Principal');
  const iMin = lines.findIndex((l) => l.startsWith('Min.'));
  const iYtm = lines.findIndex((l) => l === 'YTM' || l === 'YTM up to');
  if (iMat < 0 || iInt < 0 || iPri < 0 || iMin < 2 || iYtm < 0) continue; // not a live card
  const iSold = lines.findIndex((l) => /% Sold$/.test(l) || /units? left$/.test(l));
  const ytms = lines.slice(iYtm + 1, iMat).filter((l) => /%$/.test(l));
  const tags = lines.filter((l, i) => (i < iMin - 2 || (i > iMin && i < iYtm)) && i !== iSold);
  rows.push({
    href: card.getAttribute('href'),
    issuer: lines[iMin - 2],
    rating: lines[iMin - 1],
    min: lines[iMin],
    sold: iSold >= 0 ? lines[iSold] : '',
    ytm_label: lines[iYtm],
    ytm: ytms[0] || '',
    ytm_alt: ytms[1] || '',
    maturity_left: lines[iMat + 1] || '',
    interest: lines[iInt + 1] || '',
    principal: lines[iPri + 1] || '',
    tags,
  });
}
const live = document.body.innerText.match(/Live \((\d+)\)/);
const body = JSON.stringify(rows);
const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
const sha256 = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
const captured_at = new Date().toISOString();
const payload = JSON.stringify({
  schema: 1, captured_at, source: location.pathname,
  stated_live_count: live ? Number(live[1]) : null, sha256, rows,
});
const name = 'wint-listings-' + captured_at.replace(/[:.]/g, '-') + '.json';
const link = document.createElement('a');
link.href = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
link.download = name;
document.body.appendChild(link);
link.click();
link.remove();
JSON.stringify({ file: name, count: rows.length, sha256 });
