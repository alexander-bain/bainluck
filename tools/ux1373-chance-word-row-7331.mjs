// ux1373-chance-word-row-7331.mjs — photograph the ROW, not the page, on an unmerged build.
//
// WHY THIS EXISTS. #7331's ship is seven characters on one row of one bundle, and the two rails
// that could see it each miss by one thing:
//
//   * `tools/look.sh` / `discover-card-by-text.mjs` scroll to a card BY TEXT, which is the only
//     honest way to address a feed that reshuffles — but they can only photograph DEPLOYED code.
//   * `tools/look-local.mjs` photographs a local build with the API shimmed and cached, which is
//     the pre-merge rail — but it shoots `fullPage`, and on a 15,000px Discover feed the row under
//     review is 40px of a 2.3MB image nobody can read.
//
// So this is look-local's rig (inverted proxy bypass, `page.route` fulfilling api.bainluck.com from
// the same on-disk cache, CORS header on every fulfilled response) with `discover-card-by-text`'s
// addressing: scroll the element into view and shoot the VIEWPORT around it. Reusing the cache
// directory a look-local run populated is the point — the BEFORE that produced it and this AFTER
// are handed byte-identical JSON, so the only variable left is the code.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 the selector matched nothing after
// the page settled — which on this feed is a real answer ("this draw served no ambiguous row"),
// not a camera failure — 1 anything else. A no-match writes NO png and removes a stale one, so an
// artifact can never claim a specimen it does not contain.
//
// Usage:
//   node tools/ux1373-chance-word-row-7331.mjs --url http://127.0.0.1:4173/ \
//     --sel '[data-testid="compact-row-chance"]' --out after.png --cache /tmp/apicache [--width 390]
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
function playwright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (fs.existsSync(npx)) {
    for (const d of fs.readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/playwright`;
      if (fs.existsSync(p)) return require(p);
    }
  }
  return require("playwright");
}

const argv = process.argv.slice(2);
const arg = (name, fallback = null) => {
  const i = argv.indexOf(`--${name}`);
  return i === -1 ? fallback : argv[i + 1];
};
const url = arg("url");
const out = arg("out");
const sel = arg("sel");
const cacheDir = arg("cache");
const width = Number(arg("width", "390"));
if (!url || !out || !sel) {
  console.error("usage: --url URL --out FILE.png --sel CSS [--cache DIR] [--width 390]");
  process.exit(2);
}
if (cacheDir) fs.mkdirSync(cacheDir, { recursive: true });

const { chromium } = playwright();
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
const args = [
  // 🪤 NOT OPTIONAL, and the failure does not look like a missing flag: without it Chromium dies at
  // launch with `bootstrap_check_in … Permission denied (1100)` and playwright reports "Target page,
  // context or browser has been closed" — which reads as a crashed page, not a blocked Mach port.
  // look-local.mjs carries the same line for the same reason.
  "--single-process",
  "--no-sandbox",
  "--disable-gpu",
  "--disable-crashpad",
  "--disable-dev-shm-usage",
];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  // INVERTED vs shop-shot.mjs, exactly as look-local.mjs has it: loopback must go direct or the
  // local build is unreachable through a proxy that has never heard of port 4173.
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
    body = execFileSync("curl", ["-sS", "--max-time", "45", target], { maxBuffer: 64 * 1024 * 1024, encoding: "utf8" });
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
await page.waitForTimeout(6000);
for (const label of ["Accept", "Got it", "OK"]) {
  const btn = page.getByRole("button", { name: label });
  if (await btn.count().catch(() => 0)) {
    await btn.first().click().catch(() => {});
    break;
  }
}
await page.waitForTimeout(400);

const found = await page.locator(sel).count();
if (!found) {
  console.error(`NO MATCH: ${sel} (api: served ${served} / fetched ${fetched})`);
  if (fs.existsSync(out)) fs.rmSync(out);
  await browser.close();
  process.exit(4);
}
const target = page.locator(sel).first();
await target.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);

// 🪤 THE CLIP IS AROUND THE CARD, NOT THE MATCH. The first draft clipped to the matched element
// plus 16px and produced a picture reading `1% chance` — the `4` of `41%` was outside the box, so
// the artifact showed the word without the number it qualifies, which is the one thing under
// review. The row's own `<a>` is the unit a reader reads, and the sibling rows above it are the
// CONTROL half of the claim (they must NOT carry the word), so the clip takes the full page width
// and reaches back over the rows above.
const row = target.locator("xpath=ancestor::a[1]");
const box = (await row.count()) ? await row.first().boundingBox() : await target.boundingBox();
const above = Number(arg("above", "240"));
await page.screenshot({
  path: out,
  clip: {
    x: 0,
    y: Math.max(0, box.y - above),
    width,
    height: box.height + above + 40,
  },
});
console.log(JSON.stringify({ out, matched: found, api: { servedFromCache: served, fetchedUpstream: fetched } }));
await browser.close();
