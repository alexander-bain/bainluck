// prop-tile-fit-2788.mjs — where do the Bigger Picture prop tiles' pixels go? (#2788 / #3417 leftover)
//
// The screenshot shows `Alexander Zv…` and `Karen Khacha…` in tiles that sit alone in their
// group with two thirds of the row empty beside them. A screenshot cannot grade an ALLOCATION
// claim, so this reads the layout engine:
//
//   * the group container's rendered `gridTemplateColumns`  -> the real tracks, and whether the
//     track count is fixed or derived from how many tiles the group actually holds
//   * per-tile client rects                                 -> where each px went, and how much
//     of the row's width is unoccupied
//   * the name node's scrollWidth vs clientWidth            -> IS it clipped, and by how much
//
// Truncation is reported from scrollWidth > clientWidth on the truncating node, never from
// looking for "…" in a screenshot: a clipped node's Range reports the UNCLIPPED extent, and a
// title that happens to end in an ellipsis character is not the same fact.
//
// The tiles are found STRUCTURALLY (walk down from the Bigger Picture heading), never by the
// truncation class itself — that class is the defect, so a selector built on it reads correctly
// against the broken arm and returns null against the fixed one, which reads as "no tiles".
//
// Usage: node prop-tile-fit-2788.mjs <url> [widthPx]
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
if (!url) { console.error('usage: prop-tile-fit-2788.mjs <url> [widthPx]'); process.exit(2); }

const local = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(url);
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push(local ? '--proxy-bypass-list=127.0.0.1;localhost' : '--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

// A LOCAL BUILD CANNOT REACH THE API, AND THE BYPASS LIST ABOVE IS NOT ENOUGH (#4593).
// Bypassing the proxy for loopback is what makes the local SERVER reachable; it does
// nothing for the page's OWN fetches to `api.bainluck.com`, which this sandbox only
// grants to `curl`. Without it the tiles never render and the probe reports zero
// groups — indistinguishable from "the fix removed the tiles", which is the single
// most misleading thing an after-measurement can say. Same shim as
// `tools/grid-name-fit-4558.mjs`, and deliberately scoped to local URLs: the
// production measurement must stay byte-identical to the one the defect was filed
// with, so no route interception exists on that path at all.
if (local) {
  const { execFileSync } = await import('child_process');
  await page.route('**://api.bainluck.com/**', async (route) => {
    const target = route.request().url();
    let body;
    try {
      // curl, not the browser: this process has the session egress the page does not.
      body = execFileSync('curl', ['-sS', '--max-time', '45', target], {
        maxBuffer: 64 * 1024 * 1024,
        encoding: 'utf8',
      });
    } catch (err) {
      console.error(`  ! upstream failed ${target}: ${err.message}`);
      return route.fulfill({ status: 502, contentType: 'application/json', body: '{}' });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body,
    });
  });
}

// NOT networkidle: a page that polls never idles and `goto` just times out at 90s.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(4000);

// Scroll the whole page so lazy sections below the fold actually lay out.
await page.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 400) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 40));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(600);

const out = await page.evaluate(() => {
  const r2 = (n) => Math.round(n * 10) / 10;
  const txt = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();

  // Anchor on the section heading, not on a class.
  const heads = [...document.querySelectorAll('h1,h2,h3,h4')];
  const bp = heads.find((h) => /bigger picture/i.test(txt(h)));
  if (!bp) return { error: 'no Bigger Picture heading found' };

  // The section is the nearest ancestor that also contains the tiles.
  let section = bp.parentElement;
  for (let i = 0; i < 6 && section; i++) {
    if (section.querySelectorAll('*').length > 40) break;
    section = section.parentElement;
  }

  // A "group" = the scroller that directly holds the tiles. The tiles are links to
  // `/futures/{id}`, so anchor on THAT and walk up one level — never on the flex/grid
  // display value, which is an implementation detail the fix is allowed to change
  // (the first version of this probe looked for `display: grid`, found the flex row the
  // component actually uses, and reported zero groups on a page full of tiles).
  const tileLinks = [...section.querySelectorAll('a[href^="/futures/"]')];
  const grids = [...new Set(tileLinks.map((a) => a.parentElement))].filter(Boolean);

  const groups = grids.map((g) => {
    const cs = getComputedStyle(g);
    const gb = g.getBoundingClientRect();
    const tiles = [...g.children].map((t) => {
      const tb = t.getBoundingClientRect();
      // The name node: the deepest element whose own text is clipped, else the widest text node.
      const cands = [t, ...t.querySelectorAll('*')].filter((el) => el.children.length === 0 && txt(el));
      const clipped = cands
        .map((el) => ({ el, over: el.scrollWidth - el.clientWidth }))
        .filter((c) => c.over > 0)
        .sort((a, b) => b.over - a.over)[0];
      return {
        w: r2(tb.width),
        left: r2(tb.left),
        text: txt(t).slice(0, 60),
        clipped: clipped
          ? {
              text: txt(clipped.el),
              clientWidth: clipped.el.clientWidth,
              scrollWidth: clipped.el.scrollWidth,
              overflowPx: clipped.over,
              title: clipped.el.getAttribute('title') || clipped.el.closest('[title]')?.getAttribute('title') || null,
              ariaLabel: clipped.el.getAttribute('aria-label') || clipped.el.closest('[aria-label]')?.getAttribute('aria-label') || null,
            }
          : null,
      };
    });
    const occupied = tiles.reduce((s, t) => s + t.w, 0);
    return {
      testid: g.getAttribute('data-testid') || null,
      cls: (g.className || '').toString().slice(0, 140),
      gridTemplateColumns: cs.gridTemplateColumns,
      gap: cs.gap,
      containerW: r2(gb.width),
      tileCount: tiles.length,
      occupiedW: r2(occupied),
      unusedW: r2(gb.width - occupied - (tiles.length - 1) * parseFloat(cs.columnGap || 0)),
      tiles,
    };
  });

  return { viewport: window.innerWidth, groups: groups.filter((g) => g.tileCount >= 1) };
});

console.log(JSON.stringify(out, null, 2));
await browser.close();
