// chart-fixture-replay-7569.mjs — run a SAVED event-history payload through the REAL production
// win-probability renderer, and read what it actually draws. (ux, #7569 / #920 / #1833)
//
// ── WHY THIS EXISTS ──────────────────────────────────────────────────────────────────────────
// Every question about this chart has been answered twice this week by replaying
// `/api/events/{id}/history` rows in python and reasoning about `chartData`. That is not the
// instrument. `OddsChart` buckets by minute, seeds every minute, forward-fills, derives a y-domain
// from the POOLED series and hands recharts a categorical x-axis — so a replay of the rows agrees
// with the renderer right up to the case you are trying to measure (measured on #7837: the replay
// predicted a [25,100] axis for a page that renders [0,100]).
//
// So: intercept the page's own history fetch, hand it a payload from disk, and read the SVG.
// Saved input, real reader. The mutations below are the scenarios codex named for the pre-kickoff
// pass — a spike and reversal inside one minute, an out-of-order refresh, a reconnect, a missing
// aggregate line, a sparse series, and period/scoring markers.
//
// 🔴 A MUTATION IS NOT A CLAIM ABOUT PRODUCTION. `shuffle` and `sparse` describe payload shapes we
// have not observed on the wire; they exist to ask whether the renderer is ROBUST to them, and a
// finding from one of them is "the renderer would do X", never "the renderer does X today". Only
// `asis` and `noaggregate` are shapes production is known to serve (`aggregate_line` is emitted
// only when `len(agg_sources) > 1`, so a single-source game genuinely has none).
//
// Usage: node chart-fixture-replay-7569.mjs <fixture.json> <scenario> [url] [widthPx]
//   scenario: asis | shuffle | reconnect | noaggregate | sparse | truncate
// Exit:  0 measured (read the JSON on stdout) · 2 bad usage · 3 no chart rendered
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

const fixturePath = process.argv[2];
const scenario = process.argv[3] || 'asis';
const url = process.argv[4] || 'https://bainluck.com/events/14780544';
const width = Number(process.argv[5] || 390);
const SCENARIOS = ['asis', 'shuffle', 'reconnect', 'noaggregate', 'sparse', 'truncate'];
if (!fixturePath || !SCENARIOS.includes(scenario)) {
  console.error(`usage: chart-fixture-replay-7569.mjs <fixture.json> <${SCENARIOS.join('|')}> [url] [widthPx]`);
  process.exit(2);
}

const base = JSON.parse(readFileSync(fixturePath, 'utf8'));

/** Every probability series in the payload, by the name the chart knows it as. */
function eachSeries(payload, fn) {
  if (Array.isArray(payload.aggregate_line)) payload.aggregate_line = fn('aggregate_line', payload.aggregate_line);
  if (Array.isArray(payload.history)) payload.history = fn('history', payload.history);
  for (const k of Object.keys(payload.win_prob_history || {})) {
    payload.win_prob_history[k] = fn(`wp_${k}`, payload.win_prob_history[k]);
  }
  for (const k of Object.keys(payload.bookmaker_history || {})) {
    payload.bookmaker_history[k] = fn(`bk_${k}`, payload.bookmaker_history[k]);
  }
}

function mutate(scen) {
  const p = JSON.parse(JSON.stringify(base));
  if (scen === 'shuffle') {
    // A refresh that arrives out of temporal order: the LAST twenty readings of each series
    // reversed. Deliberately the tail — that is where the settled endpoint lives, and the tail is
    // the half a stale/duplicated poll would rewrite.
    eachSeries(p, (_n, arr) => (arr.length > 20 ? [...arr.slice(0, -20), ...arr.slice(-20).reverse()] : [...arr].reverse()));
  } else if (scen === 'noaggregate') {
    p.aggregate_line = [];
  } else if (scen === 'sparse') {
    // One reading every ~40th point: a game whose sources barely reported.
    eachSeries(p, (_n, arr) => arr.filter((_v, i) => i % 40 === 0));
  } else if (scen === 'truncate') {
    // The first 60% of the game, as if the reader opened the page mid-way: the chart must not
    // draw the part it does not have.
    eachSeries(p, (_n, arr) => arr.slice(0, Math.ceil(arr.length * 0.6)));
  }
  return p;
}

const payload = mutate(scenario);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 1600 }, deviceScaleFactor: 1 });

const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

let historyCalls = 0;
let refused = 0;
await page.route('**/api/events/*/history*', async (route) => {
  historyCalls += 1;
  // `reconnect`: the first attempt dies on the wire, the way a phone coming out of a tunnel does.
  // Everything after it is served. If the page never asks again, that IS the finding.
  if (scenario === 'reconnect' && historyCalls === 1) {
    refused += 1;
    return route.abort('connectionfailed');
  }
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(payload),
  });
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.evaluate(() => window.scrollTo(0, 700));
await page.waitForTimeout(2500);

// Open "+ N sources" so the per-source lines — the ones that actually lose readings to the minute
// bucket — are in the DOM. The blend is the only line drawn until a reader presses this.
let sourcesOpened = false;
try {
  const press = page.locator('button', { hasText: /\+\s*\d+\s*sources?/i }).first();
  if (await press.count()) { await press.click({ timeout: 5000 }); sourcesOpened = true; await page.waitForTimeout(1800); }
} catch { /* the press is absent on a single-source chart; that is a result, not an error */ }

