// chart-in-raster-4664.mjs <url> [width] — does the PHOTOGRAPH contain the chart line the DOM has?
//
// #4664: `page.screenshot({ fullPage: true })` photographed `/events/15309061` with an empty
// plot — axes, gridlines, y-domain, endpoint dot, no line — while a complete 64-vertex
// `path.recharts-line-curve` sat in the DOM at that exact moment. Under standing notice 4 that
// PNG is the PROOF a rendered-surface change is done, so the rail could fail a working chart,
// and (the worse direction) nothing about the artifact said which had happened.
//
// This asks the only question that settles it: the DOM says N line paths of colour C; does the
// raster hold pixels of colour C inside the chart's box? Both halves are measured on the SAME
// page at the SAME moment, so neither can be explained away by load timing.
//
//   exit 0  AGREE      — DOM has lines and the raster holds them, or DOM has none and nor does
//                        the raster. Either way the picture is telling the truth.
//   exit 3  FALSE-EMPTY — the DOM has a line the raster does not. This is #4664.
//   exit 4  BLIND      — no chart on this page, so there was nothing to check.
//   exit 1  camera/usage
//
// The failing direction is a first-class result, not an afterthought: run it against a page whose
// chart genuinely has no data (a scheduled fixture with no `win_probability_sources`) and it must
// report DOM 0 / raster 0 and exit 0. A rig that cannot photograph an empty chart AS empty would
// have replaced a false negative with a false positive.
//
// The raster is decoded in the browser we already launched — the PNG goes back in through a
// canvas — so this needs no image library and no second process.
import { createRequire } from 'module';
import { existsSync, readdirSync, readFileSync, unlinkSync } from 'fs';
import { chooseCapture } from './shot-click-contract.mjs';

