#!/usr/bin/env node
/**
 * #6194 — a finished game's ladder prints degenerate settled prices under a
 * heading that calls them the last quote.
 *
 * WHAT THE READER SEES (the defect this is keyed on, not a proxy for it):
 *
 *     FINAL  27 points
 *     LAST QUOTE FOR GOING OVER
 *     Over 7.5    100%
 *     Over 10.5   100%
 *
 * Seven rungs, seven 100%s, called quotes. They are not quotes — the market
 * settled and every rung collapsed to 0/1. A graded ladder does not render a
 * percentage AT ALL (`MarketMap.tsx` LadderRows: the graded arm prints
 * "cleared" / "not cleared" and draws no bar), so a percentage under a
 * "Last quote for" heading is proof the rung carries no `outcome`.
 *
 * So the detector is exact, and needs no threshold of judgement:
 *   a card on a FINISHED page whose ladder heading is "Last quote for …"
 *   and whose every rung reads 0% or 100%.
 *
 * Both ladder arms are read. `MarketMap.tsx` renders the ladder INLINE only
 * when the density band draws no shape; otherwise it goes in a hover/tap
 * popover which is in the DOM at `opacity-0` from first paint. A probe that
 * only reads the inline arm reads nothing on exactly the cards that have the
 * most data — the Giants/Cowboys specimen is one — so this walks headings,
 * not containers, and reports which arm each came from.
 *
 * exit 0  no card quotes its verdicts        exit 3  at least one does
 * exit 4  the page served no ladder at all (no specimen — NOT a pass)
 * exit 2  usage / load failure
 *
 * usage: node ux1369-settled-ladder-quotes-its-verdicts-6194.mjs <origin> <eventId> [width]
 */
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

const [origin, eventId, widthArg] = process.argv.slice(2);
if (!origin || !eventId) {
  console.error('usage: <origin> <eventId> [width]');
  process.exit(2);
}
const width = Number(widthArg || 390);
const url = `${origin.replace(/\/$/, '')}/events/${eventId}`;

const HEADINGS = /^(Each line vs the final|Last quote for (going over|winning by)|Chance of (going over|winning by))$/i;

// Same launch shape as tools/shop-shot.mjs. Without `--single-process` and
// `--disable-crashpad` Chromium dies in this sandbox on a mach-port rendezvous
// (`Permission denied (1100)`) before the first navigation, and the proxy is
// how anything reaches api.bainluck.com from here.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url)) {
    args.push('--proxy-bypass-list=<-loopback>');
  }
}

const browser = await chromium.launch({ args });
const ctx = await browser.newContext({ viewport: { width, height: 844 } });
const page = await ctx.newPage();

let cards = [];
try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 90_000 });
  // Grow the viewport to the document so intersection-lazy cards mount, the
  // same reason look.sh grows rather than using fullPage.
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30_000) });
  await page.waitForTimeout(2500);

  cards = await page.evaluate((HEAD_SRC) => {
    const HEAD = new RegExp(HEAD_SRC, 'i');
    const out = [];
    for (const el of document.querySelectorAll('div')) {
      // The heading is a leaf div whose whole text is one of the three.
      if (el.children.length !== 0) continue;
      const t = (el.textContent || '').trim();
      if (!HEAD.test(t)) continue;

      // Rungs are the heading's following siblings, one grid row each.
      const rows = [];
      let n = el.nextElementSibling;
      while (n) {
        const cells = Array.from(n.children).map((c) => (c.textContent || '').trim());
        if (cells.length) rows.push(cells.filter(Boolean).join(' | '));
        n = n.nextElementSibling;
      }

      // Card title: nearest ancestor section's first heading-ish text.
      let title = '(unknown card)';
      const sec = el.closest('section');
      if (sec) {
        const h = sec.querySelector('h1,h2,h3,h4');
        if (h) title = (h.textContent || '').trim();
      }

      const inPopover = !!el.closest('[data-inline-ladder]') === false;
      out.push({ title, heading: t, rows, arm: inPopover ? 'popover' : 'inline' });
    }
    return out;
  }, HEADINGS.source);
} catch (e) {
  console.error('LOAD FAILED:', e.message);
  await browser.close();
  process.exit(2);
}
await browser.close();

const pct = /(^|\s|\|)(\d{1,3})%\s*$/;
function rungPercents(rows) {
  const vals = [];
  for (const r of rows) {
    const m = r.match(/(\d{1,3})%\s*$/);
    if (m) vals.push(Number(m[1]));
  }
  return vals;
}

console.log(`${url}  @${width}px`);
console.log(`ladders found: ${cards.length}`);
if (!cards.length) {
  console.log('\nNO LADDER ON THIS PAGE — no specimen here. Not a pass.');
  process.exit(4);
}

let offenders = 0;
for (const c of cards) {
  const vals = rungPercents(c.rows);
  const quoting = /^Last quote for/i.test(c.heading);
  const allDegenerate = vals.length > 0 && vals.every((v) => v === 0 || v === 100);
  const bad = quoting && allDegenerate;
  if (bad) offenders++;
  console.log(
    `\n${bad ? '🔴 QUOTES ITS VERDICTS' : '  ok'}  [${c.arm}] ${c.title}` +
      `\n     heading: "${c.heading}"` +
      `\n     rungs  : ${c.rows.length}` +
      (vals.length
        ? `  percentages=[${vals.join(', ')}]${allDegenerate ? '  ← all 0/100 (settled signature)' : ''}`
        : '  (graded — no percentages, prints cleared/not cleared)')
  );
  for (const r of c.rows.slice(0, 8)) console.log(`       ${r}`);
}

console.log(`\noffenders: ${offenders}`);
process.exit(offenders ? 3 : 0);
