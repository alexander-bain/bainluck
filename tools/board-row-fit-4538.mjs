// board-row-fit-4538.mjs — measure where the tournament contender row's pixels actually go (#4538).
//
// The screenshot says "Alexander Z…" is clipped while the number column looks half empty. A
// screenshot cannot grade an ALLOCATION claim, so this reads the layout engine instead:
//
//   * the rendered `gridTemplateColumns` on `[data-testid="board-row"]`  -> the real tracks
//   * per-track client rects                                            -> where each px went
//   * the name node's scrollWidth vs clientWidth                        -> IS it clipped, and by how much
//   * the number cell's own text width vs its track                     -> is the track over-subscribed
//   * the row's right edge vs the card's content box                    -> is there trailing slack
//
// Truncation is reported from scrollWidth > clientWidth on the truncating node, never from
// looking for "…" in a screenshot: a clipped node's Range reports the UNCLIPPED extent.
//
// Usage: node board-row-fit-4538.mjs <url> [widthPx]
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
if (!url) { console.error('usage: board-row-fit-4538.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForSelector('[data-testid="board-row"]', { timeout: 30000 });

const out = await page.evaluate(() => {
  const rows = [...document.querySelectorAll('[data-testid="board-row"]')];
  const r2 = (n) => Math.round(n * 10) / 10;

  return rows.map((li) => {
    const cs = getComputedStyle(li);
    const liBox = li.getBoundingClientRect();
    const kids = [...li.children].map((el) => {
      const b = el.getBoundingClientRect();
      return { tag: el.tagName.toLowerCase(), left: r2(b.left), right: r2(b.right), w: r2(b.width) };
    });

    // The truncating node is the `.truncate` div holding the name.
    const nameCell = li.children[2];
    const clip = nameCell?.querySelector('.truncate');
    const nameSpan = clip?.querySelector('span');

    // The number's own ink, independent of its track.
    const prob = li.querySelector('[data-testid="row-probability"]');
    const delta = li.querySelector('[data-testid="row-delta"]');
    const inkOf = (el) => {
      if (!el) return null;
      const range = document.createRange();
      range.selectNodeContents(el);
      return r2(range.getBoundingClientRect().width);
    };

    return {
      entity: li.dataset.entity,
      rank: li.dataset.rank,
      tracks: cs.gridTemplateColumns,
      gap: cs.columnGap,
      padLeft: cs.paddingLeft,
      padRight: cs.paddingRight,
      rowW: r2(liBox.width),
      kids,
      name: nameSpan?.textContent ?? null,
      nameClientW: clip ? r2(clip.clientWidth) : null,
      nameScrollW: clip ? r2(clip.scrollWidth) : null,
      // The honest truncation test: the content wants more than the box gives it.
      clipped: clip ? clip.scrollWidth > clip.clientWidth + 0.5 : null,
      shortBy: clip ? r2(clip.scrollWidth - clip.clientWidth) : null,
      probText: prob?.textContent ?? null,
      probInkW: inkOf(prob),
      deltaText: delta?.textContent ?? null,
      deltaInkW: inkOf(delta),
      // Track 4 is the number block; how much of it is ink and how much is air.
      numberTrackW: kids[3]?.w ?? null,
      numberAir: kids[3] ? r2(kids[3].w - Math.max(inkOf(prob) ?? 0, inkOf(delta) ?? 0)) : null,
      sparkTrackW: kids[4]?.w ?? null,
      // Trailing slack: does the last track's right edge reach the row's content edge?
      trailingSlack: kids.length
        ? r2(liBox.right - parseFloat(cs.paddingRight) - kids[kids.length - 1].right)
        : null,
    };
  });
});

console.log(JSON.stringify({ url, width, rows: out }, null, 2));
await browser.close();
