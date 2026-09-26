// held-headline-vs-stream-8779.mjs — open ONE event page at phone width, never reload, and
// record the hero headline every second beside the page's own SSE frames (live/622, #8779).
// A nonvenue frame (source betting/stat_model/mlb/espn) proves its arm only if the headline
// the page is HOLDING moves to round(p*100) after it — a reload would read REST, not the push.
//
// usage: node tools/held-headline-vs-stream-8779.mjs <eventId> <outDir> <seconds>
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, appendFileSync } from 'fs';

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) for (const d of readdirSync(npx)) {
    const p = `${npx}/${d}/node_modules/`;
    if (existsSync(`${p}playwright`)) return p;
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');
const [eid, outDir, secs] = process.argv.slice(2);
if (!eid || !outDir) { console.error('usage: <eventId> <outDir> <seconds>'); process.exit(2); }
mkdirSync(outDir, { recursive: true });
const log = `${outDir}/held-${eid}.jsonl`;
const now = () => new Date().toISOString();
const out = (o) => appendFileSync(log, JSON.stringify({ t: now(), ...o }) + '\n');

// Same launch args as shop-shot.mjs (sandbox + session egress proxy); --single-process = one page.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
// The page's own EventSource: wrap it so every frame the PAGE receives is logged with its arrival time.
await page.exposeFunction('__frame', (d) => out({ kind: 'frame', data: d }));
await page.addInitScript(() => {
  const ES = window.EventSource;
  window.EventSource = function (u, o) {
    const es = new ES(u, o);
    es.addEventListener('message', (e) => window.__frame(e.data));
    return es;
  };
  window.EventSource.prototype = ES.prototype;
});
await page.goto(`https://bainluck.com/events/${eid}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(8000); // never networkidle: the page holds its stream open
const hero = async () => page.evaluate(() => {
  // The hero number is the largest-font "NN" + "%" in the first screen.
  let best = null;
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length) continue;
    const t = (el.textContent || '').trim();
    if (!/^\d{1,3}%?$/.test(t)) continue;
    const r = el.getBoundingClientRect();
    if (r.top > 400 || r.height === 0) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (!best || fs > best.fs) best = { fs, t };
  }
  return best && best.t;
});
let last = null, shots = 0;
const end = Date.now() + Number(secs || 180) * 1000;
while (Date.now() < end) {
  const h = await hero();
  if (h !== last) {
    out({ kind: 'headline', value: h });
    if (shots < 4) { await page.screenshot({ path: `${outDir}/held-${eid}-${now().slice(11, 19).replace(/:/g, '')}Z.png` }); shots++; }
    last = h;
  }
  await page.waitForTimeout(1000);
}
await page.screenshot({ path: `${outDir}/held-${eid}-end-${now().slice(11, 19).replace(/:/g, '')}Z.png` });
await browser.close();
