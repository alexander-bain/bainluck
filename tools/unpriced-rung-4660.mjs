/**
 * #4660 — find a rung that prints "—" beside a VISIBLE red bar.
 *
 * The defect signature, read off the rendered page rather than the payload:
 * a QuantityGroup row whose number cell is an em-dash while its fill carries
 * `bg-accent-danger` at a non-zero width. Prints one line per hit.
 *
 * Exit 0 = clean (no hit), 3 = the defect is present, 2 = usage.
 */
import { existsSync, readdirSync } from 'fs';
import { createRequire } from 'module';
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');
const url = process.argv[2];
const width = Number(process.argv[3] || 390);
if (!url) { console.error('usage: unpriced-rung-4660.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const b = await chromium.launch({ headless: true, args });
const pg = await b.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
await pg.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
for (let y = 0; y < 14; y++) { await pg.evaluate((n) => window.scrollTo(0, n * 800), y); await pg.waitForTimeout(250); }
await pg.waitForTimeout(1200);

const hits = await pg.evaluate(() => {
  const out = [];
  // The fill span QuantityGroup draws inside its track.
  for (const fill of document.querySelectorAll('span.block.h-full.rounded-md')) {
    const row = fill.closest('[aria-label]');
    if (!row) continue;
    const label = row.getAttribute('aria-label') || '';
    const w = parseFloat(fill.style.width) || 0;
    const cls = fill.className;
    // "Above 76: —" — the number cell said we do not know.
    const unpriced = /:\s*—\s*$/.test(label);
    out.push({ label, width: w, cls, unpriced, painted: w > 0 });
  }
  return out;
});

// POSITIVE CONTROL. A probe that finds no ROWS AT ALL is not reporting a clean
// page, it is reporting that it did not run — the two must never print the same
// line (gotcha #53). Say how many rungs were examined, always.
console.log(`examined ${hits.length} rung(s) on ${url}`);
if (!hits.length) { console.log('BLIND: no QuantityGroup rung found — the probe proved nothing'); await b.close(); process.exit(4); }
const unpricedHits = hits.filter((h) => h.unpriced);
console.log(`  ${unpricedHits.length} of them unpriced`);
let bad = 0;
for (const h of unpricedHits) {
  const danger = /accent-danger/.test(h.cls);
  const verdict = h.painted ? (danger ? 'DEFECT red-and-visible' : 'painted non-danger') : 'ok no-fill';
  if (h.painted && danger) bad++;
  console.log(`${verdict.padEnd(24)} width=${String(h.width).padEnd(5)} ${h.label}`);
}
console.log(`--- ${unpricedHits.length} unpriced rung(s), ${bad} painted red`);
await b.close();
process.exit(bad ? 3 : 0);
