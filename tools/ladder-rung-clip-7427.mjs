// ladder-rung-clip-7427.mjs <url> [width] — measure which Discover ladder rung labels are
// CLIPPED by their fixed slot, and by how much.
//
// WHY MEASURE RATHER THAN ESTIMATE (#7427). `QuantityGroup`'s wide-label variant gives the
// rung label a FIXED `w-[45%] shrink-0 truncate` slot. The fixed width is deliberate — with a
// content-width label the `flex-1` track is a different length on every row, so two rungs
// printing the same % draw visibly different bars (#1574 acceptance c). The cost is that a
// label longer than 45% of the row loses its TAIL, and on a date ladder the tail is the YEAR:
// "Before January 20, 2029" renders "Before January 20, …" directly above "Before 2027", and
// the one token that tells the two rungs apart is the one that got clipped.
//
// Whether a given label clips is a question about the rendered font's advance widths and the
// card's real width at 390px. A hand estimate gets that wrong in the direction that ships the
// clip, and a downscaled whole-page PNG fabricates the few pixels the answer turns on. So this
// reads `scrollWidth` vs `clientWidth` off the real element on the real page.
//
// It reports, per clipped rung: the full label (from the row's `aria-label`, which carries the
// untruncated text), the slot width, the text's natural width, and the shortfall in px and in
// ch. The shortfall is what a repair has to buy.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 measured, no rung clipped · 3 at least one rung is
// clipped (the defect is live) · 4 no ladder rung on this draw (the feed shuffled — re-run,
// not a failure) · 2 usage · 1 anything else.
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
if (!url) { console.error('usage: ladder-rung-clip-7427.mjs <url> [width]'); process.exit(2); }

// Same launch args as `tools/shop-shot.mjs`, and for the same two reasons: Chromium's default
// multi-process launch dies in the agent sandbox (`bootstrap_check_in … Permission denied
// (1100)`), and the browser does not inherit the session egress proxy. A probe that cannot
// launch reports nothing, which reads exactly like a probe that found nothing.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url)) {
    args.push('--proxy-bypass-list=<-loopback>');
  }
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

// The feed lazy-loads on intersection. Grow the viewport to the document height the way
// look.sh does, so every card below the fold mounts before anything is measured — a rung
// that never rendered cannot be reported as fitting.
for (let i = 0; i < 3; i++) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30000) });
  await page.waitForTimeout(1200);
}

