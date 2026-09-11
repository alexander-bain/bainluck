#!/usr/bin/env node
// norefresh-shop.mjs <url> <outDir> <slug> — notice 42's no-refresh mystery shop.
//
// Opens the page ONCE and never reloads it, shooting on a schedule. That is the whole
// point of the pass: a live event page has to go Final BY ITSELF, on a tab a reader left
// open. `look.sh` cannot answer that — each invocation is a fresh load, which is exactly
// the case where a broken live-update path still photographs green.
//
// Reuses the launch args and the ORIGIN-SCOPED agent header from shop-shot.mjs (#4903:
// a context-wide extraHTTPHeaders fails every no-cors <img> and photographs a page with
// no crests).
//
// Capture is a plain viewport shot at each of `SECTIONS`, NOT the grown-viewport whole-page
// capture shop-shot.mjs uses. A no-refresh pass wants a screen a person can actually read,
// and shooting sections sidesteps #4664 (fullPage remounts the charts and catches Recharts
// at t=0) rather than working around it — nothing here resizes the viewport, so the charts
// are never remounted mid-pass on the one tab this tool exists to leave alone.
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync } from 'fs';
import { agentHeaderApplies } from './shot-click-contract.mjs';

// Same resolution as shop-shot.mjs: playwright lives in the npx cache, not in this repo.
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

const [url, outDir, slug] = process.argv.slice(2);
if (!url || !outDir || !slug) {
  console.error('usage: norefresh-shop.mjs <url> <outDir> <slug>');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const W = parseInt(process.env.SHOT_W || '390', 10);
const H = parseInt(process.env.SHOT_H || '844', 10);
// Minutes from launch at which to shoot. Kickoff-relative cadence per notice 42:
// pre/at kickoff, then every ~20 minutes through a ~3.5h NFL broadcast, so the tail
// covers the final and the +10 the directive asks for explicitly.
const MARKS = (process.env.SHOT_MARKS || '0,2,20,40,60,80,100,120,140,160,180,200,215,225,235,245')
  .split(',').map((m) => parseFloat(m.trim())).filter((m) => Number.isFinite(m));

// Scroll offsets shot at every mark: the scoreboard, the win-probability chart, and the
// head of the play feed / props. A live pass is watching the score, its age, and whether
// the page goes Final by itself — all of which sit in the first screens.
const SECTIONS = (process.env.SHOT_SECTIONS || '0,700,1500').split(',').map(Number);

const ptStamp = () => {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Los_Angeles', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date()).reduce((a, x) => (a[x.type] = x.value, a), {});
  return { date: `${p.year}${p.month}${p.day}`, hhmm: `${p.hour === '24' ? '00' : p.hour}${p.minute}` };
};
const log = (...m) => console.error(`[${new Date().toISOString()}]`, ...m);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
await page.route(
  (u) => agentHeaderApplies(u.toString()),
  (route) => route.continue({ headers: { ...route.request().headers(), 'x-bainluck-origin': process.env.BL_AGENT || 'look.sh' } }),
);

let imgResponded = 0;
let imgFailed = 0;
page.on('response', (r) => { if (r.request().resourceType() === 'image') imgResponded++; });
page.on('requestfailed', (r) => { if (r.resourceType() === 'image') imgFailed++; });

log(`LOADING ONCE: ${url}`);
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 }).catch((e) => log('goto warn:', e.message));
log('loaded; no further navigation will occur');

const t0 = Date.now();
for (const mark of MARKS) {
  const due = t0 + mark * 60000;
  const wait = due - Date.now();
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  const { date, hhmm } = ptStamp();
  try {
    // VIEWPORT shots at fixed offsets, never fullPage and never the grown whole page.
    // This event page is ~20,000px at 390px wide, which is over the grown-capture
    // ceiling — so the whole-page path degrades to Chromium's fullPage, which both
    // loses the chart (#4664) and produces a 50:1 strip no reader can judge. The
    // scoreboard, the win-probability chart and the top of the props all live in the
    // first three screens, and those are what a live pass is actually watching.
    const docHeight = await page.evaluate(() => document.documentElement.scrollHeight);
    for (const y of SECTIONS) {
      const out = `${outDir}/${date}-${slug}-${hhmm}PT-y${y}.png`;
      await page.evaluate((target) => window.scrollTo(0, target), y);
      await page.waitForTimeout(900);
      await page.screenshot({ path: out });
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    const blackout = await page.evaluate(() =>
      [...document.images].filter((i) => i.naturalWidth === 0).length);
    log(`SHOT t+${mark}m -> ${date}-${slug}-${hhmm}PT-y{${SECTIONS.join(',')}} doc=${docHeight} imgResp=${imgResponded} imgFail=${imgFailed} naturalWidth0=${blackout}`);
  } catch (e) {
    log(`SHOT t+${mark}m FAILED: ${e.message}`);
  }
}
log('schedule complete; closing');
await browser.close();
