// hero-clip-probe.mjs — does the event hero's away column fit inside the phone? (#5866)
//
// live/193's `hero-headroom-probe.mjs` anchors the hero row on its computed flex triple
// (`1 1 0%` / `0 0 auto` / `1 1 0%`). That is the right anchor for REPORTING the defect and the
// wrong one for grading a FIX, because the fix changes the middle child's flex — the probe then
// reads `heroRowFound: false` on a repaired page and an unrepaired one alike.
//
// So this anchors on `[data-testid="event-hero-probability"]` (or the settled hero's block) and
// walks up to the three-child flex row that contains it. It reports the thing the reader actually
// suffers — how far past the viewport the away column sits — plus the same budget/used/headroom
// triple so the two probes can be compared line for line.
//
// PASS = awayOffscreenPx === 0 AND headroomPx >= 0.
//
// Usage: node hero-clip-probe.mjs <url> [widthPx]
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

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
if (!url) { console.error('usage: hero-clip-probe.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
// Proxy handling copied from `tools/shop-shot.mjs`, which is the only version of this that works
// for BOTH targets. The browser needs the session proxy to reach api.bainluck.com at all; but on a
// LOCAL target the `<-loopback>` bypass-list override must be omitted, or the request for
// localhost:3000 is sent through the proxy too and answered 503. Getting this wrong does not look
// like a proxy error — the page boots, renders its shell, and the probe reports "no hero anchor"
// about a page that is fine. Measured here: 501 characters of body text and one testid.
const localTarget = /localhost|127\.0\.0\.1/.test(url);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!localTarget) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
// The hero is client-rendered on a cold local server; wait for the anchor rather than a fixed
// sleep, then settle for animation.
await page.waitForSelector('[data-testid="event-hero-probability"], [data-testid="settled-outcome-hero"]', { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(4000);

const out = await page.evaluate(() => {
  const r2 = (n) => Math.round(n * 10) / 10;
  const vw = document.documentElement.clientWidth;

  const anchor = document.querySelector('[data-testid="event-hero-probability"]')
    || document.querySelector('[data-testid="settled-outcome-hero"]');
  if (!anchor) return { viewportWidth: vw, heroRowFound: false, reason: 'no hero anchor' };

  let row = anchor;
  while (row && row !== document.body) {
    const cs = getComputedStyle(row);
    if (row.children.length === 3 && cs.display === 'flex' && cs.flexDirection === 'row') break;
    row = row.parentElement;
  }
  if (!row || row === document.body) return { viewportWidth: vw, heroRowFound: false, reason: 'no 3-child flex row above the anchor' };

  const rb = row.getBoundingClientRect();
  const raw = [...row.children].map((k) => k.getBoundingClientRect());
  const [home, centre, away] = [...row.children].map((k, i) => ({
    w: r2(raw[i].width), left: r2(raw[i].left), right: r2(raw[i].right),
    flex: getComputedStyle(k).flex,
    text: (k.textContent || '').trim().slice(0, 60),
  }));

  // Budget and headroom from the RAW rects, rounded once at the end. Rounding
  // each width to 0.1 first and then subtracting manufactures a phantom −0.1px
  // on a row that fits exactly: 64.75 + 196.5 + 64.75 = 326 reads as
  // 64.8 + 196.5 + 64.8 = 326.1 against a row of 326.
  const budget = rb.width - raw[0].width - raw[2].width;
  return {
    viewportWidth: vw,
    heroRowFound: true,
    rowWidth: r2(rb.width), rowRight: r2(rb.right),
    home, centre, away,
    centreBudgetPx: r2(budget),
    centreUsedPx: r2(raw[1].width),
    headroomPx: r2(budget - raw[1].width),
    awayOffscreenPx: r2(Math.max(0, raw[2].right - vw)),
    docScrollWidth: document.documentElement.scrollWidth,
  };
});

console.log(JSON.stringify(out, null, 1));
await browser.close();
process.exit(out.heroRowFound && out.awayOffscreenPx === 0 && out.headroomPx >= 0 ? 0 : 1);
