// chart-line-decode.mjs — what VALUES is a Recharts line actually drawing? (#5493)
//
// A screenshot of a chart cannot be graded. "The blend is a square wave" and "the blend is flat
// and one faint source line steps down behind it" photograph almost identically at 390px, and I
// read the same frame both ways before writing this. So this reads the rendered `<path d>` back
// out of the DOM and decodes each vertex against the y-axis's own tick labels, giving a value per
// pixel column — the numbers the reader is looking at, not the numbers the payload contains.
//
// It reports, per line: stroke, stroke-width, dashed, and the list of TRANSITIONS (x, value) —
// consecutive equal values collapsed — so a 218-point series prints as the four steps it actually
// draws. Match `stroke` against the palette in `win_prob_sources` (polymarket `#3b82f6`, …) or
// against `OddsChart`'s own constants to name each line.
//
// ⚠ TWO TRAPS, both paid for on `/events/15308675`:
//
//   1. An event page holds MORE THAN ONE chart (Win Probability, Score Differential). A bare
//      `querySelectorAll` mixes their lines and their axes, and the x-tick list comes back with
//      duplicate labels — that is the tell. `--chart <n>` scopes to one `.recharts-wrapper`.
//   2. The decode is only as good as the tick labels it reads. A chart whose y-axis is a ±50
//      delta, or whose ticks are not plain `NN%`, yields nonsense (values like `-69`). Sanity-check
//      the printed `yScale` before believing a single number.
//
// Usage: node chart-line-decode.mjs <url> [--chart N] [--width px] [--shot out.png]
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

const argv = process.argv.slice(2);
const url = argv[0];
const flag = (name, dflt) => {
  const i = argv.indexOf(name);
  return i === -1 ? dflt : argv[i + 1];
};
const chartIndex = Number(flag('--chart', 0));
const width = Number(flag('--width', 390));
const shot = flag('--shot', null);
if (!url) { console.error('usage: chart-line-decode.mjs <url> [--chart N] [--width px] [--shot out.png]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const localTarget = /localhost|127\.0\.0\.1/.test(url);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!localTarget) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 1 });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForSelector('.recharts-surface', { timeout: 60000 }).catch(() => {});
// Recharts animates the line in on mount; decoding mid-animation reads a partial path.
await page.waitForTimeout(6000);

const out = await page.evaluate((i) => {
  const wrappers = [...document.querySelectorAll('.recharts-wrapper')];
  if (!wrappers.length) return { found: false, reason: 'no .recharts-wrapper' };
  if (i >= wrappers.length) return { found: false, reason: `chart ${i} of ${wrappers.length}`, chartCount: wrappers.length };
  const root = wrappers[i];

  const ticks = [...root.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick')]
    .map((t) => ({ v: parseFloat((t.textContent || '').replace('%', '')), y: +t.querySelector('text').getAttribute('y') }))
    .filter((t) => Number.isFinite(t.v) && Number.isFinite(t.y))
    .sort((a, b) => a.v - b.v);
  if (ticks.length < 2) return { found: false, reason: 'fewer than two readable y ticks', chartCount: wrappers.length };
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const toVal = (y) => lo.v + (lo.y - y) * (hi.v - lo.v) / (lo.y - hi.y);

  const lines = [...root.querySelectorAll('path.recharts-curve.recharts-line-curve')].map((pa) => {
    const d = pa.getAttribute('d') || '';
    const pts = d.split(/[ML]/).filter(Boolean).map((s) => s.split(',').map(Number))
      .filter((q) => q.length === 2 && Number.isFinite(q[0]) && Number.isFinite(q[1]));
    const transitions = [];
    let prev = null;
    for (const [x, y] of pts) {
      const v = Math.round(toVal(y) * 100) / 100;
      if (prev === null || Math.abs(v - prev) > 0.05) { transitions.push([Math.round(x * 10) / 10, v]); prev = v; }
    }
    const vals = pts.map(([, y]) => toVal(y));
    return {
      stroke: pa.getAttribute('stroke'),
      strokeWidth: pa.getAttribute('stroke-width'),
      dashed: /\d+px,\s*\d+px/.test(pa.getAttribute('stroke-dasharray') || ''),
      pointCount: pts.length,
      min: vals.length ? Math.round(Math.min(...vals) * 100) / 100 : null,
      max: vals.length ? Math.round(Math.max(...vals) * 100) / 100 : null,
      transitionCount: transitions.length,
      transitions: transitions.slice(0, 60),
    };
  });

  return {
    found: true,
    chartCount: wrappers.length,
    chartIndex: i,
    yScale: { lo, hi },
    xTicks: [...root.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick')]
      .map((t) => ({ text: (t.textContent || '').trim(), x: +t.querySelector('text').getAttribute('x') })),
    legend: [...root.querySelectorAll('.recharts-legend-item')].map((l) => (l.textContent || '').trim()),
    lines,
  };
}, chartIndex);

if (shot && out.found) {
  const el = (await page.$$('.recharts-wrapper'))[chartIndex];
  if (el) await el.screenshot({ path: shot });
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
process.exit(out.found ? 0 : 1);
