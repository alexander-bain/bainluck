// props-row-fit-6798.mjs — measure the WHAT HIT prop rows of an event page and report which
// labels the value chip has clipped, plus how many rows collapse to a shared visible string.
//
// #6798: on a SETTLED page with a MIXED grade list (some rows graded, some withheld) the
// withheld rows print `Resolved · grading unavailable` in a `shrink-0` span, and the label
// beside it is `flex-1 min-w-0 truncate` — so the label is the only thing in the row that can
// yield. #6129 fixed the all-ungraded page by dropping the chip; it deliberately did NOT fix
// the mixed page, because there the chip is the only place a reader learns this row is
// ungraded. So the mixed page still clips.
//
// 🔴 THIS IS NOT A jsdom MEASUREMENT AND MUST NOT BE ONE. jsdom reports every `scrollWidth` as
// 0 and every `innerText` as complete, so it calls this page clean — which is what "raster-only
// defect" in the issue means. Real layout or nothing: we drive Chromium and read the boxes.
//
// The visible prefix is measured with a DOM Range walked character by character against the
// span's own clientWidth, NOT estimated from a font metric — `truncate` is
// `text-overflow: ellipsis`, so the browser's own break point is the only true one.
//
// APPLY_FIX=1 swaps `truncate` -> `line-clamp-2` on the label spans of the LIVE page before
// measuring, which is the A/B this fix needs and the only one available while the specimen is
// alive: a local render of the branch cannot be had here (the page fetches client-side and the
// API does not answer a `127.0.0.1` origin, so `next dev` serves a shell that looks exactly
// like a probe finding nothing). It measures the CSS half of the change on real rows; the jest
// guard measures the source half — that the component emits that class and not `truncate`.
// The two together are the chain. Neither alone is the claim.
//
// usage: node tools/props-row-fit-6798.mjs <url> [out.png] [width=390]
//        APPLY_FIX=1 node tools/props-row-fit-6798.mjs <url> [out.png] [width=390]
// exit 0 = measured (read the JSON) · 4 = no props section / no rows found
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) for (const d of readdirSync(npx)) { const p = `${npx}/${d}/node_modules/`; if (existsSync(`${p}playwright`)) return p; }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');
const [url, out, widthArg] = process.argv.slice(2);
const width = Number(widthArg) || 390;
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const localTarget = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url);
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) { args.push(`--proxy-server=${proxy}`); if (!localTarget) args.push('--proxy-bypass-list=<-loopback>'); }
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width, height: 844 }, extraHTTPHeaders: { 'x-bainluck-origin': 'ux' } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForTimeout(2500);
// The consent banner is fixed to the bottom of the viewport, so it lands ON the band whatever
// the band is and both arms photograph the cookie notice instead of the rows. Dismiss it
// before anything is measured or shot. Best-effort: a page without one must not fail here.
try {
  const accept = page.getByRole('button', { name: /accept/i }).first();
  if (await accept.isVisible({ timeout: 3000 })) { await accept.click(); await page.waitForTimeout(600); }
} catch { /* no banner on this load */ }
// The props section is far down a lazy page; scroll it into existence before measuring.
for (let i = 0; i < 24; i++) { await page.evaluate(() => window.scrollBy(0, window.innerHeight)); await page.waitForTimeout(250); }
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(1200);

// The frontend commit this measurement is OF — read in the same context as the numbers, never
// from a separate request (gotcha: a bundle can roll between two calls and the report lies).
const marker = await page.evaluate(() => document.querySelector('meta[name="bainluck-frontend-commit"]')?.content || null);

// The A/B arm. Done in the page, on the rows just measured, so nothing about the specimen,
// the bundle or the viewport differs between the two readings except the one class.
// 🔴 A STYLESHEET, NOT `classList`. Mutating the class on a React page is reverted by the next
// render, and the next render lands between the measurement and the shutter: the first version
// of this rig measured `clippedRows: 0` and then photographed a frame byte-identical to the
// BEFORE — a passing A/B and one picture filed twice. An injected rule cannot be re-rendered
// away. These four declarations are what Tailwind's `line-clamp-2` compiles to, and the
// `white-space: normal` is `truncate`'s `nowrap` being lifted — the precedent's whole point.
const applied = await page.evaluate((apply) => {
  if (!apply) return 0;
  const style = document.createElement('style');
  style.textContent = `#props-script span.flex-1 {
    white-space: normal !important;
    display: -webkit-box !important;
    -webkit-box-orient: vertical !important;
    -webkit-line-clamp: 2 !important;
    overflow: hidden !important;
  }`;
  document.head.appendChild(style);
  return document.querySelectorAll('#props-script span.flex-1').length;
}, process.env.APPLY_FIX === '1');

