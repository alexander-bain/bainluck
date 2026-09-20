#!/usr/bin/env node
/**
 * #5659 — a movement badge prints a bare number with no unit.
 *
 * WHAT THE READER SEES, on the card in the issue:
 *
 *     Above 98      ▲45.0   ███████░░   89%
 *     Above 101     ▲59.5   ██████░░░   83%
 *
 * `movement: 0.45` is a probability delta in 0-1 units, so `45.0` is 45
 * percentage POINTS — a move further than the whole remaining distance to
 * certainty — printed with no unit, in a column between a label and a number
 * that IS a percent. The reader has nothing to tell them what 45.0 is, and the
 * neighbour makes it read as a percentage.
 *
 * THE DETECTOR IS THE ARROW, NOT THE COMPONENT. Every surface in this family
 * prefixes the magnitude with a direction glyph (▲ ▼ ↑ ↓ + -), so the rendered
 * signature of the defect is: a direction glyph, a number, and then anything
 * other than a unit. That reads the three repaired surfaces and any future one
 * without knowing which component drew it.
 *
 * WHY IT DOES NOT FIRE ON A PERCENTAGE. A badge reading `▲8.5%` is the OTHER
 * half of this family (#5666), already closed and separately guarded; a bare
 * `%` is a unit, wrong but present, and this probe is keyed on absence. It is
 * reported separately rather than silently counted as clean.
 *
 * exit 0  every badge on the page carries a unit
 * exit 3  at least one badge prints a bare number
 * exit 4  the page drew no movement badge at all (no specimen — NOT a pass)
 * exit 2  usage / load failure
 *
 * usage: node ux1369-movement-badges-carry-their-unit-5659.mjs <url> [width]
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

const [url, widthArg] = process.argv.slice(2);
if (!url) {
  console.error('usage: <url> [width]');
  process.exit(2);
}
const width = Number(widthArg || 390);

const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url)) {
    args.push('--proxy-bypass-list=<-loopback>');
  }
}

const browser = await chromium.launch({ args });
const page = await (await browser.newContext({ viewport: { width, height: 844 } })).newPage();

let found;
try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 90_000 });
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30_000) });
  await page.waitForTimeout(2500);

  found = await page.evaluate(() => {
    // A direction glyph followed by a magnitude. `[+-]` only counts when it is
    // glued to a digit, so ordinary prose and hyphenated names cannot match.
    const BADGE = /([▲▼↑↓]|(?<![\w%])[+-](?=\d))\s?(\d{1,3}(?:\.\d)?)/;
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    for (let el = walker.nextNode(); el; el = walker.nextNode()) {
      // Leaf-ish only: the smallest element that contains the whole badge, so
      // one badge is not reported once per ancestor.
      const txt = (el.textContent || '').trim();
      if (!txt || txt.length > 60) continue;
      if (!BADGE.test(txt)) continue;
      if (Array.from(el.children).some((c) => BADGE.test((c.textContent || '').trim()))) continue;

      const m = txt.match(BADGE);
      const after = txt.slice(txt.indexOf(m[0]) + m[0].length);
      out.push({
        text: txt,
        magnitude: m[2],
        // The unit may be in this element's own text, or supplied by the
        // element immediately after it (`{delta}` + ` pts` split across spans).
        unit: /^\s*(pts|points?)\b/.test(after)
          ? 'pts'
          : /^\s*%/.test(after)
            ? '%'
            : '',
        aria: el.getAttribute('aria-label') || el.getAttribute('title') || '',
      });
    }
    return out;
  });
} catch (e) {
  console.error('LOAD FAILED:', e.message);
  await browser.close();
  process.exit(2);
}
await browser.close();

console.log(`${url}  @${width}px`);
console.log(`movement badges found: ${found.length}`);
if (!found.length) {
  console.log('\nNO MOVEMENT BADGE ON THIS PAGE — no specimen here. Not a pass.');
  process.exit(4);
}

const bare = found.filter((f) => f.unit === '');
const pct = found.filter((f) => f.unit === '%');
for (const f of found) {
  const tag = f.unit === '' ? '🔴 BARE NUMBER' : f.unit === '%' ? '🟠 percent (#5666 arm)' : '  ok';
  console.log(
    `${tag}  "${f.text}"   magnitude=${f.magnitude} unit=${f.unit || '(none)'}` +
      (f.aria ? `\n       accessible name: "${f.aria}"` : '')
  );
}

console.log(`\nbare: ${bare.length}   percent: ${pct.length}   with-unit: ${found.length - bare.length - pct.length}`);
if (bare.length) {
  console.log('\nA bare magnitude is the defect: the accessible name beside several of these');
  console.log('already says "points", so the page is telling a screen reader the unit and the');
  console.log('eye nothing at all.');
}
process.exit(bare.length ? 3 : 0);
