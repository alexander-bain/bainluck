// card-chip-sum.mjs — read the shared EventCard's two chips OFF THE SCREEN and add them up (#2787).
//
// The defect is a client-side double rounding, so no payload can show it: the server's two numbers
// were already right. This opens the real page, waits for the cards, and reads the rendered text.
//
// WHAT COUNTS AS A CARD'S PAIR. The shared card renders exactly two probability chips, one per team
// row, inside its `a[href^="/events/"]` shell. Cards with no price print "-" and are counted
// separately rather than skipped silently — "printed nothing" and "printed a legal pair" are
// different facts and collapsing them is how a proof reports green over an empty page.
//
// Usage: node tools/card-chip-sum.mjs <url> [url ...]
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

const urls = process.argv.slice(2);
if (urls.length === 0) {
  console.error('usage: card-chip-sum.mjs <url> [url ...]');
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

// A FRESH BROWSER PER URL. `--single-process` chromium tears down the whole browser when a page
// closes, so a loop that reuses one instance dies on the second URL with "Target page, context or
// browser has been closed" — after printing a clean first row, which is the worst way to fail.
let violations = 0;
let pairs = 0;
let priceless = 0;

for (const url of urls) {
  const browser = await chromium.launch({ headless: true, args });
  const page = await browser.newPage({ viewport: { width: 1280, height: 2400 } });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('a[href^="/events/"]', { timeout: 25000 }); } catch {}
  await page.waitForTimeout(3500);

  const cards = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll('a[href^="/events/"]')) {
      const text = (el.innerText || '').replace(/\s+/g, ' ');
      // Only the two team chips are bare `NN%`. A "Proj 6-4" or a date carries no %.
      const pcts = (text.match(/(?<!\d)(\d{1,3})%/g) || []).map((s) => parseInt(s, 10));
      const dashes = (text.match(/(?:^|\s)-(?:\s|$)/g) || []).length;
      out.push({ href: el.getAttribute('href'), pcts, dashes, head: text.slice(0, 70) });
    }
    return out;
  });

  let urlPairs = 0;
  for (const c of cards) {
    if (c.pcts.length !== 2) {
      if (c.pcts.length === 0) priceless += 1;
      continue;
    }
    urlPairs += 1;
    pairs += 1;
    const sum = c.pcts[0] + c.pcts[1];
    if (sum !== 100) {
      violations += 1;
      console.log(`  VIOLATION ${c.href}  ${c.pcts[0]}% + ${c.pcts[1]}% = ${sum}   ${c.head}`);
    }
  }
  console.log(`${url}\n  cards=${cards.length} pairs=${urlPairs} violations-so-far=${violations}`);
  await browser.close();
}

console.log(`\npairs read: ${pairs}   cards with no price: ${priceless}   violations: ${violations}`);
if (pairs === 0) {
  // The anti-vacuity refusal. Zero pairs is what a blank page and a perfect page have in common.
  console.log('REFUSED — zero pairs read. This proves nothing; the page did not render its cards.');
  process.exit(3);
}
console.log(violations === 0 ? 'PASS — every printed pair sums to 100.' : `FAIL — ${violations} pair(s) do not sum to 100.`);
process.exit(violations === 0 ? 0 : 1);
