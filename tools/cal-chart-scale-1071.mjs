// cal-chart-scale-1071.mjs — how big is each /calibration chart's TYPE, in the reader's pixels?
//
// Every chart on the page is one <svg width=W viewBox="0 0 W H"> with `maxWidth:100%`, so a chart
// authored at W=700 inside a 350px card is drawn at 0.50x and its 11px axis ticks land at 5.5 CSS
// px. A 330px-wide panel in the same card is drawn at 1.00x. Both look "fine" to a DOM census that
// only asks whether the text is present — the difference is only visible if you multiply the
// authored font-size by the SVG's own scale factor, which is what this does.
//
// Usage: node cal-chart-scale-1071.mjs <url> <widthPx>
// Exit 0 always; the verdict is the table. `scale` < 0.75 at 390px is the defect.
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
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForFunction(() => document.querySelectorAll('svg').length > 2, null, { timeout: 60000 });
await page.waitForTimeout(1500);

const rows = await page.evaluate(() => {
  // Force every lazy section to mount, then measure.
  window.scrollTo(0, document.body.scrollHeight);
  window.scrollTo(0, 0);
  const out = [];
  for (const svg of document.querySelectorAll('svg')) {
    const vb = svg.getAttribute('viewBox');
    if (!vb) continue;
    const [, , vbW, vbH] = vb.split(/\s+/).map(Number);
    if (!vbW || vbW < 120) continue;            // icons, not charts
    const r = svg.getBoundingClientRect();
    if (r.width < 40) continue;                  // hidden tab panes
    // nearest section heading above
    let sec = svg.closest('section');
    const heading = sec ? (sec.querySelector('h2,h3')?.textContent || '').trim().slice(0, 40) : '';
    // authored font sizes actually used inside this chart
    const sizes = new Set();
    for (const t of svg.querySelectorAll('text')) {
      const fs = t.getAttribute('font-size');
      if (fs) sizes.add(Number(fs));
    }
    const scale = r.width / vbW;
    const authored = [...sizes].sort((a, b) => a - b);
    out.push({
      heading,
      viewBox: `${vbW}x${vbH}`,
      drawn: `${Math.round(r.width)}x${Math.round(r.height)}`,
      scale: Number(scale.toFixed(3)),
      authoredMin: authored[0] ?? null,
      renderedMin: authored.length ? Number((authored[0] * scale).toFixed(1)) : null,
      renderedTick: Number(((authored.includes(11) ? 11 : authored[0] ?? 0) * scale).toFixed(1)),
      inClosedDetails: !!svg.closest('details:not([open])'),
    });
  }
  return out;
});

await browser.close();

console.log(`# ${url} @ ${width}px viewport — ${rows.length} charts\n`);
console.log('scale  drawn      viewBox   tick-px  min-px  folded  section');
for (const r of rows) {
  console.log(
    `${String(r.scale).padEnd(6)} ${r.drawn.padEnd(10)} ${r.viewBox.padEnd(9)} ` +
    `${String(r.renderedTick).padEnd(8)} ${String(r.renderedMin).padEnd(7)} ` +
    `${(r.inClosedDetails ? 'yes' : 'no').padEnd(7)} ${r.heading}`
  );
}
const bad = rows.filter(r => !r.inClosedDetails && r.scale < 0.75);
console.log(`\nvisible charts drawn below 0.75x: ${bad.length}`);
for (const r of bad) console.log(`  ${r.heading} — ${r.scale}x, ticks render at ${r.renderedTick}px`);
