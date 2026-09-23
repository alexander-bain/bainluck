/**
 * #8147 after-check — reads THE SCRIPT's blurb out of the LIVE DOM.
 *
 * A PNG is judged by eye; this is the text receipt beside it. It asserts BOTH
 * directions on purpose: the new sentence present AND the old one absent, so a
 * page that renders neither (a blank section, a failed hydrate, a wrong URL)
 * cannot read as a pass the way a single `not.toContain` would.
 *
 * Usage: node script-blurb-8147.mjs <url> [width]
 * exit 0 = present tense served · 3 = past tense still served · 4 = no props
 * section found at all (neither sentence) · 1 = the camera/page failed.
 */
import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

// Playwright lives in the npx cache, not in a node_modules beside this file —
// the same resolution shop-shot.mjs uses. A bare `import "playwright"` throws
// ERR_MODULE_NOT_FOUND here, which exits 1 (the camera code), so the contract
// below still refuses to read as a pass; this just makes it run.
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  throw new Error("playwright not found in the npx cache — run tools/look.sh once to warm it");
}
const { chromium } = createRequire(findPlaywright())("playwright");

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
const NEW = "What the market expects before the event";
const OLD = "What the market expected before the event";

// The sandbox kills a default multi-process launch (`bootstrap_check_in …
// Permission denied (1100)`) and the browser does not inherit the session
// egress proxy. Both args are shop-shot.mjs's, for the same two reasons —
// this probe is a text read of the same page look.sh photographs, so it has
// to reach production the same way.
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy || "";
const args = ["--single-process", "--no-sandbox"];
if (proxy) { args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>"); }
const browser = await chromium.launch({ args });
try {
  const page = await browser.newPage({ viewport: { width, height: 844 } });
  const resp = await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  console.log(`HTTP ${resp?.status()}  ${url}  @${width}px`);

  const text = (await page.locator("body").innerText()).replace(/\s+/g, " ");
  const hasNew = text.includes(NEW);
  const hasOld = text.includes(OLD);

  // The surrounding chrome, quoted, so the receipt proves WHICH page this is
  // and what state it was in — a blurb with no badge beside it is unreadable
  // as evidence six months from now.
  const badge = (text.match(/GOLF\s+(UPCOMING|LIVE|FINAL|SETTLED)[^·]*?(STARTS IN [^A-Z]*)?/i) || [])[0];
  const eyebrow = (text.match(/THE SCRIPT[^.]*\./i) || [])[0];

  console.log(`  badge   : ${badge ? badge.trim() : "(none found)"}`);
  console.log(`  section : ${eyebrow ? eyebrow.trim() : "(none found)"}`);
  console.log(`  expects : ${hasNew}`);
  console.log(`  expected: ${hasOld}`);

  if (hasOld) { console.log("RESULT: PAST TENSE STILL SERVED"); process.exit(3); }
  if (!hasNew) { console.log("RESULT: NEITHER SENTENCE — no props section on this page"); process.exit(4); }
  console.log("RESULT: present tense served");
  process.exit(0);
} catch (e) {
  console.log(`CAMERA/PAGE FAILED: ${e.message}`);
  process.exit(1);
} finally {
  await browser.close();
}