// A tool in tools/ must resolve playwright the way the rest of the rail does: a bare
// `import { chromium } from 'playwright'` is MODULE_NOT_FOUND from a lane worktree.
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
if (!url) {
  console.error('usage: chart-in-raster-4664.mjs <url> [width]');
  console.error('  exit 0 agree · 3 the raster lost a line the DOM has (#4664) · 4 no chart · 1 camera');
  process.exit(1);
}
const W = parseInt(process.argv[3] || process.env.SHOT_W || '390', 10);
const H = parseInt(process.env.SHOT_H || '844', 10);
const OUT = process.env.CHART_RASTER_PNG || `/tmp/chart-in-raster-${Date.now()}.png`;
const KEEP = Boolean(process.env.CHART_RASTER_PNG);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let code = 1;
try {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(7000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(2000);
  } catch { /* no banner on this page */ }

  // Set the capture-time layout FIRST, then read the DOM, then shoot.
  //
  // Order is load-bearing: growing the viewport reflows the page, so a chart box measured at
  // 390x844 can name a rectangle the grown raster puts the chart nowhere near — and cropping
  // the wrong rectangle reports 0 stroke pixels, which is indistinguishable from the very bug
  // this tool exists to detect. DOM and raster must describe one layout.
  //
  // `CHART_RASTER_LEGACY=1` takes the pre-fix `fullPage: true` instead, which is how the
  // before/after is measured on one page in one run rather than asserted.
  const legacy = process.env.CHART_RASTER_LEGACY === '1';
  const firstHeight = await page.evaluate(() => document.body.scrollHeight);
  const plan = chooseCapture({ docHeight: firstHeight, viewportHeight: H });
  const grow = !legacy && plan.mode === 'grow';
  if (grow) {
    await page.setViewportSize({ width: W, height: plan.height });
    await page.waitForTimeout(2500);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(500);
  } else if (plan.warning && !legacy) {
    console.error(plan.warning);
  }

  // What the DOM says, in DOCUMENT coordinates — the raster is a document, not a viewport.
  //
  // A line only counts as one the picture OWES us if it would be drawn at all: a zero-width
  // box, `display:none`, `visibility:hidden` or a fully transparent stroke are all reasons a
  // path can sit in the DOM and legitimately not appear, and calling those #4664 would be a
  // false alarm on exactly the pages a lane is least able to check by eye.
  const dom = await page.evaluate(() => {
    const box = document.querySelector('.recharts-wrapper');
    const b = box ? box.getBoundingClientRect() : null;
    const lines = [...document.querySelectorAll('path.recharts-line-curve')].map((p) => {
      const cs = getComputedStyle(p);
      let bb = null;
      try { bb = p.getBBox(); } catch { /* not rendered */ }
      const alpha = Number(cs.strokeOpacity) * Number(cs.opacity || 1);
      return {
        verts: (p.getAttribute('d') || '').split(/(?=[ML])/).length,
        stroke: cs.stroke,
        // The tell #4664 hid behind: Recharts animates a line in by growing the
        // DASH, so `d` is byte-identical from t=0 to settled and reads as proof
        // the chart is fine. Reported so a caller can see a mid-animation read.
        dash: cs.strokeDasharray,
        // `width > 0 || height > 0`, never `&&`. A market whose probability never moved
        // draws a perfectly FLAT line, whose bbox height is exactly 0 — and an `&&` here
        // excused precisely the charts a LOOK most needs checked (measured: two flat
        // lines on `/events/15307099` read as "not owed"). Only a path with no extent in
        // either direction is genuinely nothing to photograph.
        drawable:
          cs.display !== 'none' &&
          cs.visibility !== 'hidden' &&
          alpha > 0 &&
          !!bb && (bb.width > 0 || bb.height > 0),
      };
    });
    return {
      lines,
      chartBox: b ? { x: b.x + scrollX, y: b.y + scrollY, w: b.width, h: b.height } : null,
      docHeight: document.body.scrollHeight,
    };
  });

  if (!dom.chartBox) {
    console.log(`BLIND ${url} — no .recharts-wrapper on this page, nothing to check`);
    code = 4;
    throw { handled: true };
  }

  // The SECOND capture: the same page with the line layer hidden. The verdict is the
  // difference between the two inside the chart box.
  //
  // WHY A DIFFERENTIAL AND NOT A COLOUR COUNT. The first cut of this tool read each line's
  // computed `stroke` and hunted the raster for pixels of that colour. It reported nine
  // correctly-drawn lines on `/events/15307099` as MISSING, because their stroke is
  // `rgba(0, 0, 0, 0.15)` — the tool parsed the first three numbers, went looking for BLACK,
  // and the pixels on screen are the light grey that 15% black composites to over white. A
  // colour count also cannot tell a line from anything else already that colour (a gridline,
  // an axis, a label). Hiding the layer and diffing asks the question directly — "is any of
  // this picture drawn BY the line?" — and is blind to alpha, blend mode and palette alike.
  const shoot = async (path) => {
    if (grow) await page.screenshot({ path });
    else await page.screenshot({ path, fullPage: true });
  };
  await shoot(OUT);
  console.log(
    grow
      ? `capture    viewport grown to ${plan.height}px (the rail's whole-page shot)`
      : `capture    ${legacy ? 'fullPage (LEGACY arm, pre-#4664-fix)' : 'fullPage (over the grown-capture limit)'}`,
  );
  const BASE = `${OUT}.lines-hidden.png`;
  await page.addStyleTag({ content: 'path.recharts-line-curve{visibility:hidden !important}' });
  await page.waitForTimeout(800);
  await shoot(BASE);

  const raster = await page.evaluate(
    async ({ withLines, without, box, dsf }) => {
      const load = (b64) =>
        new Promise((res, rej) => {
          const img = new Image();
          img.onload = () => res(img);
          img.onerror = () => rej(new Error('a PNG did not decode'));
          img.src = `data:image/png;base64,${b64}`;
        });
      const [a, b] = await Promise.all([load(withLines), load(without)]);
      if (a.width !== b.width || a.height !== b.height) {
        return { error: `the two captures are different sizes (${a.width}x${a.height} vs ${b.width}x${b.height})` };
      }
      const x = Math.max(0, Math.round(box.x * dsf));
      const y = Math.max(0, Math.round(box.y * dsf));
      const w = Math.min(Math.round(box.w * dsf), a.width - x);
      const h = Math.min(Math.round(box.h * dsf), a.height - y);
      if (w <= 0 || h <= 0) return { error: 'the chart box falls outside the raster', img: [a.width, a.height] };
      const crop = (img) => {
        const cv = document.createElement('canvas');
        cv.width = w;
        cv.height = h;
        const ctx = cv.getContext('2d');
        ctx.drawImage(img, x, y, w, h, 0, 0, w, h);
        return ctx.getImageData(0, 0, w, h).data;
      };
      const da = crop(a);
      const db = crop(b);
      let diff = 0;
      for (let i = 0; i < da.length; i += 4) {
        // A per-channel threshold, not equality: PNG encoding and antialiasing move a
        // pixel by a unit or two, and a rig that calls that a line would never say AGREE.
        if (Math.abs(da[i] - db[i]) > 8 || Math.abs(da[i + 1] - db[i + 1]) > 8 || Math.abs(da[i + 2] - db[i + 2]) > 8) diff++;
      }
      return { diff, img: [a.width, a.height], crop: [w, h] };
    },
    { withLines: readFileSync(OUT).toString('base64'), without: readFileSync(BASE).toString('base64'), box: dom.chartBox, dsf: 2 },
  );
  try { unlinkSync(BASE); } catch {}

  if (raster.error) {
    console.error(`FAIL ${url} :: ${raster.error}`);
    code = 1;
    throw { handled: true };
  }

  console.log(`url        ${url} @${W}px  docHeight=${dom.docHeight}  raster=${raster.img.join('x')}`);
  console.log(`chartBox   x=${Math.round(dom.chartBox.x)} y=${Math.round(dom.chartBox.y)} ${Math.round(dom.chartBox.w)}x${Math.round(dom.chartBox.h)}`);
  const drawable = dom.lines.filter((l) => l.drawable);
  dom.lines.forEach((l, i) => {
    console.log(
      `line ${i}     ${l.stroke}  verts=${l.verts}  ${l.drawable ? 'drawable' : 'NOT DRAWABLE (hidden/empty in the DOM, not owed)'}`,
    );
  });
  console.log(`pixels     ${raster.diff} of ${raster.crop[0] * raster.crop[1]} in the chart box are drawn BY the line layer`);

  if (drawable.length === 0) {
    console.log('AGREE — the DOM has no drawable line, and the picture shows none: a genuinely empty chart.');
    code = 0;
  } else if (raster.diff > 0) {
    console.log(`AGREE — the picture contains the line layer the DOM has (${drawable.length} drawable line(s)).`);
    code = 0;
  } else {
    console.log(
      `FALSE-EMPTY — the DOM has ${drawable.length} drawable line(s) and the picture contains NONE of them (#4664).`,
    );
    // A mid-animation dash is the smoking gun, so name it rather than leaving the
    // next reader to rediscover that `d` is the one attribute that never moves.
    for (const [i, l] of dom.lines.entries()) {
      if (l.drawable) console.log(`  line ${i} stroke-dasharray at read time: ${l.dash}`);
    }
    code = 3;
  }
} catch (e) {
  if (!e || !e.handled) {
    console.error(`FAIL ${url} :: ${e && e.message ? e.message : e}`);
    code = 1;
  }
} finally {
  await browser.close();
  if (!KEEP) { try { unlinkSync(OUT); } catch {} }
}
process.exit(code);
