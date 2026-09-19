/**
 * Do the Division Race columns LINE UP, row to row? (#7023)
 *
 * Every line of that table — the header and each team row — is its own grid box,
 * because a row carries its own background and accent. The column template used
 * to be declared on each line separately, and `max-content` is resolved PER grid
 * container: a row with a long team name resolved a wider name track than a row
 * with a short one, and every number column after it slid right. Measured on
 * production 2026-09-18: four `%` columns at four different x positions, 18px
 * apart at 390px and 50px at 1280px, with the header labels sitting 18px left of
 * the numbers they label.
 *
 * A screenshot can suggest that; only the DOM can say it. This prints the right
 * edge of every cell of every line and fails when a column's right edges differ.
 *
 * Usage: [VW=390] [BYPASS=localhost,127.0.0.1] node tools/ux1351-divrace-column-alignment-7023.mjs <url> [...]
 *   exit 0  every column is a column
 *   exit 3  at least one column zig-zags
 *   exit 4  NO TABLE WAS FOUND — nothing was checked. NOT a pass.
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

const urls = process.argv.slice(2);
if (urls.length === 0) {
  console.error("usage: node tools/ux1351-divrace-column-alignment-7023.mjs <url> [...]");
  process.exit(2);
}

const args = ["--single-process", "--no-sandbox"];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
// `<-loopback>` sends localhost THROUGH the proxy — right for production, fatal
// for a local build (every request dies, the page is empty, and the probe reports
// exit 4 on a page it never saw). Local build: BYPASS="localhost,127.0.0.1".
if (proxy)
  args.push(`--proxy-server=${proxy}`, `--proxy-bypass-list=${process.env.BYPASS || "<-loopback>"}`);

const VW = Number(process.env.VW || 390);
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: VW, height: 844 }, deviceScaleFactor: 2 });

let found = 0;
let misaligned = 0;

for (const url of urls) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  // The section streams in below the fold.
  await page.waitForTimeout(2500);

  const r = await page.evaluate(() => {
    const h2 = [...document.querySelectorAll("h2")].find((h) =>
      /^Division Race ·/.test((h.textContent || "").trim()),
    );
    if (!h2) return { found: false };
    const section = h2.closest("section");
    // `[data-divrace-table]` is the stable hook; `.min-w-[360px]` is the pre-fix
    // markup, kept so this probe can still measure the defect on an old build.
    const inner =
      section?.querySelector("[data-divrace-table]") ?? section?.querySelector(".min-w-\\[360px\\]");
    if (!inner) return { found: false };
    const left = inner.getBoundingClientRect().left;
    return {
      found: true,
      label: (h2.textContent || "").trim(),
      lines: [...inner.children].map((line) => ({
        tracks: getComputedStyle(line).gridTemplateColumns,
        cells: [...line.children].map((c) => ({
          text: (c.textContent || "").trim().slice(0, 22),
          right: Math.round(c.getBoundingClientRect().right - left),
        })),
      })),
    };
  });

  if (!r.found) {
    console.log(`NO TABLE  ${url}`);
    continue;
  }
  found++;
  console.log(`\n=== ${r.label}  @${VW}px\n    ${url}`);
  for (const line of r.lines) {
    console.log(`    ${line.cells.map((c) => `${JSON.stringify(c.text)}@${c.right}`).join("  ")}`);
  }
  // The last cell of each line is the trailing spacer; compare the data columns.
  const width = Math.max(...r.lines.map((l) => l.cells.length));
  let bad = 0;
  for (let i = 1; i < width; i++) {
    const rights = r.lines.map((l) => l.cells[i]?.right).filter((x) => x != null);
    if (rights.length < 2) continue;
    const min = Math.min(...rights);
    const max = Math.max(...rights);
    if (max - min > 1) bad++;
    console.log(
      `  column ${i}: right edges span ${min}..${max}  ${max - min > 1 ? `MISALIGNED by ${max - min}px` : "aligned"}`,
    );
  }
  if (bad > 0) misaligned++;
}

await browser.close();
console.log(`\n${misaligned} of ${found} tables have at least one misaligned column`);
process.exit(found === 0 ? 4 : misaligned > 0 ? 3 : 0);
