/**
 * #8066's remainder / #920 — does a SINGLE-SOURCE live page's chart keep up with push?
 *
 *   PW_ROOT=/Users/bain/bainluck/frontend/e2e \
 *     node tools/chart-push-speed-8066.mjs https://bainluck.com/events/<id> ./out [seconds]
 *
 * THE MEASUREMENT. On a page the backend serves no `aggregate_line` for, the only line on the
 * plot is the source's own. This records three clocks on one timeline:
 *
 *   • `frame`  — a publication the page's OWN EventSource received (wrapped, not a second
 *                subscription), with its `updated_at` and `source_value`;
 *   • `edge`   — the last vertex the CHART is actually drawing, read out of the rendered
 *                caption the reader can see, not out of any internal;
 *   • `hero`   — the big number, which merges push today and is therefore the control that
 *                tells "push is dead" apart from "push is alive and the chart is not using it".
 *
 * BEFORE the fix the hero moves at push speed while the edge only moves on the 32s poll.
 * AFTER it, the edge tracks the frames. The hero control is what makes that a defect claim
 * rather than an observation about a quiet market — without it, a flat venue and a broken
 * merge produce the same transcript.
 *
 * Read the JSONL with `grade-chart-push-speed-8066.py`. Nothing here asserts; it records.
 */
import { createRequire } from 'module';
import { appendFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const require = createRequire(import.meta.url);
const { chromium } = require(
  process.env.PW_ROOT ? process.env.PW_ROOT + '/node_modules/playwright' : 'playwright',
);

const url = process.argv[2];
const out = (process.argv[3] || './chart-push-speed') + '.jsonl';
const seconds = Number(process.argv[4] || 240);
if (!url) { console.error('usage: chart-push-speed-8066.mjs <url> [out] [seconds]'); process.exit(2); }
mkdirSync(dirname(out), { recursive: true });

const t0 = Date.now() / 1000;
const emit = (row) => {
  const line = JSON.stringify({ t: +(Date.now() / 1000 - t0).toFixed(3), ...row });
  appendFileSync(out, line + '\n');
  console.log(line);
};

const _proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const _args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (_proxy) { _args.push(`--proxy-server=${_proxy}`); _args.push('--proxy-bypass-list=<-loopback>'); }

const browser = await chromium.launch({
  headless: true, executablePath: process.env.CHROMIUM_PATH || undefined, args: _args,
});
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
const page = await context.newPage();

page.on('request', (r) => {
  if (!/\/api\//.test(r.url())) return;
  const u = r.url().replace(/^https?:\/\/[^/]+/, '');
  emit({ kind: 'request', which: /\/stream(\?|$)/.test(u) ? 'stream' : /\/history/.test(u) ? 'history' : 'poll', url: u });
});

// Wrap the page's own EventSource before any app code constructs one.
await page.addInitScript(() => {
  window.__frames = [];
  // THE INSTRUMENT'S OWN CONTROL. `frames: 0` has two causes that look identical in the
  // transcript: a quiet market, and a wrapper that never attached. These count every message
  // and every construction, so a run reporting no publications can still prove it was
  // listening. A zero here is a broken probe; a zero in `frames` beside a non-zero here is a
  // real quiet market.
  window.__esOpened = 0;
  window.__esMessages = 0;
  window.__esBeats = 0;
  const Native = window.EventSource;
  if (!Native) return;
  function Wrapped(u, init) {
    const es = new Native(u, init);
    window.__esOpened += 1;
    // 🪤 EVERY EVENT THIS SERVER SENDS IS A NAMED ONE. `event_stream.py` emits
    // `probability`, `heartbeat`, `reconnect` and `closed` — deliberately, so the
    // client's watchdog can observe a live-but-quiet server. A `message` listener
    // fires for NONE of them, so a probe wired the conventional way records zero
    // publications on a perfectly healthy stream and reads exactly like the defect.
    es.addEventListener('probability', (e) => {
      window.__esMessages += 1;
      try {
        const d = JSON.parse(e.data);
        if (d && typeof d.p === 'number') {
          window.__frames.push({
            at: Date.now() / 1000, p: d.p, source: d.source,
            source_value: d.source_value, updated_at: d.updated_at,
          });
        }
      } catch { /* a frame we cannot parse is not a frame we can count */ }
    });
    // The liveness control: heartbeats arrive on their own clock whatever the
    // market does, so `beats > 0` with `frames == 0` is a QUIET MARKET, while
    // `beats == 0` is a dead probe or a dead stream. Without this the two are
    // indistinguishable and a broken instrument reads as a proven defect.
    for (const name of ['heartbeat', 'reconnect', 'closed']) {
      es.addEventListener(name, () => { window.__esBeats += 1; });
    }
    return es;
  }
  Wrapped.prototype = Native.prototype;
  for (const k of ['CONNECTING', 'OPEN', 'CLOSED']) Wrapped[k] = Native[k];
  window.EventSource = Wrapped;
});

await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90_000 });
emit({ kind: 'loaded', url });

/**
 * What the reader can see. The chart's trailing caption ("2:44 PM  Brengle 68% — ...") is the
 * rendered right edge; the hero is the big percentage. Both are read as TEXT, so this stays
 * honest if the internals change — and it records `null` rather than guessing when a selector
 * finds nothing, so a dead probe cannot read as a frozen chart.
 */
const sample = async () => {
  try {
    return await page.evaluate(() => {
      const text = (el) => (el && el.textContent || '').trim().replace(/\s+/g, ' ');
      const body = document.body.innerText || '';
      // Trailing caption under the plot: a time, then the two names with percents.
      const cap = body.match(/(\d{1,2}:\d{2}\s?[AP]M)\s+([^\n]*?\d{1,3}%[^\n]*?\d{1,3}%)/);
      // The hero: the largest percent rendered near the top of the page.
      const heroEl = Array.from(document.querySelectorAll('*')).find(
        (e) => e.children.length === 0 && /^\d{1,3}$/.test(text(e)) &&
               parseFloat(getComputedStyle(e).fontSize) >= 30,
      );
      return {
        edge_time: cap ? cap[1] : null,
        edge_text: cap ? cap[2] : null,
        hero: heroEl ? Number(text(heroEl)) : null,
        frames: (window.__frames || []).length,
        es_opened: window.__esOpened ?? null,
        es_messages: window.__esMessages ?? null,
        es_beats: window.__esBeats ?? null,
        last_frame: (window.__frames || []).slice(-1)[0] || null,
      };
    });
  } catch (e) { return { error: String(e).slice(0, 160) }; }
};

const deadline = Date.now() / 1000 + seconds;
let prev = null;
while (Date.now() / 1000 < deadline) {
  const s = await sample();
  // Record every sample's raw state, and flag the transitions a grader counts.
  const row = { kind: 'sample', ...s };
  if (prev) {
    row.edge_moved = prev.edge_time !== s.edge_time || prev.edge_text !== s.edge_text;
    row.hero_moved = prev.hero !== s.hero;
    row.frames_delta = (s.frames ?? 0) - (prev.frames ?? 0);
  }
  emit(row);
  prev = s;
  await page.waitForTimeout(2000);
}

emit({ kind: 'done', frames_total: (prev && prev.frames) || 0 });
await browser.close();
