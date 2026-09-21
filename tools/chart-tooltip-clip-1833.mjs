// chart-tooltip-clip-1833.mjs — does the event page's win-probability chart tooltip get
// CLIPPED at phone width? (ux, #1833 web twin / codex 0923PT note)
//
// The question a class name cannot answer. `max-w-sm` on the tooltip root is 384px, but what a
// reader loses depends on the rendered width the tooltip actually takes (its content may be
// narrower), where recharts positions the wrapper (it flips sides near an edge), and how wide the
// plot is inside the page's padding. All three are layout-engine facts, so ask the layout engine.
//
// Read from getBoundingClientRect, never from pixels:
//   * `.recharts-tooltip-wrapper`   -> where the tooltip really sits, in viewport coords
//   * its first element child       -> the painted card (the wrapper can be wider than the card)
//   * `document.documentElement`    -> the viewport box the reader can actually see
//
// A card whose left edge is < 0 or whose right edge is > viewport width is text the reader cannot
// read: the page does not scroll horizontally, so those pixels are simply gone.
//
// Samples several x positions across the plot, because the defect is position-dependent: a
// tooltip near the middle fits and the same tooltip near an edge does not. Reports the WORST.
//
// 🔴 THE VERDICT IS HORIZONTAL ONLY, ON PURPOSE. The same card also runs off the BOTTOM of the
// viewport on the inline chart (measured 27–79px on 4 of 5 positions), and that is a SEPARATE,
// PRE-EXISTING defect: it is present unchanged in the before-tree, because a 444px-tall card
// pinned at the plot's top simply does not fit an 844px phone. Folding it into this exit code
// would make the horizontal fix unprovable — the probe would return 1 either way. So the
// vertical numbers are MEASURED AND REPORTED on every run (`clippedVerticallyPositions`,
// `worstOverflowBottom`) and deliberately excluded from the verdict. Do not "tidy" them into
// the exit code without a fix for them; that silently retires this after-check.
//
// 🟢 THE FIX FOR THE VERTICAL HALF IS #7848, and it did NOT tidy them in: the numbers are
// still out of the default verdict, so the paragraph above still holds and #1833's
// after-check still measures the axis it was written for. `VERTICAL=1` selects the OTHER
// axis for the exit code — one run, one axis, named in `out.axis` so a banked JSON says
// which question it answered. Measured against production on 2026-09-21 before the fix:
// default exit 0 (horizontal clean since #1833), `VERTICAL=1` exit 1 (4 of 5 positions,
// worst 79px). A probe that has only ever been seen green cannot pay an after-check.
//
// Usage: node chart-tooltip-clip-1833.mjs <url> [widthPx]
//        CORS_SHIM=1 to point at a local dev server (see below).
//        VERTICAL=1  verdict on bottom overflow (#7848) instead of side shear (#1833).
//        FRACS=0.9,0.93,0.96  override the x sweep to reach the terminal (settled) point,
//                    which the default sweep cannot — see the note beside the loop.
// Exit:  0 no clipping on the selected axis at any sampled position · 1 CLIPPED (defect
//        served) · 2 bad usage · 3 no win-probability chart on the page · 4 could not read
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
if (!url) {
  console.error('usage: chart-tooltip-clip-1833.mjs <url> [widthPx]');
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
// `<-loopback>` REMOVES chromium's implicit loopback bypass, i.e. it sends 127.0.0.1 through the
// sandbox proxy, which answers 503. That is correct for a production URL and fatal for a local
// dev server — and it fails as exit 3 "no chart on this page", which reads like a verdict about
// the page. So keep the proxy for remote targets and bypass it for a local one.
// A local run still needs the proxy for the API host (direct egress is EPERM in the sandbox),
// so keep the proxy and simply leave chromium's DEFAULT loopback bypass in place.
const isLocal = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/.test(url);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!isLocal) args.push('--proxy-bypass-list=<-loopback>');
}