const data = await page.evaluate(() => {
  const sec = document.querySelector('#props-script');
  if (!sec) return { error: 'NO_PROPS_SECTION' };
  const blurb = sec.querySelector('p.text-xs')?.textContent?.trim() || null;
  const eyebrow = sec.querySelector('span.uppercase')?.textContent?.trim() || null;

  // How much of a truncated span the reader actually sees: walk a Range forward until it
  // exceeds the span's content box. This is the browser's own ellipsis point, not a guess.
  const visiblePrefix = (span) => {
    const text = span.textContent || '';
    if (span.scrollWidth <= span.clientWidth) return text;
    const node = span.firstChild;
    if (!node || node.nodeType !== 3) return text;
    const r = document.createRange();
    let lo = 0, hi = text.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      r.setStart(node, 0); r.setEnd(node, mid);
      if (r.getBoundingClientRect().width <= span.clientWidth) lo = mid; else hi = mid - 1;
    }
    return text.slice(0, lo);
  };

  const rows = [];
  for (const row of sec.querySelectorAll('div.flex.items-center.gap-3')) {
    const label = row.querySelector('span.flex-1');
    if (!label) continue;
    // The value slot is whatever sits to the right of the label — a chip, a dash, a number.
    const value = row.lastElementChild === label ? null : row.lastElementChild;
    rows.push({
      label: (label.textContent || '').trim(),
      labelClient: Math.round(label.clientWidth),
      labelScroll: Math.round(label.scrollWidth),
      clipped: label.scrollWidth > label.clientWidth,
      // The clamp's OWN bound. Under `line-clamp-2` a label that needs a third line is
      // cut vertically, and `scrollWidth` says nothing about it — so a fix measured only
      // by the horizontal test would report "0 clipped" on a label the reader still
      // cannot read. This is the assertion behind "nothing measured reaches the clamp".
      clampedVertically: label.scrollHeight > label.clientHeight + 1,
      lines: Math.round(label.scrollHeight / (parseFloat(getComputedStyle(label).lineHeight) || 20)),
      visible: visiblePrefix(label).trim(),
      value: value ? (value.textContent || '').trim() : null,
      valueWidth: value ? Math.round(value.getBoundingClientRect().width) : 0,
    });
  }
  return { blurb, eyebrow, rows };
});

if (data.error || !data.rows?.length) {
  console.error(`NO ROWS: ${data.error || 'props section held no rows'}`);
  await browser.close();
  process.exit(4);
}

const rows = data.rows;
const withheld = rows.filter((r) => r.value && /grading unavailable/i.test(r.value));
const clipped = rows.filter((r) => r.clipped);
const clippedWithheld = withheld.filter((r) => r.clipped);
// The number the issue is actually about: how many QUESTIONS the section still asks. Two rows
// that clip to the same string have stopped being two questions to the reader.
const visibleStrings = new Set(rows.map((r) => r.visible));
const withheldVisible = new Set(withheld.map((r) => r.visible));
const sharing = withheld.filter((r) => withheld.filter((o) => o.visible === r.visible).length > 1).length;

console.log(JSON.stringify({
  marker, width,
  fixApplied: process.env.APPLY_FIX === '1' ? applied : false,
  clampedVertically: rows.filter((r) => r.clampedVertically).length,
  maxLines: Math.max(...rows.map((r) => r.lines || 1)),
  eyebrow: data.eyebrow, blurb: data.blurb,
  rows: rows.length,
  withheld: withheld.length,
  chipWidth: withheld.length ? Math.max(...withheld.map((r) => r.valueWidth)) : null,
  labelWidthWithChip: withheld.length ? Math.min(...withheld.map((r) => r.labelClient)) : null,
  labelWidthNoChip: rows.filter((r) => !withheld.includes(r)).length
    ? Math.max(...rows.filter((r) => !withheld.includes(r)).map((r) => r.labelClient)) : null,
  clippedRows: clipped.length,
  clippedWithheld: clippedWithheld.length,
  distinctVisibleAll: visibleStrings.size,
  distinctVisibleWithheld: withheldVisible.size,
  withheldSharingVisibleText: sharing,
  // 🔴 THE CONTROL FOR THE HEADLINE. "N rows collapse to M strings" is only a CLIPPING finding
  // if the FULL labels were distinct to begin with. #5191 strips the family name from a label
  // whose header already says it, so a family's rows are legitimately named "Over"/"Under" and
  // collapse with the chip removed too. Compare these two numbers before blaming truncation.
  distinctFullWithheld: new Set(withheld.map((r) => r.label)).size,
  clippedWithheldDetail: clippedWithheld.map((r) => ({ label: r.label, visible: r.visible, client: r.labelClient, scroll: r.labelScroll })),
  sampleWithheld: withheld.slice(0, 12).map((r) => ({ label: r.label, visible: r.visible, client: r.labelClient, scroll: r.labelScroll })),
}, null, 1));

