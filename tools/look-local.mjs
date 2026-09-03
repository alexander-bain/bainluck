#!/usr/bin/env node
//
// LOOK AT A LOCALLY-SERVED BUILD — the pre-merge half of tools/look.sh.
//
// WHY THIS EXISTS. `tools/look.sh` → `shop-shot.mjs` launches Chromium with
// `--proxy-bypass-list=<-loopback>`, which means *do NOT bypass the proxy for
// loopback*. That is right for production URLs and fatal for
// `http://127.0.0.1:PORT`, so the standard LOOK rail can only ever photograph
// DEPLOYED code. A before/after on an unmerged frontend branch needs its own rig
// and this is it: the bypass list is inverted, and the page's own fetches to
// `api.bainluck.com` are fulfilled by `curl`, which has the session's egress.
//
// THE API CACHE IS THE POINT, NOT AN OPTIMISATION. Two builds photographed
// minutes apart against a LIVE endpoint differ by whatever the world did in
// between — scores move, a live game goes final, the feed reranks — and those
// differences land in the picture looking exactly like the change under review.
// `--cache DIR` records every API response on first use and replays it on every
// subsequent run, so the BEFORE and AFTER builds are handed byte-identical JSON
// and the only variable left is the code. Run BEFORE first to populate, AFTER
// second to reuse; the census printed at the end says which happened.
//
// DO NOT JUDGE THE RESULT FROM THE PNG (gotcha #53). `--census SELECTOR=NAME`
// counts real DOM after the shot and prints it, because a card can look
// plausible in an image and be missing every number it exists to show.
//
// Kill the server by PID, never `pkill -f "next start -p PORT"` — after boot the
// process is `next-server (vX)`, so the pattern misses it and you silently
// re-photograph the OLD build.
//
// Usage:
//   node tools/look-local.mjs --url http://127.0.0.1:4136/sports \
//     --out shot.png --width 390 --cache /tmp/apicache \
//     --census '[data-testid="feed-card-prematch-home"]=prematchHome'

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const arg = (name, fallback = null) => {
  const i = argv.indexOf(`--${name}`);
  return i === -1 ? fallback : argv[i + 1];
};
const flag = (name) => argv.includes(`--${name}`);

const url = arg("url");
const out = arg("out");
if (!url || !out) {
  console.error("usage: look-local.mjs --url URL --out FILE.png [--width 390] [--cache DIR] [--census SEL=NAME]...");
  process.exit(2);
}
const width = parseInt(arg("width", "390"), 10);
const cacheDir = arg("cache", null);
const waitFor = arg("wait", null);
const settleMs = parseInt(arg("settle", "2500"), 10);
const fullPage = !flag("no-full-page");

const censuses = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--census") {
    // Split on the LAST `=`, never the first: an attribute selector
    // (`[data-testid="x"]`) contains one, and splitting on it yields an invalid
    // selector plus a nonsense name — which still counts SOMETHING and so reads
    // like a real census.
    const spec = argv[i + 1];
    const cut = spec.lastIndexOf("=");
    const sel = cut === -1 ? spec : spec.slice(0, cut);
    const name = cut === -1 ? spec : spec.slice(cut + 1);
    censuses.push({ sel, name });
  }
}

if (cacheDir) fs.mkdirSync(cacheDir, { recursive: true });

// Playwright lives in the npx cache; a fresh install is not available
// (the registry is unreachable from this sandbox).
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
  "--single-process", // clears the Mach port rendezvous the sandbox blocks
  "--no-sandbox",
  "--disable-gpu",
  "--disable-crashpad",
  "--disable-dev-shm-usage",
];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  // INVERTED vs shop-shot.mjs: loopback must go direct, or the local build is
  // unreachable through a proxy that has never heard of port 4136.
  args.push("--proxy-bypass-list=127.0.0.1;localhost");
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width, height: 900 },
  deviceScaleFactor: 2,
  isMobile: width < 500,
  hasTouch: width < 500,
});

let served = 0;
let fetched = 0;
await page.route("**://api.bainluck.com/**", async (route) => {
  const target = route.request().url();
  const key = createHash("sha1").update(target).digest("hex").slice(0, 16);
  const file = cacheDir ? path.join(cacheDir, `${key}.json`) : null;
  if (file && fs.existsSync(file)) {
    served++;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: fs.readFileSync(file, "utf8"),
    });
  }
  let body;
  try {
    // curl, not the browser: this process has the session egress the page does not.
    body = execFileSync("curl", ["-sS", "--max-time", "45", target], {
      maxBuffer: 64 * 1024 * 1024,
      encoding: "utf8",
    });
  } catch (err) {
    console.error(`  ! upstream failed ${target}: ${err.message}`);
    return route.fulfill({ status: 502, contentType: "application/json", body: "{}" });
  }
  fetched++;
  if (file) fs.writeFileSync(file, body);
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body,
  });
});

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
if (waitFor) {
  await page.waitForSelector(waitFor, { timeout: 60000 }).catch(() => {
    console.error(`  ! never saw ${waitFor}`);
  });
}
await page.waitForTimeout(settleMs);

// The cookie banner covers real content in every full-page shot.
for (const label of ["Accept", "Got it", "OK"]) {
  const btn = page.getByRole("button", { name: label });
  if (await btn.count().catch(() => 0)) {
    await btn.first().click().catch(() => {});
    break;
  }
}
await page.waitForTimeout(300);

await page.screenshot({ path: out, fullPage });

const counts = {};
for (const { sel, name } of censuses) {
  // A selector the browser refuses is a broken census, not a zero. Say so and
  // fail, rather than printing a number nobody can tell apart from a real one.
  const n = await page.evaluate((s) => {
    try {
      return document.querySelectorAll(s).length;
    } catch {
      return -1;
    }
  }, sel);
  if (n < 0) {
    console.error(`FATAL: invalid census selector ${JSON.stringify(sel)}`);
    await browser.close();
    process.exit(4);
  }
  counts[name] = n;
}
await browser.close();

// Assert the artifact EXISTS and is non-empty — a wrapper whose last line is an
// echo will happily report success over a dead camera (gotcha #124).
if (!fs.existsSync(out) || fs.statSync(out).size === 0) {
  console.error(`FATAL: no bytes written to ${out}`);
  process.exit(1);
}
console.log(
  JSON.stringify({
    out,
    bytes: fs.statSync(out).size,
    width,
    api: { servedFromCache: served, fetchedUpstream: fetched },
    census: counts,
  }),
);
