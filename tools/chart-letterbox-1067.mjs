// chart-letterbox-1067.mjs — measure the blank bands above and below every calibration chart at a
// given viewport width (calibration/1067, post-deploy LOOK on #4291).
//
// The question a screenshot cannot answer: is the empty space inside the "By Category" card a
// MARGIN somebody wrote, or is it SVG letterboxing — the box reserving its full `height` attribute
// while `max-width:100%` shrinks only the width, so `preserveAspectRatio` centres a short drawing
// in a tall box and leaves transparent bands the reader reads as dead space?
//
// Answered from the layout engine, never from pixels:
//   * the svg's own client rect                     -> the box the page reserved
//   * the svg's `getBBox()` in viewBox units + the
//     CTM the browser actually applied              -> where the DRAWING really lands
//   * band = (reserved height - drawn height) / 2   -> the letterbox, per chart
//
// A band of ~0 means the space is somebody's margin and this probe exonerates the chart.
//
// Usage: node chart-letterbox-1067.mjs <url> [widthPx]
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
if (!url) { console.error('usage: chart-letterbox-1067.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
// NOT `waitForSelector('svg')`: the first svg in the DOM is the chevron inside a CLOSED
// <details>, so the visibility wait times out on a page that has fully rendered (#4291 put
// those disclosures there). Wait for a chart-sized viewBox instead.
await page.waitForFunction(
  () => [...document.querySelectorAll('svg')].some(s => s.getBoundingClientRect().width > 200),
  null,
  { timeout: 60000 }
);
await page.waitForTimeout(1500);

// FIX=1 — the counterfactual arm. Inject the candidate one-property fix into the LIVE page and
// re-measure, so the claim "height:auto removes the band" is a measurement on the real DOM rather
// than a story about how SVG sizing works. Both arms render nine charts, so an empty diff here
// would be a real no-op and not a rig that drew nothing.
if (process.env.FIX === '1') {
  await page.addStyleTag({ content: 'svg[viewBox]{height:auto}' });
  await page.waitForTimeout(500);
}

const out = await page.evaluate(() => {
  // Scroll the whole page once so every lazily-mounted chart has laid out.
  window.scrollTo(0, document.body.scrollHeight);
  window.scrollTo(0, 0);

  const nearestHeading = (el) => {
    for (let n = el; n; n = n.parentElement) {
      const h = n.querySelector?.('h2, h3');
      if (h) return h.textContent.trim().slice(0, 40);
    }
    return '(no heading)';
  };

  return [...document.querySelectorAll('svg')].map((svg) => {
    const r = svg.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) return null;   // icons, chevrons, the logo
    let drawnH = null, drawnW = null;
    try {
      const bb = svg.getBBox();                        // viewBox units
      const m = svg.getScreenCTM();                    // what the browser actually applied
      if (bb && m) { drawnH = bb.height * m.d; drawnW = bb.width * m.a; }
    } catch { /* getBBox throws on a detached/display:none svg */ }
    return {
      heading: nearestHeading(svg),
      attrW: svg.getAttribute('width'),
      attrH: svg.getAttribute('height'),
      viewBox: svg.getAttribute('viewBox'),
      boxW: +r.width.toFixed(1),
      boxH: +r.height.toFixed(1),
      drawnW: drawnW == null ? null : +drawnW.toFixed(1),
      drawnH: drawnH == null ? null : +drawnH.toFixed(1),
      bandPx: drawnH == null ? null : +((r.height - drawnH) / 2).toFixed(1),
    };
  }).filter(Boolean);
});

console.log(`# ${url} @ ${width}px — ${out.length} charts`);
console.log('band = blank px above AND below the drawing, inside the reserved box\n');
for (const c of out) {
  console.log(
    `${(c.heading + ' ').padEnd(42, '·')} attr=${c.attrW}x${c.attrH} viewBox=${c.viewBox} ` +
    `box=${c.boxW}x${c.boxH} drawn=${c.drawnW}x${c.drawnH} BAND=${c.bandPx}px`
  );
}
const worst = out.filter(c => c.bandPx != null).sort((a, b) => b.bandPx - a.bandPx)[0];
console.log(`\nworst band: ${worst ? `${worst.bandPx}px on "${worst.heading}"` : 'none measured'}`);
await browser.close();
