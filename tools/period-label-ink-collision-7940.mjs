#!/usr/bin/env node
/**
 * #7940 — does the SERIES cross a period label's glyphs, and would moving the
 * label help?
 *
 * ═══ WHY THIS IS A BROWSER MEASUREMENT AND NOT A DATA ONE ═══
 *
 * The obvious instrument reads the payload, computes the y-domain and asks "is
 * the series within N% of the top at this marker's x?". That instrument cannot
 * be built honestly: the chip band is a PIXEL quantity (`PERIOD_CHIP_BAND_PX =
 * 15`, measured off a rendered page) and both charts size themselves through
 * `ResponsiveContainer width="100%" height="100%"` inside a `flex-1` parent, so
 * neither the component nor a replay knows the plot's pixel height. Converting
 * 15px into a fraction of the domain needs a height nobody has. So the only
 * place the question has an answer is the rendered page, and that is where this
 * asks it.
 *
 * ═══ WHAT IT MEASURES ═══
 *
 * For every period label actually painted, in CLIENT coordinates (so a transform
 * on any ancestor cannot silently shift one of the two operands):
 *
 *   - the label's own ink box, from `getBoundingClientRect()`;
 *   - every plotted series path, sampled along its length with
 *     `getPointAtLength()` and mapped through `getScreenCTM()` — never by
 *     parsing `d`, which would re-implement the renderer's own arithmetic;
 *   - whether any sample lands inside the label's box (COLLIDES), and by how
 *     much vertically.
 *
 * ═══ AND WHAT IT COSTS THE THREE CANDIDATE REPAIRS ═══
 *
 * The issue lists three repairs and costs none. Each needs one number this
 * cannot get from a screenshot:
 *
 *   - "drop the label below the series" needs the DROP, in rows of
 *     `PERIOD_LABEL_ROW_HEIGHT_PX`, that would clear the ink — and whether the
 *     plot is deep enough to spend it. Reported as `rowsToClear`.
 *   - "reserve a gutter above the plot" needs the plot height it would cost.
 *     Reported as `plot.height`.
 *   - "move the strip to the bottom" needs to know the bottom band is actually
 *     free, which on a two-sided chart it need not be. Reported as
 *     `bottomBandFree` — the same collision test against a mirrored box.
 *
 * Usage:
 *   node tools/period-label-ink-collision-7940.mjs <baseUrl> <eventId> <outDir> <tag>
 */
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, writeFileSync } from 'node:fs';

// Playwright lives in the npx cache, not in this repo — copied verbatim from
// the sibling probes. A bare `import { chromium } from 'playwright'` resolves
// from the tool's own directory and throws ERR_MODULE_NOT_FOUND.
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

const [, , baseUrl, eventId, outDirArg, tagArg] = process.argv;
const tag = tagArg || 'run';
const outDir = outDirArg || 'artifacts/7940';

if (!baseUrl || !eventId) {
  console.error('usage: node tools/period-label-ink-collision-7940.mjs <baseUrl> <eventId> <outDir> <tag>');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const PAGE_URL = `${baseUrl.replace(/\/$/, '')}/events/${eventId}`;

// Asked of the parsed HOST, never of the URL as a string: an unanchored
// `/localhost/` also matches `https://bainluck.com/localhost`
// (`js/regex/missing-regexp-anchor`, HIGH — ux/1429 shipped that trap twice).
// `globalThis.URL` because a module-level `const URL` in a sibling tool shadowed
// the constructor file-wide and the function's own catch ate the TypeError.
function isLoopbackBase(url) {
  let host;
  try {
    host = new globalThis.URL(url).hostname;
  } catch {
    return false;
  }
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}
const LOCAL_PAGE = isLoopbackBase(baseUrl);

// Copied from the sibling probes rather than re-derived: a hand-rolled launch
// dies with a Mach-port error on this machine where these exact flags work.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!LOCAL_PAGE) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  timezoneId: 'UTC',
});
const page = await context.newPage();

await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 90_000 });
// The chips only exist once a chart has mounted AND recharts has a viewport.
await page.waitForSelector('[data-period-labels]', { timeout: 60_000 }).catch(() => {});
await page.waitForTimeout(4000);

// The consent banner overlaps the lower half of the page, which is where the
// second chart lives. Dismiss it or the score-differential arm measures a
// chart nobody can see.
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button, [role="button"]')].find((b) =>
    /^(accept|agree|got it)/i.test((b.textContent || '').trim()),
  );
  if (btn) btn.click();
});
await page.waitForTimeout(1200);

