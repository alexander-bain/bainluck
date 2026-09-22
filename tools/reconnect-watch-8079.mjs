// reconnect-watch-8079.mjs — live/515, #836's RECONNECT criterion, on production, one held page.
//
// Descends from live/514's held_page_watch_prod.mjs (which proved venue -> hero/chart delivery on a
// held page). This rig answers the criterion live/514 did NOT pay: Alex's "Cover reconnection ...
// and honest fallback", and the issue's "Reconnect/backoff handling proven".
//
// WHAT IT DOES. It holds ONE page open for the whole run (never reloads, one `goto`) and drives the
// network underneath it through four phases, while sampling the DOM every 250 ms:
//
//   BASE          normal delivery — the positive control. If the page is not updating here, no
//                 later verdict means anything.
//   OFFLINE_SHORT offline for less than the controller's 60 s SILENCE_TIMEOUT_MS. EventSource is
//                 expected to retry by itself; this is the ADMITTED arm.
//   OFFLINE_LONG  offline for longer than SILENCE_TIMEOUT_MS. `liveStreamController.tick()` calls
//                 `stop()`, which is documented "Terminal. No reopen, ever."
//   AFTER         back online, long enough for several 32 s poll cycles.
//
// THE QUESTION THE LAST PHASE ASKS is the one that matters to a reader, and it is not "did the
// socket come back". `useLiveEventStream`'s contract is "a push path that dies must degrade to
// polling, never to a frozen number." So after a terminal stop the right answer is NOT a new
// stream — it is that the number keeps tracking the venue over HTTP, and that the freshness badge
// stops claiming push. A frozen hero, or a badge still saying `live · 3s ago` over a dead
// transport, is the defect.
//
// WHAT IT RECORDS, as JSONL, every line stamped from one `Date.now()` on this machine:
//   phase        phase boundaries, and the exact instant offline was toggled
//   request      every /api/events/... request the page makes, split stream vs poll by URL
//   sse          every `probability` / `reconnect` / `heartbeat` / `open` / `error` the page's OWN
//                EventSource sees, with the browser's receipt time and readyState at the time
//   visible      hero probability + printed numerals, freshness badge, sparkline label, and every
//                recharts line (vertex count + last vertex decoded through the y-axis ticks)
//
// Emitted only when something changed, so the file IS the list of visible changes — EXCEPT the
// badge, which is sampled into its own `badge` records because during an outage the badge's text
// is the honesty claim under test and its ticking is the signal, not noise.
//
// WHAT IT CANNOT PROVE: the iPhone client (SwiftUI); that the venue itself published during any
// given phase (join against a venue tap or the DB for that); anything about a real radio handoff —
// the cut here is a clean socket destruction, where a real phone's is lossy and gradual.
//
// Usage: node reconnect-watch-8079.mjs <page-url> <out-prefix>
import { createRequire } from 'module';
import { appendFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_ROOT ? process.env.PW_ROOT + '/node_modules/playwright' : 'playwright');

const url = process.argv[2];
const prefix = process.argv[3] || 'reconnect';
mkdirSync(dirname(prefix) || '.', { recursive: true });
const out = `${prefix}.jsonl`;
writeFileSync(out, '');
const emit = (o) => appendFileSync(out, JSON.stringify({ t: Date.now() / 1000, ...o }) + '\n');

// Phase plan, in seconds from the start of sampling. Both offline arms are deliberate:
// SHORT sits under SILENCE_TIMEOUT_MS (60 s) and LONG sits over it, so the run carries its own
// control for "the rig can see a recovery" rather than only its own failure case.
// SCALE shrinks the plan for a rig smoke test ONLY. At any SCALE but 1 the OFFLINE_LONG arm no
// longer crosses SILENCE_TIMEOUT_MS, so a scaled run proves the rig works and proves NOTHING about
// reconnect; every record it writes carries the scale so no later reader can mistake one.
const SCALE = Number(process.env.SCALE || 1);
const PHASES = [
  { name: 'BASE', until: 75, offline: false },
  { name: 'OFFLINE_SHORT', until: 100, offline: true },
  { name: 'RECOVER_SHORT', until: 175, offline: false },
  { name: 'OFFLINE_LONG', until: 270, offline: true },
  { name: 'AFTER', until: 420, offline: false },
].map((p) => ({ ...p, until: p.until * SCALE }));
// Reader frames: (phase, seconds-from-start). Each takes a headline shot and a plot shot at a real
// phone viewport, because codex's 19:27Z read of live/514's capture was that the single final
// screenshot sat below the plot and so showed neither.
const SHOTS = [60, 95, 165, 262, 330, 415].map((s) => s * SCALE);

