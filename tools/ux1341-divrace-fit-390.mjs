/**
 * Does the Division Race table FIT the card at 390px, or is the last column cut?
 *
 * A screenshot shows a clipped `%` and cannot say whether that is the camera,
 * the downscale, or the product (ux/1324: "mostly the camera"; ux/1340: judge
 * small type from a viewport shot, never off a whole-page downscale). So this
 * asks the DOM instead: for the scroll container that holds the table, compare
 * `scrollWidth` to `clientWidth`, and measure the right edge of the LAST cell
 * in the first data row against the container's own right edge.
 *
 * overflow > 0 means content a reader cannot see without swiping; the cut
 * glyph in the frame is then the product, not the lens.
 *
 * Usage: node tools/ux1341-divrace-fit-390.mjs <url> [<url> ...]
 */
// Playwright lives in the npx cache, not in this tree — same shim as ux/1340's
// probe. A bare `import "playwright"` is ERR_MODULE_NOT_FOUND, which reads as
// "the tool is broken" rather than "resolve it where it actually is".
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

const urls = process.argv.slice(2);
if (urls.length === 0) {
  console.error("usage: node tools/ux1341-divrace-fit-390.mjs <url> [...]");
  process.exit(2);
}

// 🪤 --single-process chromium dies on the first page.close() (ux/1340), so one
// page is reused for every url rather than a newPage-per-url loop.
const args = ["--single-process", "--no-sandbox"];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) args.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});

let overflowing = 0;
let found = 0;

for (const url of urls) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  // The section streams in below the fold.
  await page.waitForTimeout(2500);

  const r = await page.evaluate(() => {
    // 🪤 The section is a CSS GRID, not a `<table>`. A detector that asks for a
    // table reports "subject missing" on a page that is drawing the defect —
    // the same class as a probe keyed on the markup it expects to find.
    // Anchors are TeamDivisionRace.tsx's own: `h2` → `section` →
    // `.min-w-[360px]` inside an `overflow-x-auto` card.
    const h2 = [...document.querySelectorAll("h2")].find((h) =>
      /^Division Race ·/.test((h.textContent || "").trim()),
    );
    if (!h2) return { found: false };
    const section = h2.closest("section");
    const inner = section?.querySelector(".min-w-\\[360px\\]");
    if (!inner) return { found: false };
    const scroller = inner.parentElement; // the overflow-x-auto card

    const lines = [...inner.children];
    const header = lines[0];
    const firstRow = lines[1];
    const cells = firstRow ? [...firstRow.children] : [];
    const last = cells[cells.length - 1];
    const headButtons = [...(header?.querySelectorAll("button") || [])];

    return {
      found: true,
      label: (h2.textContent || "").trim(),
      scrollWidth: scroller.scrollWidth,
      clientWidth: scroller.clientWidth,
      innerWidth: Math.round(inner.getBoundingClientRect().width),
      lastColumn: (headButtons[headButtons.length - 1]?.textContent || "")
        .replace(/[↓\s]+$/, "")
        .trim(),
      lastCellText: (last?.textContent || "").trim(),
      lastCellRight: last ? Math.round(last.getBoundingClientRect().right) : null,
      scrollerRight: Math.round(scroller.getBoundingClientRect().right),
      firstCellText: (cells[0]?.textContent || "").trim(),
    };
  });

  if (!r.found) {
    console.log(`NO SECTION  ${url}`);
    continue;
  }
  found++;
  const overflow = r.scrollWidth - r.clientWidth;
  const cut = r.lastCellRight != null ? r.lastCellRight - r.scrollerRight : 0;
  const verdict = overflow > 0 ? "OVERFLOWS" : "fits";
  if (overflow > 0) overflowing++;
  console.log(
    `${verdict.padEnd(10)} scrollWidth=${r.scrollWidth} clientWidth=${r.clientWidth} ` +
      `overflow=${overflow}px  lastCol=${JSON.stringify(r.lastColumn)} ` +
      `cell=${JSON.stringify(r.lastCellText)} cellRight-scrollerRight=${cut}px  ` +
      `firstCell=${JSON.stringify(r.firstCellText)}\n           ${url}`,
  );
}

await browser.close();
console.log(`\n${overflowing} of ${found} sections overflow their card at 390px`);
process.exit(found === 0 ? 4 : overflowing > 0 ? 3 : 0);
