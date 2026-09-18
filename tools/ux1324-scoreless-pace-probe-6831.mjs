// ux1324-scoreless-pace-probe-6831.mjs <url> <payload.json> <out.png>
//
// #6831's AFTER-CHECK on the DEPLOYED bundle, against a manufactured specimen.
//
// WHY THE SPECIMEN IS MANUFACTURED. The defect's whole population is "a live game
// between kickoff and its first score" — a window of minutes per game that nobody
// can schedule, and tonight's marquee game (the one the issue was filed off) is
// long past it. A population you can only see for a few minutes per row is not
// absent; it is transient. So this probe loads the REAL production page with the
// REAL deployed JS, and fulfils ONE route — `/api/events/<id>/game-markets` — with
// the production payload whose `pace` block has been set to the scoreless shape
// the issue photographed (`total_scored 0`, `projected_total 0`). Nothing else on
// the page is touched: production's own fonts, layout, chart and every other fetch.
//
// Fulfil ONLY the route being pinned — catch-all-ing the API renders the page's
// ErrorBoundary, which reads exactly like a crash in the change under test.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 no points-map card
// in the DOM (the card never rendered — NOT a pass), 1 camera/navigation.
import { createRequire } from 'module';
import { existsSync, readdirSync, readFileSync } from 'fs';

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

const [url, payloadPath, out] = process.argv.slice(2);
if (!url || !payloadPath || !out) {
  console.error('usage: … <url> <payload.json> <out.png>');
  process.exit(2);
}
const body = readFileSync(payloadPath, 'utf8');

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width: 390, height: 900 },
  deviceScaleFactor: 2,
});
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });

let fulfilled = 0;
await page.route('**/api/events/*/game-markets*', (route) => {
  fulfilled += 1;
  return route.fulfill({ status: 200, contentType: 'application/json', body });
});

// `networkidle` is the wrong wait for a LIVE page: the event page re-polls every
// ~20s, so idle may never arrive and the camera times out on a page that rendered
// fine. Wait for the card's own heading instead, then settle.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.getByText('Points map', { exact: true }).first()
  .waitFor({ state: 'attached', timeout: 60000 });
await page.waitForTimeout(3000);

// The card is found by its own heading text, not by a class: a class is the
// thing most likely to have moved, and a heading that moved is a finding.
const found = await page.evaluate(() => {
  const heads = [...document.querySelectorAll('div,h2,h3')]
    .filter((e) => e.textContent.trim() === 'Points map');
  if (!heads.length) return null;
  let card = heads[0];
  for (let i = 0; i < 6 && card.parentElement; i += 1) {
    card = card.parentElement;
    if (card.className && /rounded/.test(String(card.className))) break;
  }
  card.scrollIntoView({ block: 'center' });
  const r = card.getBoundingClientRect();
  return { text: card.innerText, top: r.top, height: r.height };
});
if (!found) { console.error('NO POINTS-MAP CARD IN THE DOM — not a pass'); await browser.close(); process.exit(4); }

await page.waitForTimeout(600);
const box = await page.evaluate(() => {
  const heads = [...document.querySelectorAll('div,h2,h3')]
    .filter((e) => e.textContent.trim() === 'Points map');
  let card = heads[0];
  for (let i = 0; i < 6 && card.parentElement; i += 1) {
    card = card.parentElement;
    if (card.className && /rounded/.test(String(card.className))) break;
  }
  const r = card.getBoundingClientRect();
  return { x: Math.max(0, r.x - 8), y: Math.max(0, r.y - 8), width: Math.min(390, r.width + 16), height: r.height + 16 };
});

await page.screenshot({ path: out, clip: box });
console.log(`routes fulfilled: ${fulfilled}`);
console.log(`card text: ${JSON.stringify(found.text)}`);
console.log(out);
await browser.close();
