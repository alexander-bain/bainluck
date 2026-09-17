// futures-hero-overlap-6760.mjs — does the futures hero's 64px numeral cover the outcome name? (#6760)
//
// The ambient variant of `FuturesHero` (the one that renders when the hero outcome has >=3
// history points) paints two ABSOLUTELY POSITIONED children into one 96px box: the numeral at
// `left-0 bottom-1`, and a column holding the movement pill and the outcome name at `right-0
// bottom-2`. Neither is width-constrained, so an outcome name long enough to wrap runs the full
// width of the box and is drawn UNDER the numeral. On a live tennis market whose outcome name
// repeats the whole question ("Sao Paulo Open: Suzan Lamens vs Solana Sierra Set 1 Winner")
// the reader gets `Sao Pa100%pen: …` and can read neither.
//
// TWO INDEPENDENT SIGNALS, because a rect intersection alone is exactly the kind of geometry
// arithmetic that reads plausibly and is wrong (ux/1300 measured the same chip three ways and
// got 0/7, 7/7 and 1/7):
//
//   * `overlapPx`   — area of the intersection of the numeral's rect and the name's rect.
//   * `stolenPts`   — of N points sampled INSIDE THE NUMERAL'S OWN BOX, how many does
//                     `document.elementFromPoint` answer with the name element? That is
//                     Chromium's own hit test through the real stacking order, and it knows
//                     nothing about my arithmetic.
//
// 🪤 The direction matters and the first version of this probe had it backwards. It sampled the
// NAME's box and asked "does the hit answer the numeral?" — and got 0/24 on four pages whose
// rects overlapped by 5,075px². Both children are `position:absolute` with `z-index:auto`, and
// the name column is the LATER sibling, so the name paints ON TOP and wins every hit test on
// its own pixels. A clean, plausible, quotable zero that meant only "the name is painted last".
// Sampling the numeral's box is the direction that can see the contest at all.
//
// They must AGREE. A row where one fires and the other does not is a bug in this probe, and it
// says so rather than reporting a number.
//
// PASS for a page = overlapPx === 0 AND stolenPts === 0.
// Pages with no ambient hero (no sparkline, resolved, no probability) report `variant` and are
// not counted either way — the plain-flow variant cannot overlap and is not the subject.
//
// Usage: node tools/futures-hero-overlap-6760.mjs <baseUrl> <id[,id,...]> [widthPx]
//   node tools/futures-hero-overlap-6760.mjs https://bainluck.com 61246736,61270162 390
// Exit 0 = every measured page PASSes · 3 = at least one overlap · 4 = no page had the hero ·
//        5 = the two signals disagreed somewhere.
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
import { execFile } from 'child_process';

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

const baseUrl = process.argv[2];
const ids = (process.argv[3] || '').split(',').map((s) => s.trim()).filter(Boolean);
const width = Number(process.argv[4] || 390);
if (!baseUrl || !ids.length) {
  console.error('usage: futures-hero-overlap-6760.mjs <baseUrl> <id[,id,...]> [widthPx]');
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const localTarget = /localhost|127\.0\.0\.1/.test(baseUrl);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!localTarget) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });

// AGAINST A LOCAL BUILD, the page's own fetches of api.bainluck.com fail: the API sends no CORS
// header for a localhost origin, and `route.fetch()` runs on the Playwright driver outside the
// sandbox's proxy and EPERMs. Shelling out to `curl` is the one route that reaches the API, so
// every API request is served that way and fulfilled with an open CORS header. The BODY is the
// venue's own answer, untouched — this makes a local page reachable, it does not manufacture
// anything. (ux/1312 paid for all three of those facts; `hero-collide-fit-5807.mjs` is the
// precedent.) Against production this is skipped entirely and the page fetches normally.
if (localTarget) {
  const curlBody = (u) =>
    new Promise((resolve) => {
      execFile('curl', ['-sS', '--max-time', '30', u], { maxBuffer: 64 * 1024 * 1024 }, (err, stdout) =>
        resolve(err ? null : stdout)
      );
    });
  await page.route(
    (u) => u.hostname === 'api.bainluck.com',
    async (route) => {
      const body = await curlBody(route.request().url());
      const headers = { 'content-type': 'application/json', 'access-control-allow-origin': '*' };
      return route.fulfill(body === null ? { status: 502, body: '{}', headers } : { status: 200, body, headers });
    }
  );
}

