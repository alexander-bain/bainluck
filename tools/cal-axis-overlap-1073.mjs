// cal-axis-overlap-1073.mjs — do any two x-axis labels on /calibration collide?  (#4400)
//
// The acceptance for #4400 is not "is the label present" and not "what is the scale" — a DOM
// census passes on both while the axis reads `0% 10% 20%30%40%50%60%70%80%90%100%`. It is whether
// two labels OVERLAP in the reader's own pixels, so this measures the painted ink: every x-axis
// label's getBoundingClientRect(), sorted left to right, adjacent right-edge against next
// left-edge. A negative gap is an overlap; a gap under ~2px reads as one grey run even without one.
//
// The x-axis labels are the only `text-anchor="middle"` nodes in a CalibrationChart whose whole
// content is `N%` (the y-axis ticks are anchor="end", the axis titles are words), so that is the
// selector — no y-coordinate arithmetic to drift out of date with the component's padding.
//
// Every <details> is opened first: a folded section's chart has never been measured by the
// ResizeObserver, so it reports the un-measured authored geometry and would read as a false pass.
//
// Usage: node cal-axis-overlap-1073.mjs <url> <widthPx>
// Exit 0 = no overlaps; exit 1 = at least one chart's axis collides (the table names which).
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

const [url = 'https://bainluck.com/calibration', widthS = '390'] = process.argv.slice(2);
const width = Number(widthS);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForFunction(() => document.querySelectorAll('svg').length > 2, null, { timeout: 60000 });
await page.waitForTimeout(1200);

const rows = await page.evaluate(async () => {
  for (const d of document.querySelectorAll('details')) d.open = true;
  window.scrollTo(0, document.body.scrollHeight);
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 1200)); // let the ResizeObserver settle on newly-shown charts

  const out = [];
  for (const svg of document.querySelectorAll('svg[viewBox]')) {
    const [, , vbW] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    if (!vbW || vbW < 120) continue;            // icons, not charts
    const box = svg.getBoundingClientRect();
    if (box.width < 40) continue;               // hidden tab panes

    const labels = [...svg.querySelectorAll('text[text-anchor="middle"]')]
      .filter(t => /^\d+%$/.test((t.textContent || '').trim()))
      .map(t => ({ v: (t.textContent || '').trim(), r: t.getBoundingClientRect() }))
      .sort((a, b) => a.r.left - b.r.left);
    if (labels.length < 2) continue;

    let minGap = Infinity, at = '';
    for (let i = 0; i < labels.length - 1; i++) {
      const gap = labels[i + 1].r.left - labels[i].r.right;
      if (gap < minGap) { minGap = gap; at = `${labels[i].v}|${labels[i + 1].v}`; }
    }
    const sec = svg.closest('section');
    out.push({
      heading: (sec?.querySelector('h2,h3')?.textContent || '').trim().slice(0, 34),
      viewBox: vbW,
      drawnW: Math.round(box.width),
      scale: Number((box.width / vbW).toFixed(3)),
      nLabels: labels.length,
      widest: Number(Math.max(...labels.map(l => l.r.width)).toFixed(1)),
      minGap: Number(minGap.toFixed(1)),
      at,
    });
  }
  return out;
});

await browser.close();

console.log(`# ${url} @ ${width}px — x-axis label collisions across ${rows.length} charts\n`);
console.log('labels  scale  drawn  widest  min-gap  between      section');
for (const r of rows) {
  console.log(
    `${String(r.nLabels).padEnd(7)} ${String(r.scale).padEnd(6)} ${String(r.drawnW).padEnd(6)} ` +
    `${String(r.widest).padEnd(7)} ${String(r.minGap).padEnd(8)} ${r.at.padEnd(12)} ${r.heading}`
  );
}
const bad = rows.filter(r => r.minGap < 0);
console.log(`\ncharts with OVERLAPPING x-axis labels: ${bad.length} of ${rows.length}`);
for (const r of bad) console.log(`  ${r.heading} — ${r.nLabels} labels, ${r.minGap}px between ${r.at}`);
process.exit(bad.length ? 1 : 0);
