// boot-rail-probe.mjs — DOES the parse-time boot rail fire for this reader? (latency/137)
//
// The felt rig times pages. This answers a prior, binary question the felt numbers can only hint at:
// for a given localStorage state, does the inline boot script issue its request, or does it bail out?
//
// 🔴 WHY NOT INFER IT FROM RESOURCE TIMING. `firstApiStart < lastScriptEnd` looks like a boot-fired
// signal and is not one: `lastScriptEnd` is when the last script finished DOWNLOADING, several other
// requests leave early for reasons of their own, and on an unthrottled link everything bunches inside
// 200 ms. So this reads the two things that cannot be argued with — whether the request carried
// `x-session-id` (the boot's fetch sends no headers; the app's always sends one for a session
// principal), and whether `window.__blFeedBoot` / `__blHubBoot` was ever parked on the document.
//
// Usage: node tools/boot-rail-probe.mjs <url> ['{"localStorage":"seed"}']
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

const [url, seedArg] = process.argv.slice(2);
if (!url) { console.error('usage: boot-rail-probe.mjs <url> [seedJson]'); process.exit(2); }
const seed = seedArg ? JSON.parse(seedArg) : {};

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
const page = await browser.newPage();

// Seed BEFORE any page script, then capture the boot slot the instant it is parked. The app deletes
// the slot when it claims it (`claimBootFeed` deletes unconditionally), so reading it after load would
// report "no boot" for a boot that fired and was consumed exactly as designed.
await page.addInitScript(`(() => {
  const SEED = ${JSON.stringify(seed)};
  try { for (const k in SEED) window.localStorage.setItem(k, SEED[k]); } catch (e) {}
  window.__PROBE = { parked: [] };
  for (const slot of ['__blFeedBoot', '__blHubBoot']) {
    let v;
    Object.defineProperty(window, slot, {
      configurable: true,
      get() { return v; },
      set(x) { v = x; window.__PROBE.parked.push({ slot, url: x && x.url }); },
    });
  }
})()`);

const reqs = [];
page.on('request', (r) => {
  const u = r.url();
  if (!/api\.bainluck\.com\/api\/(feed|tournaments)/.test(u)) return;
  const h = r.headers();
  reqs.push({ url: u.replace(/^https?:\/\/[^/]+/, ''), sessionId: h['x-session-id'] ?? null, auth: !!h['authorization'] });
});

await page.goto(url, { waitUntil: 'load', timeout: 120000 });
try { await page.waitForLoadState('networkidle', { timeout: 30000 }); } catch {}

const probe = await page.evaluate('window.__PROBE');
const keys = await page.evaluate('(() => { const o=[]; for(let i=0;i<localStorage.length;i++) o.push(localStorage.key(i)); return o.sort(); })()');

console.log(JSON.stringify({
  url,
  seeded: Object.keys(seed),
  seedApplied: Object.keys(seed).every((k) => keys.includes(k)),
  bootParked: probe.parked,
  bootFired: probe.parked.length > 0,
  apiRequests: reqs,
  localStorageAtEnd: keys,
}, null, 2));

await browser.close();
