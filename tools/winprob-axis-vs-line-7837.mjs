// winprob-axis-vs-line-7837.mjs — does the event page's Win Probability chart DRAW its line
// outside its own y-axis? (ux, #7837)
//
// The question a screenshot answers only one page at a time, and an API replay cannot answer at
// all: `computeWinProbYAxis` is fed the pooled, minute-bucketed, FORWARD-FILLED series the chart
// builds, so recomputing it from `/api/events/{id}/history` rows gets the domain wrong (measured:
// it predicted [25,100] for /events/14782150, which renders [0,100]). So ask the rendered chart.
//
// Read from the layout engine, never from pixels:
//   * `.recharts-yAxis` tick texts               -> the domain the reader is told they are seeing
//   * the cartesian grid's background rect       -> the plot box, in svg pixels
//   * every `.recharts-line-curve` path's `d`    -> where the ink really lands
//
// A path vertex above the plot's top or below its bottom is ink the clip path swallows: a line
// running off the frame, on a chart whose axis says that value cannot happen.
//
// Usage: node winprob-axis-vs-line-7837.mjs <url> [widthPx]
// Exit:  0 measured (read the JSON) · 2 bad usage · 3 no win-probability chart on the page
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

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
if (!url) { console.error('usage: winprob-axis-vs-line-7837.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
// The chart mounts below the fold and recharts sizes off a ResizeObserver, so scroll it into view
// and give the animation a beat before reading coordinates.
await page.evaluate(() => window.scrollTo(0, 700));
await page.waitForTimeout(2500);

const out = await page.evaluate(() => {
  // The Win Probability card is the first recharts wrapper on the event page; Score Differential
  // is the second and is on a ±points scale, not a probability one, so index matters.
  const wrappers = [...document.querySelectorAll('.recharts-wrapper')];
  if (!wrappers.length) return null;
  const w = wrappers[0];

  const ticks = [...w.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
    .map((t) => t.textContent.trim())
    .filter(Boolean);

  // The grid's own background rect is the plot box. Fall back to the clip path recharts installs
  // for `allowDataOverflow`, which is the same rect by construction.
  const gridRect = w.querySelector('.recharts-cartesian-grid > rect')
    || w.querySelector('clipPath > rect');
  const plot = gridRect
    ? {
        top: parseFloat(gridRect.getAttribute('y')),
        height: parseFloat(gridRect.getAttribute('height')),
      }
    : null;

  // Every drawn series, in svg user units. `d` is `M x,y L x,y …` or `M x,y C …`; we only need the
  // y of each vertex, so take every second number of each coordinate pair.
  const lines = [...w.querySelectorAll('.recharts-line-curve')].map((p) => {
    const nums = (p.getAttribute('d') || '').match(/-?\d+(?:\.\d+)?/g) || [];
    const ys = [];
    for (let i = 1; i < nums.length; i += 2) ys.push(parseFloat(nums[i]));
    return {
      stroke: p.getAttribute('stroke'),
      strokeWidth: p.getAttribute('stroke-width'),
      minY: ys.length ? Math.min(...ys) : null,
      maxY: ys.length ? Math.max(...ys) : null,
      points: ys.length,
    };
  });

  return { ticks, plot, lines };
});

await browser.close();

if (!out) { console.error('no recharts wrapper on the page'); process.exit(3); }

const { ticks, plot, lines } = out;
// Ticks read bottom-up in the DOM on some recharts versions and top-down on others; sort the
// parsed numbers rather than trusting the order.
const tickNums = ticks.map((t) => parseFloat(t.replace('%', ''))).filter(Number.isFinite).sort((a, b) => a - b);
const domain = tickNums.length ? [tickNums[0], tickNums[tickNums.length - 1]] : null;

// y grows downward: above the plot means y < plot.top.
const over = plot
  ? lines.filter((l) => l.minY !== null && l.minY < plot.top - 0.5)
  : [];
const under = plot
  ? lines.filter((l) => l.maxY !== null && l.maxY > plot.top + plot.height + 0.5)
  : [];

console.log(JSON.stringify({
  url, width, ticks, domain, plot,
  lineCount: lines.length,
  linesAboveFrame: over.length,
  linesBelowFrame: under.length,
  clipped: over.length > 0 || under.length > 0,
}, null, 2));