const rows = await page.evaluate(() => {
  // A rung row is the element whose `aria-label` is "<label>: <pct>" and whose first child
  // span is the truncating label slot. Keying on the aria-label is what makes the FULL text
  // readable: the DOM text is untruncated (the clip is CSS), but the aria-label is the
  // contract the component states, so label and measurement cannot drift apart.
  const out = [];
  for (const el of document.querySelectorAll('[aria-label]')) {
    const aria = el.getAttribute('aria-label') || '';
    const m = aria.match(/^(.*): (\d+%|—|-)$/);
    if (!m) continue;
    const slot = el.querySelector(':scope > span');
    if (!slot) continue;
    const cs = getComputedStyle(slot);
    // DO NOT KEY THE LOCATOR ON THE DEFECT. The first cut of this probe selected slots whose
    // computed `text-overflow` was `ellipsis`, which is precisely the property #7427's repair
    // removes — so against a fixed build it selected nothing and exited 4, "the feed shuffled,
    // re-run". An instrument that cannot see the repaired state reports the repair as an empty
    // draw, and exit 4 reads as noise rather than as a pass. The slot is therefore identified
    // structurally: the first child span of a rung row, clipping in EITHER direction.
    if (cs.overflow === 'visible' && cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
    const text = (slot.textContent || '').trim();
    if (!text) continue;
    out.push({
      label: m[1],
      pct: m[2],
      text,
      clientWidth: slot.clientWidth,
      scrollWidth: slot.scrollWidth,
      clientHeight: slot.clientHeight,
      scrollHeight: slot.scrollHeight,
      rowWidth: el.clientWidth,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      // `truncate` ellipsises horizontally; `line-clamp-2` clips VERTICALLY at the second
      // line. Both hide text, so both have to be measured or the fix could simply move the
      // loss from one axis to the other and still read as clean.
      mode: cs.textOverflow === 'ellipsis' ? 'ellipsis' : (cs.webkitLineClamp && cs.webkitLineClamp !== 'none' ? `clamp-${cs.webkitLineClamp}` : 'hidden'),
    });
  }
  return out;
});

await browser.close();

if (rows.length === 0) {
  console.log(`NO LADDER RUNG ON THIS DRAW (${url} @ ${width}px)`);
  process.exit(4);
}

// A 1px slack absorbs sub-pixel rounding: Chromium rounds clientWidth down and scrollWidth up,
// so an exactly-fitting label can read as 1px over. Anything above that is a real clip.
const over = (r) => ({ x: r.scrollWidth - r.clientWidth, y: r.scrollHeight - r.clientHeight });
const clipped = rows.filter((r) => { const o = over(r); return o.x > 1 || o.y > 1; });

console.log(`url=${url} width=${width}px rungs=${rows.length} clipped=${clipped.length}`);
if (rows.length) {
  const w = rows[0];
  const modes = [...new Set(rows.map((r) => r.mode))].join(',');
  console.log(`slot: clientWidth=${w.clientWidth}px of row ${w.rowWidth}px  font=${w.fontSize}/${w.fontWeight}  mode=${modes}`);
}
for (const r of clipped) {
  const o = over(r);
  const axis = o.x > 1 ? `WIDTH  slot=${r.clientWidth}px text=${r.scrollWidth}px short=${o.x}px`
                       : `HEIGHT slot=${r.clientHeight}px text=${r.scrollHeight}px short=${o.y}px`;
  console.log(`  CLIPPED [${r.mode}] "${r.label}" (${r.pct})  ${axis}  row=${r.rowWidth}px`);
}
// The labels that USED to clip are the ones a repair has to be judged on, and after a wrap fix
// they no longer overflow on either axis — so an "all clear" line alone would be the same
// output as a draw with no long labels in it. Naming them keeps the pass falsifiable.
const longest = [...rows].sort((a, b) => b.text.length - a.text.length).slice(0, 6);
console.log('longest labels on this draw (the ones a clip would take):');
for (const r of longest) {
  const o = over(r);
  console.log(`  ${o.x <= 1 && o.y <= 1 ? 'whole ' : 'CLIP  '} "${r.text}" (${r.text.length} chars) [${r.mode}] box=${r.clientWidth}x${r.clientHeight} ink=${r.scrollWidth}x${r.scrollHeight}`);
}

// --apply-fix — measure the SAME elements again with #7427's treatment applied in-page.
//
// Why here rather than against a local build: a local `npm run start` cannot reach
// api.bainluck.com through the sandbox proxy, so its Discover page renders "We couldn't load
// the feed" and has no rungs at all. The probe correctly exits 4 on it, which proves nothing
// about the repair. Production is the only place the real labels, the real font stack and the
// real 300px row exist together, so the honest A/B is to re-measure production's own elements
// with the new declarations applied — same ink, same box, one property group changed.
//
// The treatment is written as inline STYLE, not as the Tailwind class names, deliberately:
// whether `line-clamp-2` and `break-words` happen to be in the deployed CSS bundle is a
// question about JIT output, and if either were absent the class swap would silently measure
// no change and report the fix as a failure. The declarations below are what those utilities
// compile to, so the measurement cannot be wrong about what it applied.
if (process.argv.includes('--apply-fix')) {
  const fixOff = process.argv.includes('--fix-off');
  const after = await (async () => {
    const b2 = await chromium.launch({ args });
    const p2 = await b2.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
    await p2.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
    for (let i = 0; i < 3; i++) {
      const h = await p2.evaluate(() => document.documentElement.scrollHeight);
      await p2.setViewportSize({ width, height: Math.min(h, 30000) });
      await p2.waitForTimeout(1200);
    }
    const res = await p2.evaluate((fixOff) => {
      const out = [];
      for (const el of document.querySelectorAll('[aria-label]')) {
        const aria = el.getAttribute('aria-label') || '';
        const m = aria.match(/^(.*): (\d+%|—|-)$/);
        if (!m) continue;
        const slot = el.querySelector(':scope > span');
        if (!slot) continue;
        const cs = getComputedStyle(slot);
        if (cs.textOverflow !== 'ellipsis') continue;
        const widthBefore = slot.clientWidth;
        // `--fix-off` runs this identical path and applies NOTHING, so the BEFORE photograph
        // is taken by the same code, at the same scroll position, on the same card as the
        // AFTER one. A before/after pair shot by two different code paths is a comparison of
        // the paths as much as of the change.
        if (fixOff) { out.push({ label: m[1], slot, widthBefore }); continue; }
        // What `break-words line-clamp-2` compiles to, replacing `truncate`.
        slot.style.whiteSpace = 'normal';
        slot.style.textOverflow = 'clip';
        slot.style.overflowWrap = 'break-word';
        slot.style.display = '-webkit-box';
        slot.style.webkitBoxOrient = 'vertical';
        slot.style.webkitLineClamp = '2';
        out.push({ label: m[1], slot, widthBefore });
      }
      // One forced reflow after every mutation, then read — reading per element as it is
      // mutated would measure a layout that is still settling.
      void document.body.offsetHeight;
      return out.map((r) => ({
        label: r.label,
        widthBefore: r.widthBefore,
        clientWidth: r.slot.clientWidth,
        scrollWidth: r.slot.scrollWidth,
        clientHeight: r.slot.clientHeight,
        scrollHeight: r.slot.scrollHeight,
      }));
    }, fixOff);

    // --shot <path> — photograph a treated card, because a clip count is not a LOOK. The
    // measurement above can say no text is hidden and still be blind to the thing a reader
    // would object to: a two-line rung next to a one-line rung makes the ladder's rows
    // uneven, and whether that reads as broken is a judgement nobody can make from px.
    const shotAt = process.argv.indexOf('--shot');
    if (shotAt > -1 && process.argv[shotAt + 1]) {
      const target = process.argv[shotAt + 2] || 'Above 20 million short tons';
      const box = await p2.evaluate((t) => {
        for (const el of document.querySelectorAll('[aria-label]')) {
          if (!(el.getAttribute('aria-label') || '').startsWith(t + ':')) continue;
          const card = el.closest('article') || el.parentElement?.parentElement;
          if (!card) continue;
          const r = card.getBoundingClientRect();
          return { x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.width, height: r.height };
        }
        return null;
      }, target);
      if (box) {
        await p2.setViewportSize({ width, height: 844 });
        await p2.evaluate((y) => window.scrollTo(0, Math.max(0, y - 40)), box.y);
        await p2.waitForTimeout(600);
        await p2.screenshot({ path: process.argv[shotAt + 1] });
        console.log(`shot: ${process.argv[shotAt + 1]} (card carrying "${target}")`);
      } else {
        console.log(`shot: SKIPPED — no card carrying "${target}" on this draw`);
      }
    }
    await b2.close();
    return res;
  })();

  const stillClipped = after.filter((r) => r.scrollWidth - r.clientWidth > 1 || r.scrollHeight - r.clientHeight > 1);
  const moved = after.filter((r) => r.clientWidth !== r.widthBefore);
  console.log(`\n--- WITH #7427 APPLIED (same page, same elements) ---`);
  console.log(`treated=${after.length} stillClipped=${stillClipped.length} slotWidthMoved=${moved.length}`);
  for (const r of after) {
    const ok = r.scrollWidth - r.clientWidth <= 1 && r.scrollHeight - r.clientHeight <= 1;
    console.log(`  ${ok ? 'whole ' : 'CLIP  '} "${r.label}"  box=${r.clientWidth}x${r.clientHeight} ink=${r.scrollWidth}x${r.scrollHeight}  slot ${r.widthBefore}px->${r.clientWidth}px`);
  }
  // `slotWidthMoved` is the control that matters as much as the clip count: if the label slot
  // changed width, the `flex-1` track beside it changed length, and #1574 acceptance (c) —
  // equal percentages draw equal bars — has been paid out to buy the tail. It must be 0.
  if (moved.length > 0) { console.log('SLOT WIDTH MOVED — #1574(c) would be paid out. STOP.'); process.exit(3); }
  process.exit(stillClipped.length > 0 ? 3 : 0);
}

process.exit(clipped.length > 0 ? 3 : 0);
