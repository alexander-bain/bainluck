// answers-row-overlap-4136.mjs — does an ANSWERS row's TITLE ink collide with its ANSWER ink?
//
// #4136 shipped `familyRowTitles`: a row title splits into a `truncate` head and a
// `flex-shrink-0` tail carrying the bytes that distinguish it from its sibling. The
// production LOOK after the merge shows row 4 (`… - First 5 Innings Winner`) painting its
// tail THROUGH the outcome text. A screenshot cannot tell overlap from antialiasing, so
// this asks the layout engine instead.
//
// 🔴 THE INK BOX IS NOT THE ELEMENT BOX (same trap as grid-fit-4171). The title container is
// `flex-1 min-w-0` with VISIBLE overflow, so its element rect stops where flexbox put it while
// its glyphs carry on over the sibling. Measuring element rects would report a tidy 0px gap and
// answer a question nobody asked. Walk to the text nodes and union their Ranges.
//
// Usage: node answers-row-overlap-4136.mjs <url> [widthPx]
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
if (!url) { console.error('usage: answers-row-overlap-4136.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'latency-295' });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForSelector('a[href^="/futures/"]', { timeout: 30000 });

const out = await page.evaluate(() => {
  // 🔴 SECOND TRAP, and the first version of this probe fell in it and reported all 5 rows
  // overlapping including two that render perfectly clean: A CLIPPED TEXT NODE'S RANGE STILL
  // REPORTS THE UNCLIPPED GEOMETRY. `truncate` is overflow:hidden + text-overflow:ellipsis, a
  // PAINT-time clip — the Range of the text inside it happily reports where the full string
  // *would* have ended (280px on a 390px viewport), because the DOM range knows nothing about
  // the ellipsis. Union those and every long title "overlaps" its answer by construction.
  // So: clamp every rect to the content box of its nearest overflow-hidden ancestor.
  const clipRightOf = (node, stopAt) => {
    let el = node.parentElement, limit = Infinity;
    while (el) {
      const cs = getComputedStyle(el);
      if (cs.overflowX === 'hidden' || cs.overflowX === 'clip') {
        limit = Math.min(limit, el.getBoundingClientRect().right - (parseFloat(cs.paddingRight) || 0));
      }
      if (el === stopAt) break;
      el = el.parentElement;
    }
    return limit;
  };

  // Union of the VISIBLE glyph rects of every non-blank text node under `el`.
  const inkOf = (el) => {
    if (!el) return null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let l = Infinity, r = -Infinity, txt = '', clipped = false;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.nodeValue.trim()) continue;
      const clipR = clipRightOf(n, null);
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const rect of range.getClientRects()) {
        if (rect.width <= 0) continue;
        if (rect.left >= clipR) { clipped = true; continue; } // wholly clipped away
        const right = Math.min(rect.right, clipR);
        if (right > clipR - 0.5 && rect.right > clipR + 0.5) clipped = true;
        l = Math.min(l, rect.left);
        r = Math.max(r, right);
      }
      txt += n.nodeValue;
    }
    return r > l ? { left: l, right: r, clipped, text: txt.replace(/\s+/g, ' ').trim() } : null;
  };

  const rows = [...document.querySelectorAll('a[href^="/futures/"]')]
    .filter((a) => a.className.includes('items-center') && a.children.length >= 1)
    .map((a) => {
      const kids = [...a.children];
      // child 0 is the title container (`flex-1 min-w-0`); the answer column is the
      // sibling that contains a "%" — identified by content, never by index, because a
      // row with no priced leader renders a different second child.
      const titleEl = kids[0];
      const answerEl = kids.slice(1).find((k) => k.textContent.includes('%')) || null;
      const title = inkOf(titleEl);
      const answer = inkOf(answerEl);
      const aRect = a.getBoundingClientRect();
      const row = {
        title: title && title.text,
        answer: answer && answer.text,
        titleRight: title && Math.round(title.right - aRect.left),
        answerLeft: answer && Math.round(answer.left - aRect.left),
      };
      if (title && answer) {
        row.gapPx = Math.round(answer.left - title.right);
        row.OVERLAP = answer.left < title.right - 0.5;
      }
      // does any ink escape the row's own padding box?
      const cs = getComputedStyle(a);
      const padR = parseFloat(cs.paddingRight) || 0;
      const inner = aRect.right - padR;
      row.spillPx = answer ? Math.round(Math.max(0, answer.right - inner)) : 0;
      return row;
    });
  return { viewport: window.innerWidth, rows };
});

console.log(JSON.stringify(out, null, 2));
const bad = out.rows.filter((r) => r.OVERLAP);
console.log(`\nrows=${out.rows.length} overlapping=${bad.length}`);
for (const r of bad) console.log(`  OVERLAP ${r.gapPx}px: "${r.title}" x "${r.answer}"`);
await browser.close();
process.exit(bad.length ? 1 : 0);
