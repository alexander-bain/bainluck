// venue-vocab-onscreen-7397.mjs — WHERE does the venue's league word actually paint? (lane1b/#7397)
//
// The served payload for `/api/leagues/americanfootball_nfl` carries 33 strings matching
// /\bPro (Football|Basketball|Hockey|Baseball)\b/ across three keys. A payload key is not a
// reader: `_build_related_futures` taught me that the rail's own relabel was real in the
// helper and invisible in the served rail. So this asks the DOM, not the JSON — which of
// those strings is a text node a person can read, and at what y, so a LOOK can frame it.
//
// Prints one line per on-screen occurrence: y, the section heading above it, the text.
// Exit 0 with `ONSCREEN=0` is a real answer (payload carries it, reader never sees it), not
// a failure — that distinction is the entire point of running this before building.
//
// Usage: node tools/venue-vocab-onscreen-7397.mjs <url> [widthPx]
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';

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

const [url, widthArg] = process.argv.slice(2);
if (!url) { console.error('usage: venue-vocab-onscreen-7397.mjs <url> [width]'); process.exit(2); }
const width = Number(widthArg || 390);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width, height: 900 } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
// The league page hydrates its sections after the payload lands; give React a paint, then
// scroll the whole document so lazy sections mount before we walk the tree.
await page.waitForTimeout(2500);
await page.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 800) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 60));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1500);

const hits = await page.evaluate(() => {
  const re = /\bPro (Football|Basketball|Hockey|Baseball)\b/;
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = (n.textContent || '').trim();
    if (!t || !re.test(t)) continue;
    const el = n.parentElement;
    if (!el) continue;
    const r = el.getBoundingClientRect();
    // A node with no box is not painted: display:none, a <template>, or an aria-only string.
    if (r.width === 0 && r.height === 0) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    // Nearest heading ABOVE this node, so the line names the section a reader sees it under.
    let heading = '';
    const heads = Array.from(document.querySelectorAll('h1,h2,h3,h4,[class*="sectionTitle"],[class*="SectionTitle"]'));
    for (const h of heads) {
      const hr = h.getBoundingClientRect();
      if (hr.top + window.scrollY <= r.top + window.scrollY) heading = (h.textContent || '').trim().slice(0, 48);
    }
    out.push({ y: Math.round(r.top + window.scrollY), tag: el.tagName.toLowerCase(), heading, text: t.slice(0, 110) });
  }
  return out;
});

console.log(`URL=${url} WIDTH=${width}`);
console.log(`docHeight=${await page.evaluate(() => document.body.scrollHeight)}`);
console.log(`ONSCREEN=${hits.length}`);
for (const h of hits.sort((a, b) => a.y - b.y)) {
  console.log(`  y=${String(h.y).padStart(6)}  [${h.heading}]  ${h.text}`);
}
await browser.close();
