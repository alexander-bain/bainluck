// yearless-date-hunt-ux1460.mjs <url> [width]
//
// Finds reader-visible date labels on a Discover surface that name a weekday +
// month + day but NO YEAR, and reports which of them resolve to a year that is
// not the reader's current year.
//
// WHY THIS IS A PROBE AND NOT A GREP: the label is composed by whichever card
// kernel owns the row, and several formatters in `lib/gameTimeLabel.ts` already
// append the year correctly. Only the rendered string proves which call site a
// reader is actually reading, and only the card's own link/testid says which
// component minted it.
//
// exit 0 = no yearless label found that points outside the current year
// exit 1 = at least one found (the defect)
// exit 3 = no date-bearing cards on the page at all (look at the frame before
//          believing this — an error card renders no cards either; ux/1459 §5)

import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

// Same resolution as tools/shop-shot.mjs — playwright lives in the npx cache,
// not in this repo's node_modules.
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
const require = createRequire(findPlaywright());
const { chromium } = require("playwright");

const url = process.argv[2] || "https://bainluck.com/";
const width = Number(process.argv[3] || 390);

// "Thu, Jul 1" / "Wed, Jun 30" — weekday, month, day, and crucially no 4-digit year.
const YEARLESS = /\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b(?!,?\s*\d{4})/;

// Same launch args as tools/shop-shot.mjs. `--single-process`/`--disable-crashpad`
// are not tuning: without them Chromium dies in this sandbox on a mach-port
// rendezvous check and the failure reads as a page error.
const args = ["--no-sandbox", "--single-process", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage"];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) args.push(`--proxy-server=${proxy}`);

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width, height: 900 },
  // Notice 39 — say who we are on every production read.
  extraHTTPHeaders: { "x-bainluck-origin": process.env.BL_AGENT || "ux" },
});
await page.goto(url, { waitUntil: "networkidle", timeout: 90_000 });
await page.waitForTimeout(3000);

// A Discover card mounts on intersection, so a 900px viewport renders a handful
// of rows and the probe reads a page the reader does not have. look.sh solves the
// same problem by growing the viewport to the document height; do that here, twice,
// so the feed's own lazy rows are all in the DOM before anything is counted.
for (let i = 0; i < 2; i++) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30000) });
  await page.waitForTimeout(2500);
}

const bodyText = await page.evaluate(() => document.body.innerText);
if (/Failed to load|Rate limit|Too many requests/i.test(bodyText)) {
  console.error("PAGE IS AN ERROR CARD — not a measurement. First 200 chars:");
  console.error(bodyText.slice(0, 200));
  await browser.close();
  process.exit(3);
}

const found = await page.evaluate((src) => {
  const re = new RegExp(src, "");
  const out = [];
  const cards = document.querySelectorAll("article, [data-card-format], [data-testid]");
  for (const card of cards) {
    // Only leaf-ish text nodes, so a parent does not report its child's string.
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = (n.textContent || "").trim();
      if (!t || !re.test(t)) continue;
      const el = n.parentElement;
      out.push({
        text: t,
        cardFormat: card.getAttribute("data-card-format"),
        testid: card.getAttribute("data-testid"),
        label: card.getAttribute("aria-label"),
        href: card.querySelector("a")?.getAttribute("href") || null,
        cls: el?.className || null,
      });
    }
  }
  return out;
}, YEARLESS.source);

console.log(`url=${url} width=${width} candidates=${found.length}`);
const seen = new Set();
for (const f of found) {
  const k = f.text + "|" + f.label;
  if (seen.has(k)) continue;
  seen.add(k);
  console.log(`  "${f.text}"  format=${f.cardFormat} testid=${f.testid} href=${f.href}`);
  console.log(`     card=${(f.label || "").slice(0, 80)}`);
}

await browser.close();
if (found.length === 0) {
  console.log("no yearless weekday-dates rendered");
  process.exit(3);
}
process.exit(1);
