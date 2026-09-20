// ladder-rung-clip-7427.mjs <url> [width] — measure which Discover ladder rung labels are
// CLIPPED by their fixed slot, and by how much.
//
// WHY MEASURE RATHER THAN ESTIMATE (#7427). `QuantityGroup`'s wide-label variant gives the
// rung label a FIXED `w-[45%] shrink-0 truncate` slot. The fixed width is deliberate — with a
// content-width label the `flex-1` track is a different length on every row, so two rungs
// printing the same % draw visibly different bars (#1574 acceptance c). The cost is that a
// label longer than 45% of the row loses its TAIL, and on a date ladder the tail is the YEAR:
// "Before January 20, 2029" renders "Before January 20, …" directly above "Before 2027", and
// the one token that tells the two rungs apart is the one that got clipped.
//
// Whether a given label clips is a question about the rendered font's advance widths and the
// card's real width at 390px. A hand estimate gets that wrong in the direction that ships the
// clip, and a downscaled whole-page PNG fabricates the few pixels the answer turns on. So this
// reads `scrollWidth` vs `clientWidth` off the real element on the real page.
//
// It reports, per clipped rung: the full label (from the row's `aria-label`, which carries the
// untruncated text), the slot width, the text's natural width, and the shortfall in px and in
// ch. The shortfall is what a repair has to buy.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 measured, no rung clipped · 3 at least one rung is
// clipped (the defect is live) · 4 no ladder rung on this draw (the feed shuffled — re-run,
// not a failure) · 2 usage · 1 anything else.
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
if (!url) { console.error('usage: ladder-rung-clip-7427.mjs <url> [width]'); process.exit(2); }

// Same launch args as `tools/shop-shot.mjs`, and for the same two reasons: Chromium's default
// multi-process launch dies in the agent sandbox (`bootstrap_check_in … Permission denied
// (1100)`), and the browser does not inherit the session egress proxy. A probe that cannot
// launch reports nothing, which reads exactly like a probe that found nothing.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url)) {
    args.push('--proxy-bypass-list=<-loopback>');
  }
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

// The feed lazy-loads on intersection. Grow the viewport to the document height the way
// look.sh does, so every card below the fold mounts before anything is measured — a rung
// that never rendered cannot be reported as fitting.
for (let i = 0; i < 3; i++) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30000) });
  await page.waitForTimeout(1200);
}

const rows = await page.evaluate(() => {
  // A rung row is the element whose `aria-label` is "<label>: <pct>" and whose first child
  // span is the truncating label slot. Keying on the aria-label is what makes the FULL text
  // readable: the DOM text is untruncated (the clip is CSS), but the aria-label is the
  // contract the component states, so label and measurement cannot drift apart.
  const out = [];
  for (const el of document.querySelectorAll('[aria-label]')) {
    const aria = el.getAttribute('aria-label') || '';
    const m = aria.match(/^(.*): (\d+%|—|-)$/);
    if (!m) continue;
    const slot = el.querySelector(':scope > span');
    if (!slot) continue;
    const cs = getComputedStyle(slot);
    if (cs.textOverflow !== 'ellipsis') continue; // not a truncating label slot
    const text = (slot.textContent || '').trim();
    if (!text) continue;
    const r = slot.getBoundingClientRect();
    out.push({
      label: m[1],
      pct: m[2],
      text,
      clientWidth: slot.clientWidth,
      scrollWidth: slot.scrollWidth,
      rowWidth: el.clientWidth,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
    });
  }
  return out;
});

await browser.close();

if (rows.length === 0) {
  console.log(`NO LADDER RUNG ON THIS DRAW (${url} @ ${width}px)`);
  process.exit(4);
}

// A 1px slack absorbs sub-pixel rounding: Chromium rounds clientWidth down and scrollWidth up,
// so an exactly-fitting label can read as 1px over. Anything above that is a real clip.
const clipped = rows.filter((r) => r.scrollWidth - r.clientWidth > 1);

console.log(`url=${url} width=${width}px rungs=${rows.length} clipped=${clipped.length}`);
if (rows.length) {
  const w = rows[0];
  console.log(`slot: clientWidth=${w.clientWidth}px of row ${w.rowWidth}px  font=${w.fontSize}/${w.fontWeight}`);
}
for (const r of clipped) {
  const short = r.scrollWidth - r.clientWidth;
  const perCh = r.scrollWidth / Math.max(1, r.text.length);
  console.log(
    `  CLIPPED  "${r.label}" (${r.pct})  slot=${r.clientWidth}px text=${r.scrollWidth}px ` +
    `short=${short}px (~${(short / perCh).toFixed(1)} chars)  row=${r.rowWidth}px`,
  );
}
const widest = rows.reduce((m, r) => Math.max(m, r.scrollWidth), 0);
const rowW = rows[0].rowWidth;
console.log(`widest rung text = ${widest}px = ${((widest / rowW) * 100).toFixed(1)}% of the row (slot is 45%)`);

process.exit(clipped.length > 0 ? 3 : 0);
