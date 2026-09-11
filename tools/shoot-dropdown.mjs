#!/usr/bin/env node
/**
 * shoot-dropdown.mjs — photograph the search typeahead dropdown a reader sees.
 *
 * WHY THIS EXISTS, beside `tools/look.sh`: look.sh clicks, it does not type, so
 * it physically cannot photograph the typeahead — the dropdown only comes into
 * existence after someone enters a query. Any mystery shop of the search
 * surface (standing notice 48) therefore needs this rig rather than look.sh.
 * It is the two halves borrowed and joined: the sandbox launch and the
 * playwright resolution from `tools/shop-shot.mjs`, and the selectors and open
 * sequence from `frontend/e2e/specs/search-answer.spec.ts` — so the shot and
 * the e2e rail agree about what "the dropdown" is. Built for #5058's LOOK
 * (lane1/242-243), generalised here at ux/1192's ask so the next lane that
 * needs the search surface photographed does not write a fourth one.
 *
 *   node tools/shoot-dropdown.mjs <query> <out.png> [width]
 *   SHOOT_BASE=http://localhost:3000 node tools/shoot-dropdown.mjs patriots a.png
 *
 * Defaults: query `patriots`, out `dropdown.png`, width `390` (phone), target
 * production — the only surface a LOOK (standing notice 4) may be paid on.
 * `SHOOT_BASE` is for the OTHER half of the job: proving a fix renders BEFORE it
 * is offered, against a local dev server. It never satisfies a LOOK.
 *
 * Two behaviours worth keeping when you edit it:
 *   · it WAITS for the mobile trigger before asking whether it is visible —
 *     see the comment at the branch, this one has already cost a session;
 *   · it EXITS 3 rather than writing a pass-looking PNG of an empty dropdown,
 *     so "the file exists" can never be mistaken for "the shot succeeded".
 * It prints the rows it photographed to stderr, so the PNG is never the only
 * record of what the shutter caught.
 */
import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + "/";
}
const { chromium } = createRequire(findPlaywright())("playwright");

const [query = "patriots", out = "dropdown.png", width = "390"] = process.argv.slice(2);
const MOBILE_TRIGGER = 'button[aria-label="Open search"]';
const INPUT = 'input[aria-label="Search teams, games, and futures"]:visible';
const ROW = '[data-testid="search-suggestion"]';
const SEASON = '[data-testid="search-team-season"]';

const BASE = (process.env.SHOOT_BASE || "https://bainluck.com").replace(/\/+$/, "");
let target;
try {
  target = new URL(BASE);
} catch {
  // A malformed SHOOT_BASE must not fall through to the production default: the
  // operator would get a clean-looking PNG of a surface that does not contain
  // their fix, and read it as their fix failing.
  console.error(`SHOOT_BASE is not a URL: ${JSON.stringify(process.env.SHOOT_BASE)}`);
  process.exit(2);
}
// `new URL("localhost:3000")` SUCCEEDS — protocol `localhost:`, hostname `""` — so the
// commonest typo would slip past the check above, read as NOT local, skip the port
// guard below and be handled as a remote target. Demand a scheme explicitly.
if (target.protocol !== "http:" && target.protocol !== "https:") {
  console.error(`SHOOT_BASE needs an http:// or https:// scheme, got ${JSON.stringify(BASE)}`);
  process.exit(2);
}
const isLocal = target.hostname === "localhost" || target.hostname === "127.0.0.1";

// 🔴 LOCAL TARGETS MUST BE SERVED ON PORT 3000 (ux/1192, #5161). The API's CORS
// allowlist is `http://localhost:3000` + `http://127.0.0.1:3000` and nothing
// else — the only origin regex is for Vercel previews (`backend/app/main.py`).
// A dev server on any other port serves the PAGE fine and has every
// `/api/events/search` call refused by the browser, so the dropdown renders
// zero rows — and the empty-dropdown refusal at the bottom of this file then
// reads as "the fix is broken" rather than "the page could not reach the API".
// Refuse here, before the browser starts, or the next operator debugs the
// wrong layer for an hour.
if (isLocal && target.port !== "3000") {
  console.error(
    `SHOOT_BASE port is ${target.port || "(default)"} — the API CORS allowlist names :3000 only, so the ` +
      `dropdown would render 0 rows for a CORS reason, not a product one. Serve the frontend on :3000.`,
  );
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ["--no-sandbox", "--single-process", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage"];
// 🔴 `<-loopback>` DOES NOT MEAN "BYPASS LOOPBACK" (ux/1192, #5161). It SUBTRACTS
// Chrome's implicit loopback bypass, i.e. forces local traffic THROUGH the
// corporate proxy. That is right for a production target — the page itself is
// remote and the sandbox can only reach it via the proxy — and fatal for a local
// one: the page half-loads, the mobile trigger reads invisible, the rig silently
// takes the DESKTOP branch and dies 30 s later on a hidden input. Two runs were
// lost to it. The fix is not "no proxy" — a local page still calls the REMOTE
// API — it is the proxy WITH loopback going direct.
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push(isLocal ? "--proxy-bypass-list=localhost;127.0.0.1" : "--proxy-bypass-list=<-loopback>");
}

const browser = await chromium.launch({ args });
let code = 1;
try {
  const page = await browser.newPage({
    viewport: { width: Number(width), height: 844 },
    deviceScaleFactor: 2,
  });
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });

  const trigger = page.locator(MOBILE_TRIGGER);
  // 🔴 WAIT BEFORE ASKING. `isVisible()` straight after `domcontentloaded` is a
  // race against hydration, and it does not throw — it answers `false`, which
  // sends the rig down the DESKTOP branch, where at 390px the input is hidden
  // and the run dies 30 s later pointing at the wrong element. The first
  // attempt at this shot failed exactly that way.
  await trigger.waitFor({ state: "visible", timeout: 20_000 }).catch(() => null);
  if (await trigger.isVisible().catch(() => false)) {
    await trigger.click();
    await page.locator(INPUT).waitFor({ state: "visible", timeout: 20_000 });
  } else {
    await page.locator(INPUT).click();
  }
  await page.locator(INPUT).fill(query);
  await page.locator(ROW).first().waitFor({ state: "visible", timeout: 25_000 }).catch(() => null);
  await page.waitForTimeout(1500);

  const rows = await page.locator(ROW).count();
  const seasonLines = await page.locator(SEASON).count();
  // `base=` is in the record because a PNG cannot say which surface it is of,
  // and a local shot read as a production one is a false LOOK.
  console.error(
    `base=${BASE} query=${JSON.stringify(query)} width=${width} rows=${rows} season_answer_lines=${seasonLines}`,
  );
  for (const t of await page.locator(ROW).allInnerTexts()) {
    console.error("  · " + t.replace(/\s*\n+\s*/g, " | "));
  }
  // A dropdown with no rows is not a photograph of this ship, and a PNG of an
  // empty page reads as a clean pass to anyone who only checks the file exists.
  if (rows === 0) {
    console.error("no suggestion rows rendered — refusing to write a pass-looking PNG");
    code = 3;
  } else {
    await page.screenshot({ path: out });
    console.error(`wrote ${out}`);
    code = 0;
  }
} finally {
  await browser.close();
}
process.exit(code);
