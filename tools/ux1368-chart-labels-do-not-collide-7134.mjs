// ux1368-chart-labels-do-not-collide-7134.mjs <baseUrl> <eventId> [out.png]
//
// #7134 — DO THE CHART'S OWN LABELS LAND ON TOP OF EACH OTHER?
//
// At the end of a settled game the Win Probability chart crowds three labels
// into one ~40px corner: the last period markers (`B8`, `T9`) and the green
// end-value callout (`100%`). The reader's eye goes to exactly that corner —
// it is the number the settled chart exists to print — and it is the one that
// is hardest to read.
//
// 🔴 IT READS GLYPH GEOMETRY, NOT THE FIX'S OWN MARKUP (ux/1351, ux/1352).
// A probe keyed on a `data-callout-*` attribute the repair introduces can never
// measure the UNFIXED production page — it reports "attribute missing" on the
// exact build whose defect it exists to bank. So this walks every `<text>` the
// chart has always drawn and intersects their client rects. That selector
// predates the repair and survives it.
//
// 🔴 IT PARTITIONS BY <svg>, NOT BY HEADING. The Score Differential chart below
// carries the SAME marker set (`T3`/`B8`/`T9`) and does NOT collide, so a probe
// that pooled every text node on the page would mix two charts' corners and
// could report a collision that no single chart has. Each svg is measured on
// its own and named by the nearest heading above it, so the output says WHICH
// chart.
//
// 🔴 THE EXIT CODE IS KEYED ON THE DEFECT, THE OUTPUT IS NOT. #7134 is the
// END-VALUE CALLOUT landing on something, so only a pair with the callout in it
// can fail this probe. Every other overlapping pair is still PRINTED, under its
// own heading — two of them are live on this page (the first x-axis tick's box
// against the lowest y-axis tick's, 1–3px, on both charts and on both arms) and
// a probe that exited 3 on those could never pay as this fix's after-check,
// while one that filtered them out of the output would be hiding what it saw.
//
// EXIT CODES ARE A STORY (gotcha #124):
//   0  nothing overlaps the end-value callout — paid
//   3  something overlaps it — the defect, live
//   4  no chart svg, no chart with two labels, or NO CALLOUT ON THE PAGE =
//      NOTHING WAS CHECKED, not a pass
//   2  usage · 1 camera/navigation
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

const [base, eventId, out] = process.argv.slice(2);
if (!base || !eventId) {
  console.error('usage: node ux1368-chart-labels-do-not-collide-7134.mjs <baseUrl> <eventId> [out.png]');
  process.exit(2);
}
const URL = `${base.replace(/\/$/, '')}/events/${eventId}`;

/**
 * Every `<text>` in every chart svg, with its client rect and its chart's name.
 *
 * Axis ticks are KEPT, not filtered. A callout sitting on the x-axis tick below
 * it is the same smudge to a reader as one sitting on a marker, and deciding in
 * advance which glyphs "count" is how a measurement talks itself out of the
 * defect it came to find.
 */
const READ_LABELS = () =>
  Array.from(document.querySelectorAll('svg')).map((svg, i) => {
    // Name the chart by the nearest preceding heading-ish text, so the output
    // says "Win Probability" rather than "svg #2".
    let name = null;
    for (let n = svg.parentElement; n && !name; n = n.parentElement) {
      const h = n.querySelector('h1,h2,h3,h4,[class*="uppercase"]');
      if (h && (h.textContent || '').trim()) name = h.textContent.trim().slice(0, 40);
      if (n.tagName === 'MAIN' || n.tagName === 'BODY') break;
    }
    const labels = Array.from(svg.querySelectorAll('text'))
      .map((t) => {
        const r = t.getBoundingClientRect();
        const ff = t.getAttribute('font-family') || getComputedStyle(t).fontFamily || '';
        const anchor = t.getAttribute('text-anchor') || getComputedStyle(t).textAnchor;
        const text = (t.textContent || '').trim();
        return {
          text,
          x: Math.round(r.x),
          y: Math.round(r.y),
          w: Math.round(r.width),
          h: Math.round(r.height),
          // The end-value callout, read the way ux/1352 reads it: monospace,
          // anchored `end`, a bare percentage. That selector predates the repair
          // and survives it, unlike any `data-callout-*` the fix might add. The
          // y-axis `100%` tick is also a percentage and is NOT monospace, which
          // is what keeps the two apart.
          isCallout: /monospace/i.test(ff) && anchor === 'end' && /^[<>]?\d{1,3}%$/.test(text),
        };
      })
      // A zero-area node draws nothing, so it can neither be read nor collide.
      .filter((l) => l.text && l.w > 0 && l.h > 0);
    const box = svg.getBoundingClientRect();
    return {
      idx: i,
      name: name || `svg #${i}`,
      labels,
      box: { x: box.x, y: box.y, w: box.width, h: box.height },
    };
  });

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const launchArgs = [
  '--no-sandbox',
  '--single-process',
  '--disable-gpu',
  '--disable-crashpad',
  '--disable-dev-shm-usage',
];
if (proxy) {
  launchArgs.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(URL)) {
    launchArgs.push('--proxy-bypass-list=<-loopback>');
  }
}

const overlap = (a, b) => {
  const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return ox > 0 && oy > 0 ? { ox, oy } : null;
};

const isLoopback = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(URL);

