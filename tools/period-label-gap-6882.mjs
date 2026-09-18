// period-label-gap-6882.mjs — how much clear space is there between two period markers'
// LABELS on an event page's charts?  (#6882)
//
// #6882 was filed off a TIME measurement: `HT → Q3` is 15.0 min on a 191.6 min span, so it
// clears `PERIOD_LABEL_MIN_SPACING_FRACTION` (7%) by 1.6 minutes and both labels are kept.
// That arithmetic says the pair SURVIVES the collapse rule; it does not say how the survivors
// read. Collision is a PIXEL problem (UX-P022's whole point), and a fraction-of-span threshold
// only becomes pixels once you know the plot width — so the number that decides whether this is
// a defect, and the number any fix has to clear, is measured here and nowhere else.
//
// It reports, per chart, every adjacent pair of period-marker labels and the CLEAR GAP between
// them: next label's left edge minus this label's right edge, in CSS pixels. A negative gap is
// an overlap. A small positive gap is the #6882 symptom — `HT Q3` reading as one token.
//
// SELECTOR: a period marker is a `<text class="recharts-label">` inside a
// `.recharts-reference-line` group. That is narrower than "every text in the svg" (which picks
// up axis ticks and the `>99%` end-of-line chip) and it does not depend on any y arithmetic, so
// it cannot drift out of date with the component's margins. The y=50 guide line carries no
// label and the Final marker deliberately carries none (#3541), so both are absent by
// construction rather than by a filter that could silently start matching them.
//
// Both charts are measured, because the spacing rule is shared by both call sites
// (`dedupePeriodLabels`, #888 / latency/467) and a fix that helps one and not the other is half
// a fix. Charts are named by the nearest section heading.
//
// Usage: node period-label-gap-6882.mjs <eventUrl> [widthPx] [comfortPx]
// Exit 0 = every pair clears `comfort` (default 8px) · 1 = at least one pair is tighter
//        · 4 = no period labels found at all (wrong page, or the chart never drew) — a
//              SUBJECT-DETECTION failure, never a pass.
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

const [url, widthS = '390', comfortS = '8'] = process.argv.slice(2);
if (!url) { console.error('usage: node period-label-gap-6882.mjs <eventUrl> [widthPx] [comfortPx]'); process.exit(2); }
const width = Number(widthS);
const comfort = Number(comfortS);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
// The charts mount below the fold and animate in; scroll them through the viewport so the
// ResizeObserver has measured real geometry before anything is read.
await page.evaluate(async () => {
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 900));
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 900));
});
await page.waitForTimeout(1500);

const charts = await page.evaluate(() => {
  const out = [];
  for (const svg of document.querySelectorAll('svg.recharts-surface')) {
    const box = svg.getBoundingClientRect();
    if (box.width < 120) continue;

    const labels = [...svg.querySelectorAll('.recharts-reference-line text.recharts-label')]
      .map(t => {
        const r = t.getBoundingClientRect();
        return { v: (t.textContent || '').trim(), left: r.left, right: r.right, top: r.top, bottom: r.bottom };
      })
      .filter(l => l.v)
      .sort((a, b) => a.left - b.left);
    if (labels.length < 2) continue;

    // The plot rectangle, for turning a fraction-of-span into pixels.
    const grid = svg.querySelector('.recharts-cartesian-grid');
    const g = grid ? grid.getBoundingClientRect() : null;

    // Name the chart by the nearest preceding heading.
    let name = '(unnamed)';
    let node = svg.closest('section') || svg.parentElement;
    for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
      const h = node.querySelector('h1,h2,h3,h4');
      if (h && (h.textContent || '').trim()) { name = h.textContent.trim().slice(0, 40); break; }
    }

    out.push({ name, svgWidth: box.width, plotWidth: g ? g.width : null, labels });
  }
  return out;
});

await browser.close();

if (charts.length === 0) {
  console.log('NO PERIOD LABELS FOUND — subject absent, not a pass.');
  process.exit(4);
}

let worst = Infinity;
let tight = 0;
for (const c of charts) {
  console.log(`\n${c.name}  svg=${c.svgWidth.toFixed(0)}px  plot=${c.plotWidth ? c.plotWidth.toFixed(0) + 'px' : 'n/a'}  labels=${c.labels.length}`);
  console.log(`  ${'pair'.padEnd(16)} ${'gap'.padStart(8)} ${'rows'.padStart(6)}`);
  for (let i = 0; i < c.labels.length - 1; i++) {
    const a = c.labels[i], b = c.labels[i + 1];
    const gap = b.left - a.right;
    // Two labels on different vertical rows do not collide however close in x they are.
    const sameRow = !(b.top >= a.bottom || a.top >= b.bottom);
    const effective = sameRow ? gap : Infinity;
    if (effective < worst) worst = effective;
    if (effective < comfort) tight++;
    const flag = !sameRow ? 'STAGGERED' : gap < 0 ? '🔴 OVERLAP' : gap < comfort ? '🔴 TIGHT' : 'ok';
    console.log(`  ${`${a.v} → ${b.v}`.padEnd(16)} ${gap.toFixed(1).padStart(8)} ${(sameRow ? 'same' : 'diff').padStart(6)}   ${flag}`);
  }
  if (c.plotWidth) {
    console.log(`  (${comfort}px of clear space = ${(comfort / c.plotWidth * 100).toFixed(2)}% of the plot width)`);
  }
}

console.log(`\nworst same-row gap: ${worst === Infinity ? 'none (all staggered)' : worst.toFixed(1) + 'px'} · comfort ${comfort}px · tight pairs ${tight}`);
process.exit(tight > 0 ? 1 : 0);
