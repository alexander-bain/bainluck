// bundle-row-link-4425.mjs — #4425 after-check: can an EXPANDED bundle's rows be opened?
//
// The defect was that `FuturesCard`'s outcome_distribution leaderboard branch rendered a bare
// <h3>, so expanding a bundle took its clickable-title count DOWN. A screenshot cannot photograph
// "this row does nothing"; the proof is the measurement, so this probe:
//
//   1. finds every bundle on page one by its expand control,
//   2. records the anchor count inside the bundle BEFORE expanding (the collapsed peek rows are
//      `FuturesCompactRow`s and were always links — this is the control that says the probe is
//      reading the right subtree),
//   3. clicks Expand and records the anchor count AFTER,
//   4. reports each expanded MEMBER TITLE and whether it sits inside an <a href="/futures/...">.
//
// Pre-fix, step 3 read LOWER than step 2 (the 2028 bundle went 2 -> 0). Post-fix every expanded
// member title must be an anchor.
//
// Usage: node bundle-row-link-4425.mjs <url> [widthPx]
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
if (!url) { console.error('usage: bundle-row-link-4425.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForTimeout(2500);

// A bundle is the card whose header button carries aria-expanded, or that has an Expand/Show all
// footer button. Keyed on the CONTROL rather than on a class string, which changes with the skin.
const bundles = await page.evaluate(() => {
  const out = [];
  const buttons = [...document.querySelectorAll('button')];
  for (const b of buttons) {
    const t = (b.textContent || '').trim();
    if (!/^(Expand|Show all \d+|Show \d+ more)$/.test(t)) continue;
    const card = b.closest('div.rounded-2xl');
    if (!card) continue;
    const header = card.querySelector('button');
    out.push({
      label: t,
      question: (header?.innerText || '').split('\n').filter(Boolean).slice(-1)[0] || '(no question)',
      anchorsBefore: card.querySelectorAll('a[href^="/futures/"], a[href^="/event"]').length,
    });
  }
  return out;
});

console.log(`URL      ${url} @ ${width}px`);
console.log(`BUNDLES  ${bundles.length} on page one`);

let expandedTotal = 0, linkedTotal = 0;
for (let i = 0; i < bundles.length; i++) {
  const b = bundles[i];
  // Re-find by text each round: expanding one bundle re-lays out the page.
  const btn = page.locator('button', { hasText: new RegExp(`^${b.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) }).first();
  if (!(await btn.count())) { console.log(`\n[${i}] ${b.question} — control gone, skipped`); continue; }
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  await page.waitForTimeout(900);
  // Park the pointer off the card so no :hover state is measured (ux/1157's shop-shot lesson).
  await page.mouse.move(2, 2);

  const after = await page.evaluate((question) => {
    const cards = [...document.querySelectorAll('div.rounded-2xl')];
    const card = cards.find((c) => (c.innerText || '').includes(question));
    if (!card) return null;
    // A member title is an <h3> inside the expanded block.
    const titles = [...card.querySelectorAll('h3')].map((h) => ({
      text: (h.textContent || '').trim(),
      linked: !!h.closest('a[href^="/futures/"], a[href^="/event"]'),
      href: h.closest('a')?.getAttribute('href') || null,
    }));
    return { anchors: card.querySelectorAll('a[href^="/futures/"], a[href^="/event"]').length, titles };
  }, b.question);

  if (!after) { console.log(`\n[${i}] ${b.question} — card not re-found after expand`); continue; }
  console.log(`\n[${i}] ${b.question}`);
  console.log(`     anchors: ${b.anchorsBefore} collapsed -> ${after.anchors} expanded`);
  for (const t of after.titles) {
    expandedTotal += 1;
    if (t.linked) linkedTotal += 1;
    console.log(`     ${t.linked ? 'LINK ' : '🔴DEAD'} ${t.href || ''}  ${t.text.slice(0, 60)}`);
  }
}

console.log(`\nVERDICT  ${linkedTotal}/${expandedTotal} expanded member titles are anchors`);
console.log(expandedTotal === 0 ? '🔴 NO SPECIMEN — the probe never expanded a bundle; this is NOT a pass'
  : linkedTotal === expandedTotal ? '✅ PASS' : '🔴 FAIL');
await browser.close();
process.exit(expandedTotal > 0 && linkedTotal === expandedTotal ? 0 : 1);
