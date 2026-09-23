#!/usr/bin/env node
//
// #8135 — CAN A READER ACTUALLY READ EVERY X-AXIS TICK ON A FUTURES BOARD?
//
// WHY A JEST RENDER IS NOT ENOUGH. #4262's guard measures each tick's box inside
// the SVG viewBox, and it is a real guard — but the futures chart is an 800-unit
// viewBox laid out 600px wide inside an `overflow-x-auto` scroller only ~318px
// across, anchored hard to its right edge. So the box a jest render calls "well
// inside the plot" can be scrolled off the screen entirely, and #4262's OWN
// left-hand defect was never a clip at all: the label was 0.47px inside the plot
// with an opaque chip painted on top of it. Widening a label — which is what
// #8135 does, `1:48 PM` becoming `Aug 24, 1:48 PM` — is exactly the change that
// can reintroduce either. Neither is visible to `renderToStaticMarkup`.
//
// WHAT IT CLASSIFIES, and the three states are deliberately not one:
//
//   OFFSCREEN  the tick's box is wholly outside the scroller's visible window.
//              Normal here: the chart rests scrolled to the newest data, so the
//              oldest ticks sit behind the left edge and the reader scrolls to
//              them. Counted, never failed on.
//   CLIPPED    the box CROSSES an edge of that window, so the reader sees half a
//              label and no way to tell it is half. This is the failure.
//   FADED      wholly visible, but overlapping `futures-chart-fade-left/right` —
//              the chart's own 32px decorative gradient marking that the plot
//              scrolls further. Dimmed, not cut. Reported, not failed on: it is
//              a pre-existing affordance and calling it a defect would red every
//              scrolled chart in the app.
//   CLEAR      wholly visible and untouched by a fade.
//
// `--cache DIR` fulfils `api.bainluck.com` from a directory `look-local.mjs`
// populated, so this reads the SAME payload the screenshot did. WITHOUT it a
// local page renders no chart at all and the probe finds no ticks — which is the
// shape of a pass if you read a count and not the verdict, so that case has its
// own exit code.
//
//   node tools/futures-axis-tick-legibility-8135.mjs <url> [width] [--cache DIR]
//
// exit 0 no visible tick is cut  ·  3 a tick is CLIPPED  ·  4 no ticks found

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const url = process.argv[2];
const width = Number(process.argv[3] ?? 390);
const cacheIdx = process.argv.indexOf("--cache");
const cacheDir = cacheIdx > -1 ? process.argv[cacheIdx + 1] : null;
if (!url) {
  console.error(
    "usage: futures-axis-tick-legibility-8135.mjs <url> [width] [--cache DIR]",
  );
  process.exit(2);
}

const pwRoot = fs
  .readdirSync(`${process.env.HOME}/.npm/_npx`)
  .map((h) => `${process.env.HOME}/.npm/_npx/${h}/node_modules/playwright/index.mjs`)
  .find((p) => fs.existsSync(p));
if (!pwRoot) {
  console.error("FATAL: no playwright in the npx cache");
  process.exit(3);
}
const { chromium } = await import(pwRoot);

const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
const args = [
  "--single-process",
  "--no-sandbox",
  "--disable-gpu",
  "--disable-crashpad",
  "--disable-dev-shm-usage",
];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  // INVERTED vs shop-shot.mjs, for look-local.mjs's reason: loopback must go
  // direct or a local build is unreachable through a proxy on port 4136.
  args.push("--proxy-bypass-list=127.0.0.1;localhost");
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width, height: 900 },
  deviceScaleFactor: 2,
  isMobile: width < 500,
  hasTouch: width < 500,
});

let servedFromCache = 0;
let missed = 0;
if (cacheDir) {
  await page.route("**://api.bainluck.com/**", async (route) => {
    const key = createHash("sha1")
      .update(route.request().url())
      .digest("hex")
      .slice(0, 16);
    const file = path.join(cacheDir, `${key}.json`);
    if (fs.existsSync(file)) {
      servedFromCache++;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: fs.readFileSync(file, "utf8"),
      });
    }
    missed++;
    return route.continue();
  });
}

await page.goto(url, { waitUntil: "networkidle", timeout: 90000 });
await page.waitForTimeout(2500);

const report = await page.evaluate(() => {
  // Found by geometry, not by a class name: the x-axis row is the SVG <text>
  // nodes sharing the largest `y` in the chart's own svg. A restyle cannot make
  // this probe silently measure nothing.
  const svg = [...document.querySelectorAll("svg")].find(
    (s) => s.querySelectorAll("text").length >= 3,
  );
  if (!svg) return { ticks: [], scroller: null };

  let el = svg.parentElement;
  let scroller = null;
  while (el && el !== document.body) {
    if (el.scrollWidth > el.clientWidth + 2) {
      scroller = el;
      break;
    }
    el = el.parentElement;
  }
  // No scroller is a legitimate state (a chart that fits). The whole viewport is
  // then the window, so nothing can be off-screen for this reason.
  const win = scroller
    ? scroller.getBoundingClientRect()
    : { left: 0, right: window.innerWidth };

  const fades = ["left", "right"]
    .map((side) => document.querySelector(`[data-testid="futures-chart-fade-${side}"]`))
    .filter(Boolean)
    .map((f) => {
      const r = f.getBoundingClientRect();
      return { left: r.left, right: r.right };
    });

  const texts = [...svg.querySelectorAll("text")];
  const ys = texts.map((t) => Number(t.getAttribute("y")));
  const maxY = Math.max(...ys.filter(Number.isFinite));

  const ticks = texts
    .filter((t) => Number(t.getAttribute("y")) === maxY)
    .map((t) => {
      const r = t.getBoundingClientRect();
      const insideL = r.left >= win.left - 0.5;
      const insideR = r.right <= win.right + 0.5;
      const wholly_out = r.right <= win.left || r.left >= win.right;
      let state;
      if (wholly_out) state = "OFFSCREEN";
      else if (!insideL || !insideR) state = "CLIPPED";
      else if (fades.some((f) => r.left < f.right && r.right > f.left)) state = "FADED";
      else state = "CLEAR";
      return {
        text: t.textContent.trim(),
        anchor: t.getAttribute("text-anchor"),
        left: Math.round(r.left * 10) / 10,
        right: Math.round(r.right * 10) / 10,
        state,
      };
    })
    .sort((a, b) => a.left - b.left);

  return {
    scroller: scroller
      ? {
          left: Math.round(win.left * 10) / 10,
          right: Math.round(win.right * 10) / 10,
          scrollLeft: Math.round(scroller.scrollLeft),
          scrollWidth: scroller.scrollWidth,
          clientWidth: scroller.clientWidth,
        }
      : null,
    fades: fades.map((f) => ({
      left: Math.round(f.left * 10) / 10,
      right: Math.round(f.right * 10) / 10,
    })),
    ticks,
  };
});

await browser.close();

const { ticks } = report;
if (ticks.length === 0) {
  console.log(
    JSON.stringify({ url, width, servedFromCache, missed, ...report, verdict: "NO-TICKS" }, null, 1),
  );
  process.exit(4);
}

const tally = ticks.reduce((a, t) => ({ ...a, [t.state]: (a[t.state] ?? 0) + 1 }), {});
const clipped = tally.CLIPPED ?? 0;
console.log(
  JSON.stringify(
    { url, width, servedFromCache, missed, ...report, tally, verdict: clipped ? "CLIPPED" : "OK" },
    null,
    1,
  ),
);
process.exit(clipped ? 3 : 0);