(async () => {
  const browser = await chromium.launch({ args: launchArgs });

  // ═══ MEASURING A LOCAL BUILD ON REAL DATA ═══
  //
  // The defect is a collision between production's own inning times and
  // production's own final probability, so the honest AFTER — before the fix is
  // deployed — is the LOCAL build fed the LIVE payload. Two things block that,
  // and both are quiet:
  //
  // 1. `api.bainluck.com` sends no `Access-Control-Allow-Origin` for a
  //    `127.0.0.1` origin, so every fetch the page makes is blocked and the page
  //    renders its empty state. The probe then exits 4 — correct, and NOT a pass.
  // 2. `route.fetch()` runs in the playwright SERVER process, not the browser,
  //    so it does not inherit `--proxy-server` and dies `connect EPERM` in the
  //    agent sandbox. The proxy has to be on the browser CONTEXT for the
  //    interception to reach the network at all — and then it needs an explicit
  //    loopback `bypass`, because a context proxy overrides Chromium's implicit
  //    one and the page itself stops loading.
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    proxy: proxy ? { server: proxy, bypass: 'localhost,127.0.0.1,::1' } : undefined,
  });
  const page = await ctx.newPage();

  // Only ever for a loopback target: against production this would put a shim
  // between the probe and the thing it came to measure.
  if (isLoopback) {
    await page.route('https://api.bainluck.com/**', async (route) => {
      try {
        const res = await route.fetch();
        await route.fulfill({
          response: res,
          headers: { ...res.headers(), 'access-control-allow-origin': '*' },
        });
      } catch (e) {
        console.error(`[api shim] ${route.request().url().slice(0, 90)} — ${e.message.split('\n')[0]}`);
        await route.abort();
      }
    });
  }

  try {
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 90000 });
  } catch (e) {
    console.error(`navigation failed: ${e.message}`);
    await browser.close();
    process.exit(1);
  }
  // The charts live ~700px down and recharts animates in. Scroll them into the
  // viewport first: `getBoundingClientRect` on an off-screen node is still
  // geometrically true, but the series only mounts once the chart is near.
  await page.evaluate(() => window.scrollTo(0, 700));
  await page.waitForTimeout(4000);

  const charts = await page.evaluate(READ_LABELS);
  const measured = charts.filter((c) => c.labels.length >= 2);

  const onCallout = [];
  const elsewhere = [];
  for (const c of measured) {
    for (let i = 0; i < c.labels.length; i++) {
      for (let j = i + 1; j < c.labels.length; j++) {
        const ov = overlap(c.labels[i], c.labels[j]);
        if (!ov) continue;
        const pair = { chart: c.name, a: c.labels[i], b: c.labels[j], ...ov };
        (c.labels[i].isCallout || c.labels[j].isCallout ? onCallout : elsewhere).push(pair);
      }
    }
  }

  for (const c of measured) {
    console.log(`\n${c.name}  —  ${c.labels.length} label(s)`);
    for (const l of c.labels) {
      console.log(
        `   ${String(l.text).padEnd(10)} x=${String(l.x).padStart(4)} w=${String(l.w).padStart(3)}` +
          ` y=${String(l.y).padStart(4)} h=${String(l.h).padStart(3)}${l.isCallout ? '   <- end-value callout' : ''}`,
      );
    }
  }

  const calloutCount = measured.reduce((n, c) => n + c.labels.filter((l) => l.isCallout).length, 0);

  // Shoot the chart the callout is IN, not the viewport: the charts sit ~700px
  // down a long page, so a viewport shot at any scroll position is a picture of
  // something else. Geometry above is scroll-independent; a photograph is not.
  if (out) {
    const subject = measured.find((c) => c.labels.some((l) => l.isCallout)) ?? measured[0];
    const b = subject?.box;
    if (b && b.w > 0 && b.h > 0) {
      await page.evaluate((top) => window.scrollBy(0, top - 60), b.y);
      await page.waitForTimeout(800);
      const after = await page.evaluate(
        (idx) => {
          const r = document.querySelectorAll('svg')[idx].getBoundingClientRect();
          return { x: r.x, y: r.y, w: r.width, h: r.height };
        },
        subject.idx,
      );
      await page.screenshot({
        path: out,
        clip: { x: Math.max(0, after.x - 4), y: Math.max(0, after.y - 4), width: after.w + 8, height: after.h + 8 },
      });
    } else {
      await page.screenshot({ path: out });
    }
    console.log(`\nshot: ${out}`);
  }
  await browser.close();

  if (measured.length === 0 || calloutCount === 0) {
    console.error(
      `\nNOTHING WAS CHECKED (this is not a pass): ${measured.length} chart(s) with labels,` +
        ` ${calloutCount} end-value callout(s) found`,
    );
    process.exit(4);
  }

  if (elsewhere.length) {
    // Printed, not failed: see the header. These are real and they are not this
    // issue — recording them here is what stops the next reader re-finding them.
    console.log(`\nother overlapping pairs (NOT #7134, reported only): ${elsewhere.length}`);
    for (const c of elsewhere) {
      console.log(
        `  [${c.chart}] "${c.a.text}" (x=${c.a.x} y=${c.a.y}) ∩ "${c.b.text}" (x=${c.b.x} y=${c.b.y})` +
          `  overlap ${c.ox}x${c.oy}px`,
      );
    }
  }

  if (onCallout.length) {
    console.error(`\nTHE END-VALUE CALLOUT IS OVERLAPPED — ${onCallout.length} pair(s), #7134 is live`);
    for (const c of onCallout) {
      console.error(
        `  [${c.chart}] "${c.a.text}" (x=${c.a.x} y=${c.a.y}) ∩ "${c.b.text}" (x=${c.b.x} y=${c.b.y})` +
          `  overlap ${c.ox}x${c.oy}px`,
      );
    }
    process.exit(3);
  }
  console.log(
    `\nCALLOUT CLEAR on all ${calloutCount} callout(s) across ${measured.length} chart(s) — #7134 paid`,
  );
  process.exit(0);
})();