const _proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const _args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (_proxy) { _args.push(`--proxy-server=${_proxy}`); _args.push('--proxy-bypass-list=<-loopback>'); }
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: _args,
});
// A real phone viewport. live/514 used 1700px tall, which is not a reader's frame.
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push({ t: Date.now() / 1000, text: m.text().slice(0, 200) }); });
page.on('requestfailed', (r) => {
  if (/\/api\//.test(r.url())) emit({ kind: 'request_failed', url: r.url().replace(/^https?:\/\/[^/]+/, ''), err: (r.failure() || {}).errorText });
});
page.on('request', (r) => {
  if (!/\/api\//.test(r.url())) return;
  const u = r.url().replace(/^https?:\/\/[^/]+/, '');
  // The discriminator the whole run turns on: a reopened STREAM vs a fallback POLL.
  const kindOf = /\/stream(\?|$)/.test(u) ? 'stream' : /\/history/.test(u) ? 'history' : 'poll';
  emit({ kind: 'request', which: kindOf, url: u });
});

// Observe the page's OWN EventSource. Not a second subscription — a wrapper that records what the
// page's transport actually receives, plus the readyState at receipt, which is what separates
// "EventSource is retrying" (CONNECTING=0) from "the browser has given up" (CLOSED=2).
await page.addInitScript(() => {
  window.__ev = [];
  window.__esList = [];
  const Orig = window.EventSource;
  if (!Orig) return;
  const Wrapped = function (u, init) {
    const es = new Orig(u, init);
    const idx = window.__esList.length;
    window.__esList.push(es);
    const rec = (type, extra) => window.__ev.push({ t: Date.now() / 1000, es: idx, type, rs: es.readyState, ...extra });
    rec('constructed', { url: String(u) });
    for (const type of ['open', 'error', 'heartbeat', 'reconnect', 'closed']) {
      es.addEventListener(type, () => rec(type));
    }
    es.addEventListener('probability', (e) => rec('probability', { data: e.data }));
    return es;
  };
  Wrapped.prototype = Orig.prototype;
  Wrapped.CONNECTING = 0; Wrapped.OPEN = 1; Wrapped.CLOSED = 2;
  window.EventSource = Wrapped;
});

emit({ kind: 'goto', url });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForSelector('[data-testid=event-hero-probability]', { timeout: 60000 });
// Dismiss the consent banner, which otherwise sits over the bottom third of the plot in every
// reader frame. Decline rather than Accept: it is the choice that stores least, and the frame under
// test is the chart, not the consent state.
try {
  const decline = page.locator('button', { hasText: /^\s*decline\s*$/i }).first();
  if (await decline.count()) { await decline.click({ timeout: 4000 }); emit({ kind: 'consent', action: 'declined' }); }
} catch { emit({ kind: 'consent', action: 'absent_or_unclickable' }); }
await page.waitForTimeout(2000);

// Where the headline and the plot actually are, measured rather than guessed.
const geom = await page.evaluate(() => {
  const hero = document.querySelector('[data-testid=event-hero-probability]');
  const chart = document.querySelector('.recharts-wrapper');
  const box = (n) => { if (!n) return null; const r = n.getBoundingClientRect(); return { top: r.top + window.scrollY, bottom: r.bottom + window.scrollY, h: r.height }; };
  return { hero: box(hero), chart: box(chart), vh: window.innerHeight };
});
emit({ kind: 'geometry', ...geom });

const shot = async (tag) => {
  // Two frames, because at a phone viewport the headline and the plot are not in one.
  try {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${prefix}-${tag}-headline.png` });
    const y = geom.chart ? Math.max(0, Math.round(geom.chart.top - 60)) : 600;
    await page.evaluate((yy) => window.scrollTo(0, yy), y);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${prefix}-${tag}-plot.png` });
    emit({ kind: 'shot', tag, plotScrollY: y });
  } catch (e) { emit({ kind: 'shot_error', tag, error: String(e).slice(0, 200) }); }
};

