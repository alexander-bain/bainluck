// card-text-for-href.mjs <url> <href-substring> [width]
//
// Prints, for every anchor on a rendered page whose href contains the given
// substring, the text of the CARD THAT OWNS IT — not the anchor's own text.
//
// WHY THIS EXISTS. `tools/yearless-date-hunt-ux1460.mjs` answers "is any date
// label on this page missing its year", and it answers it by ABSENCE: exit 0
// means it found none. That is the right question and the wrong evidence for an
// after-check, because a page whose defective cards have simply LEFT THE FEED
// passes it just as cleanly as a page whose cards were fixed. Paying #8223's
// after-check (ux/1461) needed the other half: the three `/event/ufc/27jul*`
// cards are STILL HERE, and they now read `Sat, Jul 10, 2027`.
//
// So the pairing is: the hunt probe proves no bad label remains, and this proves
// the rows that carried them are still on the page and now say the right thing.
// Both readings come out of one DOM snapshot, so nothing can have changed
// between them.
//
// WHY IT WALKS UP FROM THE ANCHOR. On a Discover card the date is not inside the
// link — the link wraps the title. Reading `a.innerText` returns
// "Manel Kape vs Joshua Van" and no date at all, which reads as "the label is
// gone" when it is one DOM level up. The walk stops at the first ancestor with
// enough text to be the card (60 chars), which on the measured surfaces is the
// card body and not the whole feed.
//
// Example (the ux/1461 after-check, verbatim):
//   node tools/card-text-for-href.mjs https://bainluck.com/ /event/ufc/ 390
//     /event/ufc/27jul01 || MMA Manel Kape 50% Joshua Van 50% Wed, Jun 30, 2027 …
//     /event/ufc/26dec27 || MMA Benoit Saint-Denis 64% Paddy Pimblett 36% Sat, Dec 26 …
//
// exit 0 = at least one matching anchor was found and printed
// exit 3 = the page rendered no anchor matching that href (look at a screenshot
//          before believing it — an error card renders no anchors either, and a
//          lazy feed renders none until the viewport grows; see below)

import { createRequire } from "module";
import { existsSync, readdirSync } from "fs";

// Same resolution as tools/yearless-date-hunt-ux1460.mjs — playwright lives in
// the npx cache, not in this repo's node_modules.
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

const url = process.argv[2];
const hrefPart = process.argv[3];
const width = Number(process.argv[4] || 390);
if (!url || !hrefPart) {
  console.error("usage: card-text-for-href.mjs <url> <href-substring> [width]");
  process.exit(2);
}

// Same launch args as tools/shop-shot.mjs. `--single-process`/`--disable-crashpad`
// are not tuning: without them Chromium dies in this sandbox on a mach-port
// rendezvous check and the failure reads as a page error.
const args = [
  "--no-sandbox",
  "--single-process",
  "--disable-gpu",
  "--disable-crashpad",
  "--disable-dev-shm-usage",
];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) args.push(`--proxy-server=${proxy}`);

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width, height: 900 },
  // Notice 39 — say who we are on every production read.
  extraHTTPHeaders: { "x-bainluck-origin": process.env.BL_AGENT || "ux" },
});
await page.goto(url, { waitUntil: "networkidle", timeout: 90_000 });
await page.waitForTimeout(2500);

// A Discover card mounts on intersection, so a 900px viewport renders a handful
// of rows and the probe reads a page the reader does not have. look.sh solves
// the same problem by growing the viewport to the document height; do that here,
// TWICE, because growing it loads more rows which makes the document taller
// again. Bounded at two so an endless feed cannot hold the camera open.
for (let i = 0; i < 2; i++) {
  const h = await page.evaluate(() => document.body.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30_000) });
  await page.waitForTimeout(2500);
}

const rows = await page.evaluate((needle) => {
  const out = [];
  for (const a of document.querySelectorAll("a[href]")) {
    const href = a.getAttribute("href") || "";
    if (!href.includes(needle)) continue;
    // Walk up to the first ancestor carrying enough text to be the card. Six
    // levels is the fence: past that, a card grid starts returning its siblings.
    let node = a;
    let up = 0;
    while (node && up < 6 && (node.innerText || "").length < 60) {
      node = node.parentElement;
      up++;
    }
    out.push({
      href,
      text: (node?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 240),
    });
  }
  return out;
}, hrefPart);

console.log(`url=${url} href~=${hrefPart} width=${width} matches=${rows.length}`);
for (const r of rows) console.log(`  ${r.href} || ${r.text}`);

await browser.close();
process.exit(rows.length === 0 ? 3 : 0);
