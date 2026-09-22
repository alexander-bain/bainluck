// sse-cut-instrument-check-8079.mjs — live/515. Does `context.setOffline(true)` actually SEVER an
// already-established SSE stream, or does it only block NEW requests?
//
// WHY THIS EXISTS BEFORE THE REAL RUN. The whole reconnect measurement turns on the page genuinely
// losing its transport. If offline emulation blocks new connections but leaves the open EventSource
// streaming, then an OFFLINE_LONG arm would sail through with heartbeats arriving the whole time
// and I would report "the page survived a 95 s outage" — the instrument's failure mode and the
// happy result are the same picture. So: establish the stream, cut for 50 s, and watch the
// HEARTBEAT, which the server emits every ~20 s. Three heartbeats in a 50 s window means the cut
// did not happen and this rig cannot ask the question.
//
// PASS  = heartbeats stop during the cut, and/or the stream request fails.
// FAIL  = heartbeats keep arriving across the cut (offline is cosmetic here; find another cut).
import { createRequire } from 'module';
import { appendFileSync, writeFileSync } from 'fs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_ROOT ? process.env.PW_ROOT + '/node_modules/playwright' : 'playwright');

const url = process.argv[2];
const out = process.argv[3] || 'instrument-check.jsonl';
writeFileSync(out, '');
const emit = (o) => appendFileSync(out, JSON.stringify({ t: Date.now() / 1000, ...o }) + '\n');

const _proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const _args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (_proxy) { _args.push(`--proxy-server=${_proxy}`); _args.push('--proxy-bypass-list=<-loopback>'); }
const browser = await chromium.launch({ headless: true, args: _args });
const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await context.newPage();
page.on('requestfailed', (r) => { if (/\/api\//.test(r.url())) emit({ kind: 'request_failed', url: r.url().replace(/^https?:\/\/[^/]+/, ''), err: (r.failure() || {}).errorText }); });
page.on('request', (r) => { if (/\/api\/events\/\d+\/stream/.test(r.url())) emit({ kind: 'stream_request' }); });

await page.addInitScript(() => {
  window.__ev = [];
  const Orig = window.EventSource;
  if (!Orig) return;
  const W = function (u, init) {
    const es = new Orig(u, init);
    const rec = (type) => window.__ev.push({ t: Date.now() / 1000, type, rs: es.readyState });
    for (const type of ['open', 'error', 'heartbeat', 'reconnect', 'closed', 'probability']) es.addEventListener(type, () => rec(type));
    return es;
  };
  W.prototype = Orig.prototype; W.CONNECTING = 0; W.OPEN = 1; W.CLOSED = 2;
  window.EventSource = W;
});

await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForSelector('[data-testid=event-hero-probability]', { timeout: 60000 });

let seen = 0;
const drain = async (phase) => {
  const ev = await page.evaluate(() => window.__ev || []);
  for (const e of ev.slice(seen)) emit({ kind: 'sse', ...e, phase });
  seen = ev.length;
};

// 45 s of normal running first: long enough to bank at least two heartbeats as the BASELINE rate.
// Without that baseline, "no heartbeats during the cut" could just mean the server never sends any.
const until = async (secs, phase) => {
  const end = Date.now() + secs * 1000;
  while (Date.now() < end) { await drain(phase); await page.waitForTimeout(500); }
};
// CUT_VIA=proxy uses killable-proxy-8079.mjs, which destroys the actual sockets. CUT_VIA=offline is the
// original CDP path, kept so the comparison stays reproducible rather than being a claim in prose.
const CUT_VIA = process.env.CUT_VIA || 'offline';
const ctl = async (what) => {
  if (CUT_VIA !== 'proxy') return context.setOffline(what === 'cut');
  const r = await fetch(`http://127.0.0.1:${process.env.PROXY_PORT || 10555}/__${what}`);
  emit({ kind: 'proxy_ctl', what, body: await r.json() });
};
emit({ kind: 'phase', phase: 'BASE', cut_via: CUT_VIA });
await until(45, 'BASE');
emit({ kind: 'phase', phase: 'CUT' });
await ctl('cut');
await until(50, 'CUT');
await ctl('restore');
emit({ kind: 'phase', phase: 'RESTORED' });
await until(30, 'RESTORED');
emit({ kind: 'done' });
await browser.close();
