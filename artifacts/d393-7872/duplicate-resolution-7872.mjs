// duplicate-resolution-7872.mjs — read the two resolution statements OFF THE SCREEN.
//
// #7872. The defect is a card printing `resolution_date` twice: once exactly in the
// eyebrow ("Resolves Oct 10, 2026") and once vaguely in the caption below it
// ("…; resolves within a month"). The payload cannot show it — both strings are
// correct on the wire and the duplication only exists once the card renders them
// together. So this opens the real page at phone width, walks every futures card,
// and reports the cards where BOTH appear, with a crop of each so the finding is
// read as a reader and not as a boolean.
//
// Usage: node duplicate-resolution-7872.mjs <url> <outdir>
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, writeFileSync } from 'fs';

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

const [url, outdir = '.'] = process.argv.slice(2);
if (!url) {
  console.error('usage: duplicate-resolution-7872.mjs <url> <outdir>');
  process.exit(2);
}
mkdirSync(outdir, { recursive: true });

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 120000 });
// Page one is virtualised/lazy — scroll it in so the cards below the fold mount.
for (let y = 0; y < 14000; y += 700) {
  await page.evaluate((v) => window.scrollTo(0, v), y);
  await page.waitForTimeout(120);
}
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(500);

const WINDOW = /resolv(?:es|ing) within (a day|two days|a week|a month)/i;
const EXACT = /(Resolves [A-Z][a-z]{2} \d{1,2}, \d{4}|Closes (in \d+[mh]|tomorrow|[A-Z][a-z]{2} \d{1,2}))/;

// THE CARD IS NOT THE LINK. `a[href^="/futures/"]` wraps the TITLE only — the
// eyebrow sits in the header row above it and the caption in the body below, both
// OUTSIDE the anchor. Keying on the anchor reported 0 duplicates on a page whose
// own text held 8 vague clauses and 25 exact lines; the two strings were never in
// the same element to begin with. So the containment test runs the other way:
// start at the vague clause the reader actually saw and climb to the smallest
// ancestor that also states the resolution exactly. That ancestor IS the card.
const { cards, hits } = await page.evaluate(
  ({ vagueSrc, exactSrc }) => {
    const VAGUE = new RegExp(vagueSrc, 'i');
    const EX = new RegExp(exactSrc);
    const all = Array.from(document.querySelectorAll('div,p,span,section,article'));
    const cardCount = document.querySelectorAll('a[href^="/futures/"]').length;
    // Leaf-most elements carrying the clause, so one clause is counted once.
    const leaves = all.filter(
      (el) =>
        VAGUE.test(el.textContent || '') &&
        !Array.from(el.children).some((c) => VAGUE.test(c.textContent || '')),
    );
    const found = [];
    const seen = new Set();
    for (const leaf of leaves) {
      let el = leaf;
      for (let up = 0; up < 8 && el; up += 1) {
        const t = el.innerText || '';
        const r = el.getBoundingClientRect();
        // A card, not the whole feed: it must state the resolution exactly and
        // still be card-sized.
        if (EX.test(t) && r.height > 40 && r.height < 900) {
          const key = `${Math.round(r.top + window.scrollY)}:${Math.round(r.height)}`;
          if (!seen.has(key)) {
            seen.add(key);
            found.push({
              text: t.trim(),
              exact: (t.match(EX) || [''])[0],
              vague: (t.match(VAGUE) || [''])[0],
              top: r.top + window.scrollY,
              height: r.height,
            });
          }
          break;
        }
        el = el.parentElement;
      }
    }
    return { cards: cardCount, hits: found };
  },
  { vagueSrc: WINDOW.source, exactSrc: EXACT.source },
);

// FAIL OPEN, LOUDLY. "0 cards print it twice" and "my selector or my regex missed
// the page" are the same output, and only one of them is a finding. So the raw
// counts the verdict rests on are printed every run.
const body = await page.evaluate(() => document.body.innerText);
const bodyVague = body.match(new RegExp(WINDOW.source, 'gi')) || [];
const bodyExact = body.match(new RegExp(EXACT.source, 'g')) || [];
console.log(`page text: ${bodyVague.length} vague clause(s), ${bodyExact.length} exact resolution line(s)`);
console.log(`  sample vague: ${JSON.stringify(bodyVague.slice(0, 4))}`);
console.log(`  sample exact: ${JSON.stringify(bodyExact.slice(0, 4))}`);
console.log(`futures cards on page: ${cards}`);
console.log(`cards printing the resolution TWICE: ${hits.length}`);
for (const [i, h] of hits.entries()) {
  const title = h.text.split('\n').slice(0, 3).join(' | ');
  console.log(`  [${i}] ${title}`);
  console.log(`       exact : ${h.exact}`);
  console.log(`       vague : ${h.vague}`);
  const y = Math.max(0, Math.round(h.top) - 12);
  await page.screenshot({
    path: `${outdir}/dup-${String(i).padStart(2, '0')}.png`,
    clip: { x: 0, y, width: 390, height: Math.min(Math.round(h.height) + 24, 700) },
    fullPage: true,
  });
}
writeFileSync(`${outdir}/dup-report.json`, JSON.stringify({ url, cards: cards.length, hits }, null, 1));
await browser.close();
process.exit(0);