const read = await page.evaluate(() => {
  const PERIOD_LABEL_ROW_HEIGHT_PX = 13; // lib/periodMarkers.ts — quoted, not guessed.

  const out = [];
  for (const wrapper of document.querySelectorAll('[data-period-labels]')) {
    const svg = wrapper.querySelector('svg.recharts-surface');
    if (!svg) continue;

    // ═══ THE PLOT RECT, AND WHY IT IS NOT READ FROM THE GRID ═══
    //
    // 🪤 The obvious reads all return a 0x0 box and every number derived from
    // one still LOOKS like a measurement. `.recharts-cartesian-grid-bg` is not
    // mounted unless `fill` is set; the clipPath rect that does carry the exact
    // plot geometry lives inside `<defs>`, which is never rendered, so
    // `getBoundingClientRect()` on it is 0x0 by specification rather than by
    // accident. A first pass here reported `plot=0x0` and went on to print
    // `tallestGap=464px` and `bottomFree=true` for every label — both computed
    // from `plot.y = 0`, both plausible, both meaningless.
    //
    // So the rect is taken from ink that is actually painted and actually spans
    // the plot: the grid lines and the period rules themselves. A vertical
    // reference rule is drawn from the plot's top edge to its bottom edge, and
    // a horizontal grid line from its left to its right — so the union of their
    // boxes IS the plot rect, measured off the renderer with nothing assumed
    // about margins.
    let plot = null;
    {
      const spans = [
        ...svg.querySelectorAll('.recharts-cartesian-grid line'),
        ...svg.querySelectorAll('.recharts-reference-line line'),
      ]
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 0 || r.height > 0);
      if (spans.length) {
        const x = Math.min(...spans.map((r) => r.x));
        const y = Math.min(...spans.map((r) => r.y));
        const right = Math.max(...spans.map((r) => r.x + r.width));
        const bottom = Math.max(...spans.map((r) => r.y + r.height));
        // A degenerate union is still a non-answer; say so rather than divide by it.
        if (right - x > 1 && bottom - y > 1) plot = { x, y, width: right - x, height: bottom - y };
      }
    }

    // Every drawn series, sampled along its own length. `getPointAtLength` +
    // `getScreenCTM` rather than parsing `d`: the point of the measurement is
    // where the ink IS, and only the renderer knows that.
    const seriesPts = [];
    for (const path of svg.querySelectorAll('path.recharts-curve')) {
      const d = path.getAttribute('d');
      if (!d || d.length < 4) continue;
      // A reference line is also a curve in recharts' class vocabulary; the
      // series are the ones under a Line/Area layer.
      const layer = path.closest('.recharts-line, .recharts-area');
      if (!layer) continue;
      let len = 0;
      try {
        len = path.getTotalLength();
      } catch {
        continue;
      }
      if (!Number.isFinite(len) || len <= 0) continue;
      const ctm = path.getScreenCTM();
      if (!ctm) continue;
      const steps = Math.min(2000, Math.max(200, Math.ceil(len)));
      for (let i = 0; i <= steps; i++) {
        const p = path.getPointAtLength((len * i) / steps);
        const sp = new DOMPoint(p.x, p.y).matrixTransform(ctm);
        seriesPts.push({ x: sp.x, y: sp.y, stroke: path.getAttribute('stroke') || '' });
      }
    }

    // The period labels. A reference-line label is a <text> inside the
    // reference-line group; the Start/Final markers are drawn the same way, so
    // they are read and reported rather than silently filtered — a collision on
    // "Final" is the same defect.
    const labels = [];
    for (const g of svg.querySelectorAll('.recharts-reference-line')) {
      for (const t of g.querySelectorAll('text')) {
        const text = (t.textContent || '').trim();
        if (!text) continue;
        const r = t.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        labels.push({ text, box: { x: r.x, y: r.y, w: r.width, h: r.height } });
      }
    }

    const hitsIn = (box) =>
      seriesPts.filter(
        (p) => p.x >= box.x && p.x <= box.x + box.w && p.y >= box.y && p.y <= box.y + box.h,
      );

    const measured = labels.map((l) => {
      const hits = hitsIn(l.box);
      // How far DOWN the label would have to move to sit under every series
      // sample that currently shares its x-span. Answered against the x-span
      // only, because a drop does not change the label's x.
      const overX = seriesPts.filter((p) => p.x >= l.box.x && p.x <= l.box.x + l.box.w);
      const lowestInkAtX = overX.length ? Math.max(...overX.map((p) => p.y)) : null;
      const needPx = lowestInkAtX === null ? 0 : Math.max(0, lowestInkAtX - l.box.y + 1);
      const rowsToClear = Math.ceil(needPx / PERIOD_LABEL_ROW_HEIGHT_PX);

      // ⭐ THE DECISIVE NUMBER, and the one neither the issue nor a screenshot
      // has. `rowsToClear` answers "how far down to get under EVERYTHING",
      // which is only the right question if the ink at this x is one band. It
      // is not: the dashed source series swing across the whole plot, so the
      // useful question is whether ANY gap in the ink at this x is tall enough
      // to hold a label. If the tallest gap is shorter than the label, no
      // vertical move can help and the whole "drop it" family of repairs is
      // dead on this chart — which is a costing result, not a failure.
      let tallestGapPx = null;
      let tallestGapTop = null;
      if (plot && overX.length) {
        const ys = [...overX.map((p) => p.y)].sort((a, b) => a - b);
        let prev = plot.y;
        let best = 0;
        let bestTop = plot.y;
        for (const y of ys) {
          if (y - prev > best) {
            best = y - prev;
            bestTop = prev;
          }
          prev = Math.max(prev, y);
        }
        if (plot.y + plot.height - prev > best) {
          best = plot.y + plot.height - prev;
          bestTop = prev;
        }
        tallestGapPx = Math.round(best);
        tallestGapTop = Math.round(bestTop - plot.y);
      }

      // The same test against the mirrored box at the bottom of the plot —
      // "move the strip to the bottom" is only a repair if that band is empty.
      let bottomBandFree = null;
      if (plot) {
        const offsetFromTop = l.box.y - plot.y;
        const mirrored = {
          x: l.box.x,
          y: plot.y + plot.height - offsetFromTop - l.box.h,
          w: l.box.w,
          h: l.box.h,
        };
        bottomBandFree = hitsIn(mirrored).length === 0;
      }

      return {
        text: l.text,
        box: { x: Math.round(l.box.x), y: Math.round(l.box.y), w: Math.round(l.box.w), h: Math.round(l.box.h) },
        collides: hits.length > 0,
        hitCount: hits.length,
        strokes: [...new Set(hits.map((h) => h.stroke))],
        needPx: Math.round(needPx),
        rowsToClear,
        tallestGapPx,
        tallestGapTop,
        fitsInAGap: tallestGapPx === null ? null : tallestGapPx >= l.box.h,
        bottomBandFree,
      };
    });

    out.push({
      labelsAttr: wrapper.getAttribute('data-period-labels') || '',
      rowsAttr: wrapper.getAttribute('data-period-label-rows') || '',
      plot: plot
        ? { x: Math.round(plot.x), y: Math.round(plot.y), w: Math.round(plot.width), h: Math.round(plot.height) }
        : null,
      seriesSamples: seriesPts.length,
      labels: measured,
    });
  }
  return out;
});

