// rail-contents-5973.mjs — what the "More <LEAGUE>" rail at the foot of a game page actually holds (#5973).
//
// A screenshot of a rail proves the four cards that fit the frame. This reads the rail's own DOM:
// the heading (with its count), every card title IN ORDER, and the rail's absolute y offset so a
// paired frame can be shot at an offset that was MEASURED rather than remembered — a live page
// grows as the game goes, so yesterday's SHOT_SCROLL is not today's.
//
// Case-insensitive on the heading: CSS uppercases "More MLB" to "MORE MLB", so searching the
// screen's casing finds nothing in the DOM.
//
// Usage: node tools/rail-contents-5973.mjs <url> [widthPx]
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
if (!url) { console.error('usage: rail-contents-5973.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
// NOT `networkidle`: a LIVE game page polls for score and price, so the network never goes
// idle and the wait times out — an instrument failure that reads like an unreachable page.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(6000);
// Scroll to the foot so a lazily-mounted rail is actually rendered before it is read.
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(2500);

const out = await page.evaluate(() => {
  const heads = [...document.querySelectorAll('h2,h3,div,span')].filter(
    (e) => /^\s*more\s+\S/i.test(e.textContent || '') && (e.textContent || '').length < 40,
  );
  if (!heads.length) return { found: false, docHeight: document.body.scrollHeight };
  // The innermost element carrying the heading text.
  const head = heads[heads.length - 1];
  const section = head.closest('section') || head.parentElement?.parentElement || head.parentElement;
  const links = [...(section?.querySelectorAll('a') || [])];
  const titles = links
    .map((a) => (a.textContent || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  const r = (section || head).getBoundingClientRect();
  return {
    found: true,
    heading: (head.textContent || '').trim(),
    cardCount: links.length,
    titles,
    sectionTopAbsolute: Math.round(r.top + window.scrollY),
    docHeight: document.body.scrollHeight,
  };
});

if (!out.found) {
  console.log(`NO "More <X>" RAIL FOUND — dead instrument or an absent rail, not a clean result.`);
  console.log(`docHeight=${out.docHeight}`);
} else {
  console.log(`heading      : ${JSON.stringify(out.heading)}`);
  console.log(`cards        : ${out.cardCount}`);
  out.titles.forEach((t, i) => console.log(`   ${i + 1}. ${t.slice(0, 90)}`));
  console.log(`section top  : ${out.sectionTopAbsolute}   docHeight=${out.docHeight}`);
  console.log(`SHOT_SCROLL  : ${Math.max(0, out.sectionTopAbsolute - 40)}  (with SHOT_H=844)`);
}

await browser.close();
