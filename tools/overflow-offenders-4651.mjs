// overflow-offenders-4651.mjs — list every element whose box sticks out past the viewport.
//
// #4651. `overflow-culprit-4631.mjs` answers "which SUBTREE, if hidden, removes the
// overflow" — it walks down while a single child is solely responsible and stops the
// moment no one child is. That is the right question for a page with one offender and
// the wrong one for a page with several: it names the lowest COMMON ancestor, whose own
// box may fit perfectly well, and then you are staring at a 366px-wide div wondering how
// it overflows a 390px viewport.
//
// This asks the complementary question — "which boxes actually cross the right edge, or
// start left of zero" — and prints them deepest-first with the styles that decide whether
// a flex/grid child is allowed to shrink (`min-width`, `flex`, `white-space`, `overflow-x`).
// A leaf with `min-width: auto` under a `display: flex` parent is the usual answer.
//
// Reads `overflow` FIRST, like its sibling: if the page does not overflow, there are no
// offenders and any list would be noise.
//
// Usage: node overflow-offenders-4651.mjs <url> [widthPx]
// Exit:  0 no overflow · 3 overflow with offenders listed · 4 BLIND (nothing measured) · 2 usage

// Playwright is not a dependency of this repo — it lives in the npx cache that
// `look.sh` primes. Same resolver as `overflow-culprit-4631.mjs`; a bare
// `import { chromium } from 'playwright'` is MODULE_NOT_FOUND from `tools/`.
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
if (!url) { console.error('usage: overflow-offenders-4651.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1500);

  const report = await page.evaluate(() => {
    const doc = document.documentElement;
    const client = doc.clientWidth;
    const scrollWidth = doc.scrollWidth;
    const overflow = scrollWidth - client;

    const name = (el) => {
      const cls = (el.className && typeof el.className === 'string')
        ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.')
        : '';
      return el.tagName.toLowerCase() + cls;
    };
    const chainOf = (el) => {
      const out = [];
      for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) out.unshift(name(n));
      return out;
    };

    const all = Array.from(document.body.querySelectorAll('*'));
    let examined = 0;
    const offenders = [];

    for (const el of all) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      examined++;
      const past = Math.round((r.right - client) * 10) / 10;
      if (past <= 1 && r.left >= -1) continue;

      const parent = el.parentElement;
      const pcs = parent ? getComputedStyle(parent) : null;
      offenders.push({
        el: name(el),
        past,                                   // px beyond the right edge
        left: Math.round(r.left * 10) / 10,
        width: Math.round(r.width * 10) / 10,
        scrollWidth: el.scrollWidth,
        depth: chainOf(el).length,
        minWidth: cs.minWidth,
        flex: cs.flex,
        whiteSpace: cs.whiteSpace,
        overflowX: cs.overflowX,
        position: cs.position,
        parentDisplay: pcs ? pcs.display : null,
        parentName: parent ? name(parent) : null,
        text: (el.textContent || '').trim().slice(0, 60),
        chain: chainOf(el).slice(-4),
      });
    }

    // Deepest first: the leaf that sticks out is the one with a fix.
    offenders.sort((a, b) => b.depth - a.depth || b.past - a.past);
    return { client, scrollWidth, overflow, examined, offenders };
  });

  console.log(`examined ${report.examined} laid-out element(s) on ${url} at ${width}px`);
  console.log(`  client=${report.client} scrollWidth=${report.scrollWidth} overflow=${report.overflow}`);

  if (report.examined === 0) {
    console.log('BLIND: no laid-out element measured — the probe proved nothing');
    await browser.close();
    process.exit(4);
  }
  if (report.overflow <= 1) {
    console.log('--- no overflow, so no offenders ---');
    await browser.close();
    process.exit(0);
  }

  console.log(`  ${report.offenders.length} element(s) cross the edge, deepest first:\n`);
  for (const o of report.offenders.slice(0, 25)) {
    console.log(`  +${o.past}px  d${o.depth}  ${o.el}`);
    console.log(`      left=${o.left} width=${o.width} scrollWidth=${o.scrollWidth} min-width=${o.minWidth} flex=${o.flex}`);
    console.log(`      white-space=${o.whiteSpace} overflow-x=${o.overflowX} position=${o.position}`);
    console.log(`      parent=${o.parentName} (display:${o.parentDisplay})`);
    console.log(`      chain=${o.chain.join(' > ')}`);
    if (o.text) console.log(`      text=${JSON.stringify(o.text)}`);
    console.log('');
  }
  await browser.close();
  process.exit(3);
} catch (err) {
  console.error('probe failed:', err && err.message ? err.message : err);
  await browser.close();
  process.exit(4);
}