const measured = await page.evaluate(() => {
  const wrappers = [...document.querySelectorAll('.recharts-wrapper')];
  if (!wrappers.length) return null;
  const w = wrappers[0];
  const svg = w.querySelector('svg.recharts-surface');
  const grid = w.querySelector('.recharts-cartesian-grid-bg rect') || w.querySelector('.recharts-cartesian-grid rect');
  const plot = grid ? { x: +grid.getAttribute('x'), y: +grid.getAttribute('y'), w: +grid.getAttribute('width'), h: +grid.getAttribute('height') } : null;

  const yTicks = [...w.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')].map((t) => t.textContent.trim()).filter(Boolean);
  const xTicks = [...w.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map((t) => t.textContent.trim()).filter(Boolean);

  // THE SCALE COMES FROM THE AXIS THE READER IS SHOWN, not from a grid rect (which recharts omits
  // when the grid has no fill) and not from a recomputation of the domain. Pair each y tick's
  // printed percentage with its own svg y, and the two extremes give the linear map.
  const tickPairs = [...w.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick')]
    .map((g) => {
      const t = g.querySelector('.recharts-cartesian-axis-tick-value');
      const label = t ? t.textContent.trim() : '';
      const pct = /^-?[\d.]+%$/.test(label) ? parseFloat(label) : null;
      const y = t ? +(t.getAttribute('y') ?? NaN) : NaN;
      return pct === null || !Number.isFinite(y) ? null : { pct, y };
    })
    .filter(Boolean)
    .sort((a, b) => a.y - b.y);
  let svgYToPct = null;
  if (tickPairs.length >= 2) {
    const a = tickPairs[0], b = tickPairs[tickPairs.length - 1];
    if (b.y !== a.y) svgYToPct = (y) => a.pct + ((y - a.y) * (b.pct - a.pct)) / (b.y - a.y);
  }

  // The legend maps a stroke colour to a source name, which is the only handle recharts leaves on
  // "which line is this" — it stamps no dataKey on the DOM.
  const legend = [...w.querySelectorAll('.recharts-legend-item')].map((li) => {
    const sw = li.querySelector('path, rect, line, svg *[fill], svg *[stroke]');
    const colour = sw ? (sw.getAttribute('fill') || sw.getAttribute('stroke') || '') : '';
    return { name: (li.textContent || '').trim(), colour: colour.toLowerCase() };
  });

  // Each drawn line: its vertices decoded back into the axis' own units, plus the extrema and the
  // terminal value — the two things every claim in this slice is about.
  const lines = [...w.querySelectorAll('.recharts-line')].map((g) => {
    const path = g.querySelector('.recharts-line-curve');
    const d = path ? path.getAttribute('d') || '' : '';
    const pts = [...d.matchAll(/([-\d.]+),([-\d.]+)/g)].map((m) => [+m[1], +m[2]]);
    const stroke = (path ? path.getAttribute('stroke') || '' : '').toLowerCase();
    const named = legend.find((l) => l.colour && l.colour === stroke);
    const pcts = svgYToPct ? pts.map(([, y]) => Math.round(svgYToPct(y) * 100) / 100) : [];
    return {
      name: named ? named.name : `unnamed(${stroke})`,
      stroke,
      vertices: pts.length,
      dots: g.querySelectorAll('.recharts-dot').length,
      min: pcts.length ? Math.min(...pcts) : null,
      max: pcts.length ? Math.max(...pcts) : null,
      first: pcts.length ? pcts[0] : null,
      last: pcts.length ? pcts[pcts.length - 1] : null,
      // Kept whole so a caller can ask "is this value drawn at this category" without re-running.
      pcts,
    };
  });

  // Period markers / scoring markers: ReferenceLines that resolved to a real category land inside
  // the plot; one that did not resolve is dropped by recharts entirely, so the COUNT is the check.
  const refLines = [...w.querySelectorAll('.recharts-reference-line line')].map((l) => ({ x1: +l.getAttribute('x1'), x2: +l.getAttribute('x2'), y1: +l.getAttribute('y1'), y2: +l.getAttribute('y2') }));
  const refLabels = [...w.querySelectorAll('.recharts-reference-line text')].map((t) => t.textContent.trim());
  const refDots = [...w.querySelectorAll('.recharts-reference-dot')].length;

  // What the card SAYS, beside what it draws — a chart that silently draws nothing is a different
  // defect from one that says it has nothing.
  const card = w.closest('div[class*="rounded"]') || w.parentElement;
  const cardText = (card ? card.innerText : '').split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 14);

  return { plot, scaleReadFromAxis: !!svgYToPct, yTicks, xTicks: { count: xTicks.length, first: xTicks[0], last: xTicks[xTicks.length - 1], all: xTicks }, legend, lines, refLines: refLines.length, refLabels, refDots, cardText, svgPresent: !!svg };
});

const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 400));
await browser.close();

if (!measured) {
  console.log(JSON.stringify({ scenario, url, width, historyCalls, refused, chart: null, bodyText, consoleErrors }, null, 2));
  process.exit(3);
}

console.log(JSON.stringify({
  scenario, url, width, fixture: fixturePath,
  historyCalls, refusedFirstCall: refused, sourcesOpened,
  ...measured,
  totalVertices: measured.lines.reduce((n, l) => n + l.vertices, 0),
  linesWithInk: measured.lines.filter((l) => l.vertices > 1).length,
  consoleErrors: consoleErrors.slice(0, 8),
}, null, 2));