const charts = read;
for (let i = 0; i < charts.length; i++) {
  const c = charts[i];
  const colliding = c.labels.filter((l) => l.collides);
  console.log(
    `chart ${i}: labels=[${c.labelsAttr}] plot=${c.plot ? `${c.plot.w}x${c.plot.h}` : 'unknown'} ` +
      `samples=${c.seriesSamples} painted=${c.labels.length} COLLIDING=${colliding.length}`,
  );
  for (const l of c.labels) {
    console.log(
      `   ${l.collides ? 'HIT ' : '    '}${l.text.padEnd(6)} box=${l.box.x},${l.box.y} ${l.box.w}x${l.box.h}` +
        ` hits=${String(l.hitCount).padStart(4)} needPx=${String(l.needPx).padStart(3)}` +
        ` rowsToClear=${String(l.rowsToClear).padStart(2)} tallestGap=${String(l.tallestGapPx).padStart(4)}px@+${l.tallestGapTop}` +
        ` fitsInAGap=${l.fitsInAGap} bottomFree=${l.bottomBandFree}`,
    );
  }
}

// One screenshot per chart, so the numbers can always be read back as a picture.
const wrappers = await page.$$('[data-period-labels]');
for (let i = 0; i < wrappers.length; i++) {
  await wrappers[i].screenshot({ path: `${outDir}/${tag}-chart${i}.png` }).catch(() => {});
}
await page.screenshot({ path: `${outDir}/${tag}-page.png`, fullPage: true }).catch(() => {});
writeFileSync(
  `${outDir}/${tag}.json`,
  JSON.stringify({ url: PAGE_URL, at: new Date().toISOString(), charts }, null, 2),
);

await browser.close();

const anyCollision = charts.some((c) => c.labels.some((l) => l.collides));
console.log(anyCollision ? 'VERDICT: at least one label has series ink through it' : 'VERDICT: no label collides');
