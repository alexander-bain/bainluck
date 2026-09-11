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
 *
 * Defaults: query `patriots`, out `dropdown.png`, width `390` (phone). Always
 * shoots production, because that is the only surface a LOOK may be paid on.
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

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ["--no-sandbox", "--single-process", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage"];
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

const browser = await chromium.launch({ args });
let code = 1;
try {
  const page = await browser.newPage({
    viewport: { width: Number(width), height: 844 },
    deviceScaleFactor: 2,
  });
  await page.goto("https://bainluck.com/", { waitUntil: "domcontentloaded" });

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
  console.error(`query=${JSON.stringify(query)} width=${width} rows=${rows} season_answer_lines=${seasonLines}`);
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