const sample = () => page.evaluate(() => {
  const hero = document.querySelector('[data-testid=event-hero-probability]');
  const heroText = hero ? hero.textContent.replace(/\s+/g, ' ').trim() : null;
  const heroProb = hero ? hero.getAttribute('data-probability') : null;
  const badge = [...document.querySelectorAll('span,div')].map((n) => n.textContent || '')
    .find((t) => /^(live|stale|updated)\s*·\s*\d+\s*[smh]\s*ago$/i.test(t.trim())) || null;
  const spark = document.querySelector('[data-testid=live-sparkline]');
  const sparkLabel = spark ? spark.getAttribute('aria-label') : null;
  const w = document.querySelector('.recharts-wrapper');
  let lines = null;
  if (w) {
    const tickPairs = [...w.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick')].map((g) => {
      const t = g.querySelector('.recharts-cartesian-axis-tick-value');
      const label = t ? t.textContent.trim() : '';
      const pct = /^-?[\d.]+%$/.test(label) ? parseFloat(label) : null;
      const y = t ? +(t.getAttribute('y') ?? NaN) : NaN;
      return pct === null || !Number.isFinite(y) ? null : { pct, y };
    }).filter(Boolean).sort((a, b) => a.y - b.y);
    let f = null;
    if (tickPairs.length >= 2) { const a = tickPairs[0], b = tickPairs[tickPairs.length - 1]; if (b.y !== a.y) f = (y) => a.pct + ((y - a.y) * (b.pct - a.pct)) / (b.y - a.y); }
    lines = [...w.querySelectorAll('.recharts-line')].map((g) => {
      const path = g.querySelector('.recharts-line-curve');
      const d = path ? path.getAttribute('d') || '' : '';
      const pts = [...d.matchAll(/([-\d.]+),([-\d.]+)/g)].map((m) => [+m[1], +m[2]]);
      // live/514: identity is stroke-WIDTH, not colour. Blend is 3, a source line is 1 dashed,
      // and both are green — reading colour here filed two near-miss defects.
      const sw = path ? path.getAttribute('stroke-width') : null;
      const last = pts.length && f ? Math.round(f(pts[pts.length - 1][1]) * 10) / 10 : null;
      return { sw, vertices: pts.length, last };
    });
  }
  return { heroProb, heroText, badge: badge ? badge.trim() : null, sparkLabel, lines };
});

// THE CUT. Not `context.setOffline`: that was measured in tools/
// (sse-cut-instrument-check-8079.mjs) to block only NEW requests while an established SSE stream kept
// receiving heartbeats at readyState 1 straight through a 50 s "outage". Every reconnect verdict
// here would have been fabricated by that. `killable-proxy-8079.mjs` destroys the sockets instead, which
// is what losing signal does. CUT_VIA=offline reproduces the broken instrument on purpose.
const CUT_VIA = process.env.CUT_VIA || 'proxy';
const cutNetwork = async (on) => {
  if (CUT_VIA !== 'proxy') { await context.setOffline(on); emit({ kind: 'cut', via: 'offline', on }); return; }
  const r = await fetch(`http://127.0.0.1:${process.env.PROXY_PORT || 10555}/__${on ? 'cut' : 'restore'}`);
  emit({ kind: 'cut', via: 'proxy', on, body: await r.json() });
};

const t0 = Date.now();
const el = () => (Date.now() - t0) / 1000;
let phaseIdx = -1;
let offline = false;
let lastKey = null;
let lastBadge = null;
let seenEv = 0;
let shotIdx = 0;

emit({ kind: 'start', scale: SCALE, cut_via: CUT_VIA, phases: PHASES, shots: SHOTS });
while (el() < PHASES[PHASES.length - 1].until) {
  const now = el();
  // Advance the phase, toggling the network exactly once per boundary.
  let want = 0;
  while (want < PHASES.length - 1 && now >= PHASES[want].until) want += 1;
  if (want !== phaseIdx) {
    phaseIdx = want;
    const p = PHASES[phaseIdx];
    if (p.offline !== offline) {
      await cutNetwork(p.offline);
      offline = p.offline;
    }
    emit({ kind: 'phase', phase: p.name, offline, elapsed: Math.round(now) });
  }
  if (shotIdx < SHOTS.length && now >= SHOTS[shotIdx]) {
    await shot(`${String(SHOTS[shotIdx]).padStart(3, '0')}s-${PHASES[phaseIdx].name}`);
    shotIdx += 1;
  }

  let s;
  try {
    const ev = await page.evaluate(() => window.__ev || []);
    for (const e of ev.slice(seenEv)) {
      emit({ kind: 'sse', ...e, frame: e.data ? JSON.parse(e.data) : undefined, phase: PHASES[phaseIdx].name });
    }
    seenEv = ev.length;
    s = await sample();
  } catch (e) {
    emit({ kind: 'sample_error', error: String(e).slice(0, 200), phase: PHASES[phaseIdx].name });
    await page.waitForTimeout(250);
    continue;
  }
  // The badge is the honesty claim under test during an outage, so it gets its own record rather
  // than being excluded from the change key the way live/514 excluded it as noise.
  if (s.badge !== lastBadge) { emit({ kind: 'badge', badge: s.badge, phase: PHASES[phaseIdx].name }); lastBadge = s.badge; }
  const key = JSON.stringify({ ...s, badge: undefined });
  if (key !== lastKey) { emit({ kind: 'visible', ...s, phase: PHASES[phaseIdx].name }); lastKey = key; }
  await page.waitForTimeout(250);
}

if (offline) await cutNetwork(false);
await shot('final');
emit({ kind: 'done', consoleErrors: consoleErrors.slice(0, 20) });
await browser.close();
