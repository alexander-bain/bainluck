// held-headline-vs-stream-8779.mjs — open ONE event page at phone width, never reload, and
// record what the PAGE itself receives and renders, all on one in-page monotonic clock
// (performance.now(); `wall` = performance.timeOrigin + mono, for joins to DB clocks) (#8779).
//
//   frame      every `probability` SSE frame the page's own EventSource receives — p, source,
//              source_value, clock (frame updated_at), status — stamped BEFORE the page's handler
//              runs (our listener is registered in the constructor, ahead of the page's).
//              The backend emits NAMED events only (event_stream.py: event="probability";
//              liveStreamController.ts listens 'probability'). live/622's version listened
//              'message', which never fires for a named event — its JSONL held zero frames.
//   rest       every /api/events/<id>[/...] response the page's fetch receives: sent / headers /
//              body-received mono and the body itself (saved under rest/), so a concurrent REST
//              refresh can be excluded, not assumed away.
//   headline   hero number mutations (MutationObserver), plus `headline_painted` two rAFs later.
//   chart      main-chart (win-probability-card SVG) mutations, plus `chart_painted`.
//   shot       a saved screenshot on each headline change, with the mono it was taken at.
//
// On exit it writes held-<id>-attribution.json: for each headline/chart change, the latest frame
// whose round(p*100) (or its complement) equals the new headline, and the REST responses whose
// body arrived between that frame and the mutation. A change is `push` only when a matching
// frame precedes it and NO watched REST body arrived in that window.
//
// usage: node tools/held-headline-vs-stream-8779.mjs <eventId> <outDir> <seconds>
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, appendFileSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';

const USAGE = 'usage: node tools/held-headline-vs-stream-8779.mjs <eventId> <outDir> <seconds>';
const [eid, outDir, secs] = process.argv.slice(2);
if (eid === '--help' || eid === '-h') { console.log(USAGE); process.exit(0); }
if (!eid || !outDir) { console.error(USAGE); process.exit(2); }

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) for (const d of readdirSync(npx)) {
    const p = `${npx}/${d}/node_modules/`;
    if (existsSync(`${p}playwright`)) return p;
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');
mkdirSync(`${outDir}/rest`, { recursive: true });
const log = `${outDir}/held-${eid}.jsonl`;
const out = (o) => appendFileSync(log, JSON.stringify({ t: new Date().toISOString(), ...o }) + '\n');

// Same launch args as shop-shot.mjs (sandbox + session egress proxy); --single-process = one page.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });

// Everything is stamped IN the page and buffered on window.__held; Node drains it. An exposed
// binding would stamp on Node's clock after an IPC hop, which is not the page's clock.
await page.addInitScript(() => {
  const held = (window.__held = []);
  const M = () => performance.now();
  const W = () => performance.timeOrigin + performance.now();
  const push = (o) => held.push({ mono: M(), wall: W(), ...o });

  const ES = window.EventSource;
  class HeldEventSource extends ES {
    constructor(u, o) {
      super(u, o);
      const url = String(u);
      push({ kind: 'stream_new', url });
      this.addEventListener('open', () => push({ kind: 'stream_open', url }));
      this.addEventListener('error', () => push({ kind: 'stream_error', url, readyState: this.readyState }));
      this.addEventListener('probability', (e) => {
        const rec = { kind: 'frame', url };
        try {
          const f = JSON.parse(e.data);
          Object.assign(rec, { event_id: f.event_id, p: f.p, source: f.source,
            source_value: f.source_value, clock: f.updated_at, status: f.status });
        } catch { rec.raw = String(e.data).slice(0, 500); }
        push(rec);
      });
      for (const name of ['heartbeat', 'reconnect', 'closed', 'message']) {
        this.addEventListener(name, (e) => push({ kind: `stream_${name}`, url, data: String(e.data ?? '').slice(0, 200) }));
      }
    }
  }
  window.EventSource = HeldEventSource;

  const WATCH = /\/api\/events\/\d+(?:[/?]|$)/;
  const F = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || String(input);
    const sent_mono = M();
    const res = await F.call(this, input, init);
    if (WATCH.test(url)) {
      const headers_mono = M();
      res.clone().text().then(
        (body) => push({ kind: 'rest', url, status: res.status, sent_mono, headers_mono, body_mono: M(), body }),
        (err) => push({ kind: 'rest', url, status: res.status, sent_mono, headers_mono, body_error: String(err) }),
      );
    }
    return res;
  };

  // The hero number is the largest-font "NN" / "NN%" leaf in the first screen (live/622's rule).
  const heroNow = () => {
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
    return best ? best.t : null;
  };
  // The main chart line: OddsChart draws the headline series (the blend line, or the sportsbooks
  // line when betting is the only source) at strokeWidth 3 and every other source thinner. Not
  // "the longest path": two series of near-equal length swap that title as x drifts (live/624's
  // second run flipped last_y between two series every frame). Keyed on point count and LAST y
  // only — the x domain ends at "now", so each re-render nudges every x by a few thousandths.
  const chartNow = () => {
    const card = document.querySelector('[data-testid="win-probability-card"]');
    if (!card) return null;
    const lines = [...card.querySelectorAll('path.recharts-line-curve')];
    const main = lines.filter((p) => p.getAttribute('stroke-width') === '3' && !p.closest('.recharts-gap-connector'));
    const n = lines.length;
    const d = main.length ? main[main.length - 1].getAttribute('d') || '' : '';
    const nums = d.match(/-?\d+(?:\.\d+)?/g) || [];
    const points = (d.match(/[MLCQ]/gi) || []).length;
    const lastY = nums.length ? Number(nums[nums.length - 1]) : null;
    return { key: `${n}|${points}|${lastY == null ? '' : lastY.toFixed(1)}`, paths: n, points, last_y: lastY, d_tail: d.slice(-80) };
  };
  const painted = (kind, extra) =>
    requestAnimationFrame(() => requestAnimationFrame(() => push({ kind, ...extra })));

  let lastHero, lastChart;
  const check = () => {
    const h = heroNow();
    if (h !== lastHero) {
      push({ kind: 'headline', value: h, prev: lastHero ?? null });
      painted('headline_painted', { value: h });
      lastHero = h;
    }
    const c = chartNow();
    const ck = c ? c.key : null;
    if (ck !== lastChart) {
      push({ kind: 'chart', paths: c?.paths ?? 0, points: c?.points ?? 0, last_y: c?.last_y ?? null, d_tail: c?.d_tail ?? null });
      painted('chart_painted', { points: c?.points ?? 0, last_y: c?.last_y ?? null });
      lastChart = ck;
    }
  };
  const start = () => {
    check();
    new MutationObserver(check).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  };
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start, { once: true });
});