if (out) {
  // 🪤 GROW THE VIEWPORT **BEFORE** MEASURING THE BOX, NOT AFTER. Growing it reflows the page
  // and mounts lazy content, so coordinates taken at 844px address different pixels in the
  // grown document — playwright then refuses with "Clipped area is either empty or outside
  // the resulting image", which reads as a broken selector rather than a stale coordinate.
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; });
  const docH = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(14000, docH) });
  await page.waitForTimeout(1200);

  // Point the shutter at the DEFECT, not at the section. A 4000px band of a 379-row list is
  // not a frame anyone reads; the clipped rows are what the issue is about, so clip to the
  // run that contains them and fall back to the section top only if nothing clipped.
  // 🔴 BAND_NEEDLE ANCHORS BOTH ARMS TO THE SAME ROWS, and an A/B of this fix is unreadable
  // without it. "Frame the clipped rows" is a selector that the AFTER arm, by construction,
  // cannot satisfy — it has no clipped rows — so it silently falls back to the section top and
  // you get two pictures of different parts of the page filed as a before and an after.
  const box = await page.evaluate(({ needle, padTop, padBottom }) => {
    const sec = document.querySelector('#props-script');
    const allRows = [...sec.querySelectorAll('div.flex.items-center.gap-3')];
    const clippedRows = needle
      ? allRows.filter((row) => (row.textContent || '').includes(needle))
      : allRows.filter((row) => {
          const l = row.querySelector('span.flex-1');
          return l && l.scrollWidth > l.clientWidth;
        });
    const r = sec.getBoundingClientRect();
    if (!clippedRows.length) {
      return { x: 0, y: r.top + window.scrollY, width: Math.round(r.width), height: Math.min(1200, Math.round(r.height)) };
    }
    const first = clippedRows[0].getBoundingClientRect();
    const last = clippedRows[clippedRows.length - 1].getBoundingClientRect();
    // Pad generously so the family headings above the rows are in frame — a row reading
    // "Over" is only judgeable under the heading that names what it is over.
    //
    // 🪤 Anchor on a row's FULL label, not a prefix. `textContent` is complete even when the
    // row is visually clipped, so "Jameson Willia" matches every Jameson row on the page —
    // including a graded family 14,000px above the clipped one — and the 3000px cap then
    // frames rows that never clipped. Both arms then photograph the same innocent band and
    // agree, which reads as "the fix changed nothing".
    const top = Math.max(r.top + window.scrollY, first.top + window.scrollY - padTop);
    const bottom = Math.min(r.bottom + window.scrollY, last.bottom + window.scrollY + padBottom);
    return { x: 0, y: top, width: Math.round(r.width), height: Math.min(3000, Math.round(bottom - top)) };
  }, {
    needle: process.env.BAND_NEEDLE || null,
    padTop: Number(process.env.BAND_PAD_TOP) || 120,
    padBottom: Number(process.env.BAND_PAD_BOTTOM) || 60,
  });
  // 🪤 AND DO NOT CLIP AN ABSOLUTE COORDINATE OUT OF A CAPPED VIEWPORT. A 379-row list is far
  // taller than the 14000px ceiling above, so a band at y≈20000 is simply not in the image and
  // playwright says "outside the resulting image" — again indistinguishable from a bad
  // selector. Size the viewport to the BAND and scroll the band into it; then an ordinary
  // viewport shot cannot be out of range.
  const shotH = Math.max(200, Math.min(3000, box.height));
  await page.setViewportSize({ width, height: shotH });
  await page.waitForTimeout(600);
  await page.evaluate((y) => window.scrollTo(0, y), box.y);
  await page.waitForTimeout(600);
  await page.screenshot({ path: out });
  console.error(`shot ${out} band=${JSON.stringify(box)} viewport=${width}x${shotH}`);
}
await browser.close();