const measure = () =>
  page.evaluate(() => {
    // The hero's ambient box is the only `position:relative` block that is exactly 96px tall and
    // holds an absolutely positioned 64px numeral. Match on the numeral, then walk up — the
    // Tailwind class string is an implementation detail and `h-[96px]` is not a stable selector.
    const numeralSpan = Array.from(document.querySelectorAll('span')).find(
      (s) => parseFloat(getComputedStyle(s).fontSize) >= 60 && /^\d+$/.test(s.textContent.trim())
    );
    if (!numeralSpan) return { variant: 'no-hero-numeral' };
    const numeral = numeralSpan.closest('div');

    // 🪤 VARIANT DETECTION MUST NOT BE KEYED ON THE DEFECT'S OWN MARKUP. The first version asked
    // `getComputedStyle(numeral).position === 'absolute'` — true only while the numeral was one
    // of the two independently positioned children, which is the bug. Run against a build where
    // the numeral sits in a flex row inside an absolute strip, it answered "plain-flow" for
    // every page and reported that nothing was measurable: the FIX read as an ABSENCE OF THE
    // SUBJECT. The ambient variant is identified by the thing that actually defines it — the
    // ambient history `<svg>` inside a `position:relative` box around the numeral.
    let box = null;
    for (let el = numeral.parentElement, i = 0; el && i < 4; el = el.parentElement, i++) {
      if (getComputedStyle(el).position === 'relative' && el.querySelector(':scope > svg')) {
        box = el;
        break;
      }
    }
    if (!box) return { variant: 'plain-flow' };

    // The name: prefer the addressable element, which is what the component ships after #6760.
    // Fall back to the structural search for a build that predates the testid — a production
    // BEFORE has no testid, and BEFORE and AFTER must answer the same question or the comparison
    // is between two different measurements.
    let nameEl = document.querySelector('[data-testid="hero-outcome-name"]');
    let how = 'testid';
    if (!nameEl) {
      const sibling = Array.from(box.children).find(
        (c) => c !== numeral && c.tagName !== 'svg' && getComputedStyle(c).position === 'absolute'
      );
      if (!sibling) return { variant: 'ambient-no-name-column' };
      nameEl = Array.from(sibling.querySelectorAll('span')).reverse().find(
        (s) => s.children.length === 0 && s.textContent.trim().length > 0
      );
      how = 'structural';
    }
    if (!nameEl) return { variant: 'ambient-empty-name-column' };

    const n = numeral.getBoundingClientRect();
    const t = nameEl.getBoundingClientRect();

    // SIGNAL 1 — rect intersection area.
    const ox = Math.max(0, Math.min(n.right, t.right) - Math.max(n.left, t.left));
    const oy = Math.max(0, Math.min(n.bottom, t.bottom) - Math.max(n.top, t.top));
    const overlapPx = Math.round(ox * oy);

    // SIGNAL 2 — Chromium's own hit test, sampled on a grid INSIDE THE NUMERAL'S box. A point
    // that answers with the name element is a pixel the reader sees the name drawn on while the
    // numeral believes it owns it. See the direction trap in the header.
    const COLS = 8;
    const ROWS = 3;
    const SAMPLES = COLS * ROWS;
    let stolenPts = 0;
    const probed = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = n.left + ((c + 0.5) / COLS) * n.width;
        const y = n.top + ((r + 0.5) / ROWS) * n.height;
        const hit = document.elementFromPoint(Math.round(x), Math.round(y));
        const onName = !!hit && (hit === nameEl || nameEl.contains(hit));
        if (onName) stolenPts++;
        probed.push(onName ? 1 : 0);
      }
    }

    return {
      variant: 'ambient',
      nameFoundBy: how,
      numeral: numeralSpan.textContent.trim(),
      name: nameEl.textContent.trim(),
      nameLen: nameEl.textContent.trim().length,
      nameWrapLines: Math.max(1, Math.round(t.height / parseFloat(getComputedStyle(nameEl).lineHeight || '18'))),
      numeralRect: [n.left, n.top, n.width, n.height].map((v) => Math.round(v)),
      nameRect: [t.left, t.top, t.width, t.height].map((v) => Math.round(v)),
      overlapPx,
      stolenPts,
      samples: SAMPLES,
      hitMap: probed.join(''),
    };
  });

let measured = 0;
let failed = 0;
let disagreed = 0;
const rows = [];

for (const id of ids) {
  const url = `${baseUrl.replace(/\/$/, '')}/futures/${id}`;
  let r;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(Number(process.env.SETTLE_MS || 1200));
    r = await measure();
  } catch (e) {
    r = { variant: 'load-failed', error: String(e).slice(0, 120) };
  }
  r.id = id;
  rows.push(r);
  if (r.variant !== 'ambient') {
    console.log(`${id}  —  ${r.variant}${r.error ? ' ' + r.error : ''}`);
    continue;
  }
  measured++;
  // The two signals must agree on WHETHER there is an overlap. Magnitudes need not match.
  const a = r.overlapPx > 0;
  const b = r.stolenPts > 0;
  if (a !== b) {
    disagreed++;
    console.log(
      `${id}  🔴 SIGNALS DISAGREE  overlapPx=${r.overlapPx} stolenPts=${r.stolenPts}/${r.samples}` +
        `  numeral=${JSON.stringify(r.numeralRect)} name=${JSON.stringify(r.nameRect)}`
    );
    continue;
  }
  if (a) failed++;
  console.log(
    `${id}  ${a ? '🔴 OVERLAP' : '✅ clear  '}  overlapPx=${String(r.overlapPx).padStart(6)}` +
      `  stolen=${r.stolenPts}/${r.samples}  lines=${r.nameWrapLines}  ${r.numeral}%  "${r.name.slice(0, 70)}"`
  );
}

console.log(
  `\n${measured} ambient heroes measured at ${width}px · ${failed} overlapping · ` +
    `${disagreed} signal disagreements · ${ids.length - measured} pages with no ambient hero`
);
if (process.env.OVERLAP_JSON) {
  const { writeFileSync } = await import('fs');
  writeFileSync(process.env.OVERLAP_JSON, JSON.stringify({ baseUrl, width, rows }, null, 2));
  console.log(`json → ${process.env.OVERLAP_JSON}`);
}

await browser.close();
if (disagreed) process.exit(5);
if (!measured) process.exit(4);
process.exit(failed ? 3 : 0);