// Node-side cross-check only: a watched response the in-page fetch wrap did not see (XHR, a
// service worker) would otherwise be an unexcluded REST path.
const netSeen = [];
page.on('response', (r) => {
  if (/\/api\/events\/\d+(?:[/?]|$)/.test(r.url()) && !/\/stream(?:[?]|$)/.test(r.url())) netSeen.push({ url: r.url(), status: r.status() });
});
// The stream's own HTTP story, Node-side (EventSource hides status and failure text from the
// page): the status of every (re)connect and the net:: error of every drop. Without it a page
// that fell back to polling cannot say whether the server refused, the router cut, or the
// sandbox proxy did.
// Node-clock records (no mono): they fire after goto, by which time `records` exists.
const note = (o) => { records.push(o); out(o); };
const STREAM = /\/api\/events\/\d+\/stream(?:[?]|$)/;
page.on('response', (r) => { if (STREAM.test(r.url())) note({ kind: 'stream_http', status: r.status(), url: r.url() }); });
page.on('requestfailed', (r) => { if (STREAM.test(r.url())) note({ kind: 'stream_failed', error: r.failure()?.errorText ?? null, url: r.url() }); });
page.on('requestfinished', (r) => { if (STREAM.test(r.url())) note({ kind: 'stream_finished', url: r.url() }); });

const records = [];
let restSeq = 0;
const drain = async () => {
  let batch = [];
  try { batch = await page.evaluate(() => (window.__held ? window.__held.splice(0) : [])); } catch { return []; }
  for (const r of batch) {
    if (r.kind === 'rest' && r.body !== undefined) {
      const kind = /\/history(?:[?]|$)/.test(r.url) ? 'history' : /\/api\/events\/\d+(?:\?|$)/.test(r.url) ? 'detail' : 'other';
      const file = `rest/${String(++restSeq).padStart(4, '0')}-${kind}.json`;
      writeFileSync(`${outDir}/${file}`, r.body);
      r.rest_kind = kind;
      r.body_file = file;
      r.body_bytes = Buffer.byteLength(r.body);
      r.body_sha256 = createHash('sha256').update(r.body).digest('hex').slice(0, 16);
      delete r.body;
    }
    records.push(r);
    out(r);
  }
  return batch;
};