// CORS_SHIM=1 — point this probe at a LOCAL dev server. api.bainluck.com allows the production
// origin, so a page served from localhost gets "Failed to fetch", renders the error card and no
// chart at all: exit 3, which reads as "this page has no chart" rather than "I could not talk to
// the API". So drop the origin check for a local run. It changes nothing about the page's own
// layout, which is the only thing being measured. Off by default, so a production run is never
// touched by it.
//
// 🪤 It turns the CHECK off in chromium rather than re-serving the responses. The obvious form —
// `route.fetch()` then `route.fulfill()` with a permissive header — cannot work in this sandbox:
// `route.fetch` is playwright's OWN network stack and does not honour `--proxy-server`, so every
// API call dies `connect EPERM` and the page renders with no chart. That arrives as exit 3, "no
// recharts surface", which reads as a verdict about the PAGE rather than about the harness, so it
// is worth naming. The browser's own fetches do go through the proxy; leave them alone.
if (process.env.CORS_SHIM === '1') {
  args.push('--disable-web-security');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

// Measure one chart surface: hover across the plot and report the worst overflow seen.
// `root` scopes the query: once the fullscreen modal is open the INLINE chart is still in the
// DOM behind it, so an unscoped selector hovers coordinates the modal overlay swallows and the
// surface reads "no tooltip" — a blind spot that looks exactly like a clean result.
async function measure(label, root = '', idx = 0) {
  // Address the chart BY INDEX among the wrappers under `root`: an event page carries several
  // charts (win probability, score differential), they share one tooltip class, and a selector
  // that takes the first match measures one chart and silently clears the others.
  const wrappers = await page.$$(`${root} .recharts-wrapper`.trim());
  const wrapper = wrappers[idx];
  if (!wrapper) return { label, error: `no chart wrapper at index ${idx}` };
  const box = await wrapper.boundingBox();
  if (!box) return { label, error: 'chart wrapper has no box' };
  await wrapper.scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  const box2 = await wrapper.boundingBox();
  if (box2) { box.x = box2.x; box.y = box2.y; box.width = box2.width; box.height = box2.height; }

  const samples = [];
  // Sample across the plot including both edges, where the defect lives.
  //
  // 🔴 THE DEFAULT SWEEP CANNOT REACH THE LAST POINT. These fracs are of the `.recharts-wrapper`
  // box, which includes the chart's own margins, so 0.98 lands in the right MARGIN and reads
  // `tooltip: null` — indistinguishable from "no tooltip here". On a completed game the terminal
  // point is exactly where the settled row lives: `/events/14780544` serves ESPN
  // `period: "Final"` beside `game_clock: "Final"`, and #7860's second symptom (`Final Final`)
  // was therefore in the one place this probe never looked. FRACS overrides the sweep
  // (`FRACS=0.9,0.93,0.96` — comma-separated, 0..1) so a settled row can be named and read.
  // Report which sweep ran, so a banked JSON cannot be mistaken for a default run.
  // 🪤 A mistyped FRACS must not read as a clean page. Filtering garbage away silently would
  // leave an EMPTY sweep, and a surface with zero samples reports `withTooltip: 0` and no
  // clipping — indistinguishable from a page whose tooltip never overflows. Refuse instead.
  const FRACS = process.env.FRACS
    ? process.env.FRACS.split(',').map(Number).filter((n) => Number.isFinite(n) && n >= 0 && n <= 1)
    : [0.02, 0.15, 0.35, 0.5, 0.65, 0.85, 0.98];
  if (!FRACS.length) {
    console.error(`FRACS=${process.env.FRACS} has no usable value (want comma-separated 0..1)`);
    process.exit(2);
  }
  for (const frac of FRACS) {
    const x = box.x + box.width * frac;
    const y = box.y + box.height * 0.5;
    await page.mouse.move(x, y);
    await page.waitForTimeout(140);
    const m = await page.evaluate(({ sel, i }) => {
      const w = document.querySelectorAll(`${sel} .recharts-tooltip-wrapper`.trim())[i];
      if (!w) return null;
      const card = w.firstElementChild;
      const r = (card || w).getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return null;
      return {
        left: Math.round(r.left), right: Math.round(r.right),
        top: Math.round(r.top), bottom: Math.round(r.bottom),
        width: Math.round(r.width), height: Math.round(r.height),
        vw: document.documentElement.clientWidth,
        vh: document.documentElement.clientHeight,
        // 🔴 THE VIEWPORT IS NOT THE READABLE AREA. The mobile nav is `fixed
        // bottom-0 z-50`, 57px tall, painted OVER the page — so a card whose
        // bottom sits at 836 on an 844px screen still has its last rows hidden,
        // and measuring against `vh` alone scores that as clean. It did: the
        // first cut of #7848's fix passed this probe at 0 of 5 while the
        // screenshot showed the ESPN row behind the bar. Read the same marker
        // the fix reads, so probe and fix cannot disagree about where the
        // bottom is. Absent or `display:none` (desktop) => the viewport bottom.
        readableBottom: (() => {
          const o = document.querySelector('[data-viewport-bottom-obstruction]');
          const or = o && o.getBoundingClientRect();
          return or && or.height > 0
            ? Math.min(document.documentElement.clientHeight, Math.round(or.top))
            : document.documentElement.clientHeight;
        })(),
        maxWidth: getComputedStyle(card || w).maxWidth,
        // The tooltip text, so a clipped card can be named by what the reader loses.
        text: (card || w).innerText.replace(/\s+/g, ' ').slice(0, 90),
      };
    }, { sel: root, i: idx });
    if (!m) { samples.push({ frac, tooltip: null }); continue; }
    const overflowLeft = Math.max(0, 0 - m.left);
    const overflowRight = Math.max(0, m.right - m.vw);
    const overflowBottom = Math.max(0, m.bottom - m.readableBottom);
    const overflowTop = Math.max(0, 0 - m.top);
    samples.push({
      frac, ...m, overflowLeft, overflowRight, overflowTop, overflowBottom,
      clipped: overflowLeft > 0 || overflowRight > 0,
      clippedVertically: overflowTop > 0 || overflowBottom > 0,
    });
  }
  const seen = samples.filter((s) => s.tooltip !== null && s.width);
  const worst = seen.reduce(
    (a, s) => (Math.max(s.overflowLeft, s.overflowRight) > Math.max(a.overflowLeft, a.overflowRight) ? s : a),
    { overflowLeft: 0, overflowRight: 0 }
  );
  return {
    label,
    plotWidth: Math.round(box.width),
    // Which sweep ran. A banked JSON from a FRACS run answers a different question from a
    // default run, and nothing else in the file says so.
    fracs: FRACS.join(','),
    fracsOverridden: Boolean(process.env.FRACS),
    sampled: samples.length,
    withTooltip: seen.length,
    maxCardWidth: seen.length ? Math.max(...seen.map((s) => s.width)) : null,
    worstOverflowLeft: worst.overflowLeft,
    worstOverflowRight: worst.overflowRight,
    clippedPositions: seen.filter((s) => s.clipped).length,
    // Reported, NOT part of the verdict — see the exit-code note at the top of the file.
    clippedVerticallyPositions: seen.filter((s) => s.clippedVertically).length,
    worstOverflowBottom: Math.max(0, ...seen.map((s) => s.overflowBottom)),
    samples,
  };
}

const out = { url, width, surfaces: [] };
let exit = 0;
try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
  // The chart mounts below the fold and recharts sizes off a ResizeObserver, so scroll it in.
  // The chart is client-rendered after its history fetch, so `networkidle` can land before the
  // first recharts node exists (always on a cold dev server, sometimes on production). Waiting
  // for the node — rather than querying once — is the difference between "this page has no
  // chart" and "I looked too early", which exit 3 would otherwise conflate.
  let chart = null;
  try {
    await page.waitForSelector('.recharts-surface', { timeout: 45000 });
    chart = await page.$('.recharts-surface');
  } catch { /* falls through to exit 3 below */ }
  if (!chart) { console.log(JSON.stringify({ ...out, error: 'no recharts surface' }, null, 2)); await browser.close(); process.exit(3); }
  await chart.scrollIntoViewIfNeeded();
  await page.waitForTimeout(900);

  const inlineCount = (await page.$$('.recharts-wrapper')).length;
  out.inlineChartCount = inlineCount;
  for (let i = 0; i < inlineCount; i++) {
    out.surfaces.push(await measure(`inline[${i}]`, '', i));
  }

  // The fullscreen modal is the surface codex photographed. It is the same chart component with
  // `fillContainer`, inside a p-4 box, so its plot is narrower still.
  const expand = await page.$('button[title="Fullscreen"]');
  if (expand) {
    await expand.click();
    // A tap that does not land is an error, not a clean surface (look.sh #3932). Require the
    // modal before believing anything measured after the click.
    const MODAL = 'div.fixed.inset-0.z-50';
    try {
      await page.waitForSelector(`${MODAL} .recharts-surface`, { timeout: 15000 });
      await page.waitForTimeout(900);
      out.surfaces.push(await measure('fullscreen', MODAL));
    } catch {
      out.surfaces.push({ label: 'fullscreen', error: 'expand tapped but modal chart never appeared' });
    }
  } else {
    out.surfaces.push({ label: 'fullscreen', error: 'no expand control' });
  }

  const readable = out.surfaces.filter((s) => s.withTooltip > 0);
  // VERTICAL=1 moves the bottom-overflow numbers INTO the verdict. Off by default,
  // so #1833's after-check keeps measuring exactly what it always measured: the two
  // defects share a card but not an axis, and one exit code cannot pay both. See the
  // note at the top of the file.
  out.axis = process.env.VERTICAL === '1' ? 'vertical (#7848)' : 'horizontal (#1833)';
  const offending = (s) =>
    process.env.VERTICAL === '1' ? s.clippedVerticallyPositions > 0 : s.clippedPositions > 0;
  if (readable.length === 0) exit = 4;
  else if (readable.some(offending)) exit = 1;
  out.verdict = exit === 1 ? 'CLIPPED' : exit === 4 ? 'COULD-NOT-READ' : 'clean';
  console.log(JSON.stringify(out, null, 2));
} catch (e) {
  console.log(JSON.stringify({ ...out, error: String(e) }, null, 2));
  exit = 4;
} finally {
  await browser.close();
}
process.exit(exit);
