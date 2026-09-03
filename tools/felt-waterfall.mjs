// felt-waterfall.mjs — WHERE the seconds go on one cold load, request by request.
//
// felt-load.mjs answers "how long until a real card". It does not answer "what was the page waiting
// for", and on a phone-class connection those have different answers: Chrome's Slow-4G profile is
// 1.6 Mbit/s with a **562 ms round trip**, so one extra sequential request costs more than 100 KB of
// extra bytes. A byte-cut aimed at a round-trip problem is a ship that moves nothing.
//
// This prints every request on the critical path with start/end relative to navigation, so the next
// latency ship is chosen against the waterfall rather than against a hunch about bundle size.
//
//   node tools/felt-waterfall.mjs https://www.bainluck.com/ slow4g
import { createRequire } from 'module';
import { existsSync, readdirSync, writeFileSync } from 'fs';

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

// Identical to felt-load.mjs's table, on purpose: a waterfall measured under a different throttle
// than the number it is explaining is not an explanation of that number.
const THROTTLE = {
  slow4g: { downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8, latency: 562.5 },
  fast4g: { downloadThroughput: 9 * 1024 * 1024 / 8, uploadThroughput: 1.5 * 1024 * 1024 / 8, latency: 170 },
  none: null,
};

const url = process.argv[2] || 'https://www.bainluck.com/';
const throttleKey = process.argv[3] || 'slow4g';
const cpu = Number(process.env.FELT_CPU || 4);
const outJson = process.argv[4] || null;

// Same launch args and same egress proxy as felt-load.mjs. `--single-process` is not a preference:
// without it Chromium cannot check in with the Mach port rendezvous server under this sandbox and
// dies before the first navigation. And a run that bypassed the session proxy would be measuring a
// different network from every other number in the felt table.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const baseArgs = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) baseArgs.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args: baseArgs });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
await cdp.send('Network.enable');
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
if (THROTTLE[throttleKey]) await cdp.send('Network.emulateNetworkConditions', { offline: false, ...THROTTLE[throttleKey] });
if (cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });

const reqs = new Map();
let t0 = null;
cdp.on('Network.requestWillBeSent', (e) => {
  if (t0 === null) t0 = e.timestamp;
  reqs.set(e.requestId, { url: e.request.url, start: (e.timestamp - t0) * 1000, initiator: e.initiator?.type });
});
cdp.on('Network.responseReceived', (e) => {
  const r = reqs.get(e.requestId);
  if (r) { r.headersAt = (e.timestamp - t0) * 1000; r.status = e.response.status; }
});
cdp.on('Network.loadingFinished', (e) => {
  const r = reqs.get(e.requestId);
  if (r) { r.end = (e.timestamp - t0) * 1000; r.bytes = e.encodedDataLength; }
});

await page.goto(url, { waitUntil: 'commit', timeout: 120000 });
// Wait for the felt moment, not for the network: `networkidle` includes polling and lazy images and
// would report a page as slow because it keeps working after the reader is already reading.
await page.waitForTimeout(12000);

const paints = await page.evaluate(() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const fcp = performance.getEntriesByType('paint').find((p) => p.name === 'first-contentful-paint');
  return { fcp: fcp ? fcp.startTime : null, domContentLoaded: nav.domContentLoadedEventEnd, responseStart: nav.responseStart, requestStart: nav.requestStart };
});

const rows = [...reqs.values()].filter((r) => r.end != null).sort((a, b) => a.start - b.start);
const short = (u) => u.replace(/^https?:\/\//, '').replace(/\?.*$/, '').slice(0, 62);
console.log(`\n${url}  throttle=${throttleKey} cpu=${cpu}x   FCP=${Math.round(paints.fcp)} ms  DCL=${Math.round(paints.domContentLoaded)} ms\n`);
console.log('  start     end    dur   bytes  status  resource');
for (const r of rows) {
  console.log(
    `${String(Math.round(r.start)).padStart(7)} ${String(Math.round(r.end)).padStart(7)} ` +
    `${String(Math.round(r.end - r.start)).padStart(6)} ${String(r.bytes ?? '').padStart(7)} ` +
    `${String(r.status ?? '').padStart(6)}  ${short(r.url)}`
  );
}
// Hostname equality, not `url.includes(...)`: a substring test would also match
// `https://evil.example/?x=api.bainluck.com`, and a waterfall that mislabels which request is the
// API call names the wrong thing as the critical path.
const isApiHost = (u) => {
  try {
    return new URL(u).hostname === 'api.bainluck.com';
  } catch {
    return false;
  }
};
const api = rows.filter((r) => isApiHost(r.url));
if (api.length) {
  const firstApi = api[0];
  console.log(`\nFIRST API CALL starts at ${Math.round(firstApi.start)} ms, ${Math.round(firstApi.start - paints.fcp)} ms AFTER first paint — that gap is hydration, and it is dead time on the critical path.`);
}
if (outJson) writeFileSync(outJson, JSON.stringify({ url, throttle: throttleKey, cpu, paints, rows }, null, 2));
await browser.close();