await page.goto(`https://bainluck.com/events/${eid}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
let shots = 0;
const shoot = async (label) => {
  const before = await page.evaluate(() => performance.now());
  const file = `held-${eid}-${label}-${new Date().toISOString().slice(11, 19).replace(/:/g, '')}Z.png`;
  await page.screenshot({ path: `${outDir}/${file}` });
  const after = await page.evaluate(() => performance.now());
  const rec = { kind: 'shot', label, file, mono_before: before, mono_after: after };
  records.push(rec);
  out(rec);
};
const end = Date.now() + Number(secs || 180) * 1000;
while (Date.now() < end) {
  const batch = await drain();
  for (const r of batch) {
    if (r.kind === 'headline' && r.prev !== null && shots < 8) { shots++; await shoot(`h${r.value}`); }
  }
  await page.waitForTimeout(250);
}
await drain();
await shoot('end');
await browser.close();

// ---- attribution: which delivery path preceded each visible change ----
const frames = records.filter((r) => r.kind === 'frame' && typeof r.p === 'number');
const rests = records.filter((r) => r.kind === 'rest');
const num = (v) => (v == null ? null : Number(String(v).replace('%', '')));
const inWindow = (a, b) => rests.filter((r) => (r.body_mono ?? r.headers_mono) > a && (r.body_mono ?? r.headers_mono) <= b)
  .map((r) => ({ url: r.url, rest_kind: r.rest_kind, body_mono: r.body_mono, body_file: r.body_file }));
const headlines = records.filter((r) => r.kind === 'headline');
const changes = headlines.filter((h) => h.prev !== null && h.value !== null).map((h) => {
  const v = num(h.value);
  const match = [...frames].reverse().find((f) => f.mono <= h.mono &&
    (Math.round(f.p * 100) === v || Math.round((1 - f.p) * 100) === v));
  const paintedRec = records.find((r) => r.kind === 'headline_painted' && r.mono >= h.mono && r.value === h.value);
  const shot = records.find((r) => r.kind === 'shot' && r.mono_before >= h.mono && r.label === `h${h.value}`);
  const restBetween = match ? inWindow(match.mono, h.mono) : null;
  const chartAfter = records.find((r) => r.kind === 'chart' && r.mono >= (match ? match.mono : h.mono) && r.mono <= h.mono + 2000);
  const restBefore = [...rests].reverse().find((r) => (r.body_mono ?? r.headers_mono) <= h.mono);
  return {
    headline: { from: h.prev, to: h.value, mono: h.mono, wall: new Date(h.wall).toISOString() },
    painted_mono: paintedRec?.mono ?? null,
    shot: shot ? { file: shot.file, mono_before: shot.mono_before } : null,
    frame: match ? { source: match.source, p: match.p, source_value: match.source_value, clock: match.clock,
      mono: match.mono, wall: new Date(match.wall).toISOString(), frame_to_mutation_ms: +(h.mono - match.mono).toFixed(1) } : null,
    chart_mutation: chartAfter ? { mono: chartAfter.mono, points: chartAfter.points, last_y: chartAfter.last_y } : null,
    rest_between_frame_and_mutation: restBetween,
    latest_rest_before_mutation: restBefore ? { url: restBefore.url, rest_kind: restBefore.rest_kind, body_mono: restBefore.body_mono,
      rest_to_mutation_ms: +(h.mono - (restBefore.body_mono ?? restBefore.headers_mono)).toFixed(1), body_file: restBefore.body_file } : null,
    verdict: !match ? 'no-matching-frame' : restBetween.length ? 'ambiguous-rest-in-window' : 'push',
  };
});
const wrapMissed = netSeen.filter((n) => !rests.some((r) => n.url.endsWith(r.url) || r.url.endsWith(n.url.replace(/^https?:\/\/[^/]+/, ''))));
const summary = {
  event_id: Number(eid), seconds: Number(secs || 180),
  counts: {
    frames: frames.length,
    frames_by_source: frames.reduce((a, f) => ((a[f.source] = (a[f.source] || 0) + 1), a), {}),
    rest: rests.length, headline_changes: changes.length,
    chart_mutations: records.filter((r) => r.kind === 'chart').length,
    stream_events: records.filter((r) => r.kind.startsWith('stream_')).reduce((a, r) => ((a[r.kind] = (a[r.kind] || 0) + 1), a), {}),
  },
  // Last frame the page received: after this the headline can only have moved by REST.
  last_frame_mono: frames.length ? frames[frames.length - 1].mono : null,
  rest_seen_by_network_not_by_fetch_wrap: wrapMissed,
  changes,
};
writeFileSync(`${outDir}/held-${eid}-attribution.json`, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary.counts), 'push-attributed:', changes.filter((c) => c.verdict === 'push').length);
