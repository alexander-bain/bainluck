// overflow-tryfix-4651.mjs — measure a page's overflow, inject candidate CSS, measure again.
//
// #4651. A CSS fix for horizontal overflow is cheap to write and expensive to verify:
// the only honest check is a real browser at a real width, and the local dev server is
// not the surface the bug was reported on. This loads PRODUCTION, reads `scrollWidth`,
// injects the candidate rules against the CSS-module class names by PREFIX
// (`[class*="presHeroHead"]`, since the shipped names are hashed), and reads it again.
//
// It proves the rules are sufficient BEFORE they are committed. It cannot prove they are
// necessary — drop a rule and re-run for that — and it says nothing about how the result
// LOOKS, which is what the screenshot is for.
//
// Usage: node overflow-tryfix-4651.mjs <url> <cssFile> [widthPx] [outPng]
// Exit:  0 fixed (overflow <= 1) · 3 still overflowing · 4 BLIND · 2 usage
//
// Pass `outPng` and it also shoots the patched page. Several candidate rule sets can
// all drive the overflow to 0 while looking quite different — a stranded right-aligned
// chip row, a clipped label — so the number picks the CANDIDATES and the picture picks
// the winner.

import { createRequire } from 'module';
import { existsSync, readdirSync, readFileSync } from 'fs';

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
const cssFile = process.argv[3];
const width = Number(process.argv[4] || 390);
const outPng = process.argv[5];
if (!url || !cssFile) { console.error('usage: overflow-tryfix-4651.mjs <url> <cssFile> [widthPx] [outPng]'); process.exit(2); }
const css = readFileSync(cssFile, 'utf8');

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1500);

  const before = await page.evaluate(() => {
    const d = document.documentElement;
    return { client: d.clientWidth, scrollWidth: d.scrollWidth, elements: document.body.querySelectorAll('*').length };
  });

  if (before.elements === 0) {
    console.log('BLIND: page laid out no elements');
    await browser.close();
    process.exit(4);
  }

  // Positive control: the selectors must MATCH something, or a green reading below
  // is just "I injected a stylesheet that styles nothing".
  const selectors = Array.from(new Set((css.match(/\[class\*="[^"]+"\]/g) || [])));
  const matched = await page.evaluate((sels) => sels.map((s) => ({ sel: s, n: document.querySelectorAll(s).length })), selectors);

  await page.addStyleTag({ content: css });
  await page.waitForTimeout(600);

  const after = await page.evaluate(() => {
    const d = document.documentElement;
    return { client: d.clientWidth, scrollWidth: d.scrollWidth };
  });

  console.log(`${url} at ${width}px`);
  console.log(`  BEFORE  client=${before.client} scrollWidth=${before.scrollWidth} overflow=${before.scrollWidth - before.client}`);
  console.log(`  selector match counts (0 anywhere = the rule is inert):`);
  for (const m of matched) console.log(`    ${m.sel} -> ${m.n}`);
  console.log(`  AFTER   client=${after.client} scrollWidth=${after.scrollWidth} overflow=${after.scrollWidth - after.client}`);

  const dead = matched.filter((m) => m.n === 0);
  if (dead.length) console.log(`  WARNING: ${dead.length} selector(s) matched nothing`);

  if (outPng) {
    // The overflowing row is rarely at the top of the page, and a viewport shot of
    // the masthead proves nothing about it. `TRYFIX_SCROLL_TO=<selector>` centres the
    // node under test first; without it you get the top of the page.
    const scrollTo = process.env.TRYFIX_SCROLL_TO;
    if (scrollTo) {
      const found = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        el.scrollIntoView({ block: 'center' });
        return true;
      }, scrollTo);
      console.log(found ? `  scrolled to ${scrollTo}` : `  WARNING: ${scrollTo} matched nothing — shooting the top`);
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: outPng, fullPage: false });
    console.log(`  shot (viewport) -> ${outPng}`);
  }

  const fixed = after.scrollWidth - after.client <= 1;
  console.log(fixed ? '--- FIXED' : '--- STILL OVERFLOWING');
  await browser.close();
  process.exit(fixed ? 0 : 3);
} catch (err) {
  console.error('probe failed:', err && err.message ? err.message : err);
  await browser.close();
  process.exit(4);
}
