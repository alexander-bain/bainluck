// ux1340-division-race-pool-6992.mjs <url> [outPng]
//
// #6992 — does a team page's DIVISION RACE count over the pool its heading names?
//
// The section is rendered BELOW a streaming boundary: `curl` of the team page
// returns 200 with the string "Division Race" nowhere in it, so a text check over
// served HTML reads every page as clean (the ux/1325 trap, in its quietest form —
// the instrument reports agreement because it is blind, not because the page is
// right). This drives a real browser and reads the rendered rows.
//
// SUBJECT DETECTION IS KEYED ON THE HEADING, NOT ON THE DEFECT. The section is
// found by its `Division Race ·` <h2>; if that heading is absent the probe exits 4
// (SUBJECT MISSING) and never 0, so a page that stopped rendering the race at all
// can never read as a fix.
//
// WHAT IT MEASURES, per page:
//   ROWS     how many teams the race lists
//   LEADERS  how many of them are over 50% in the DIVISION column
//   DIVSUM   what the DIVISION column sums to
// A division is won by exactly one team, so the honest shape is one leader and a
// sum near 100%. Two leaders and ~200% is two races stacked into one column.
//
// EXIT CODES ARE A STORY (gotcha #124):
//   0  every page counted over one pool (<=1 leader AND DIVSUM <= 130%)
//   3  at least one page stacked two races  <- the defect
//   4  the heading was not found on some page (subject missing; NOT a pass)
//   2  usage        1  camera/navigation
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');

const urls = process.argv.slice(2).filter((a) => a.startsWith('http'));
const outPng = process.argv.slice(2).find((a) => a.endsWith('.png')) || null;
if (!urls.length) {
  console.error('usage: node ux1340-division-race-pool-6992.mjs <url> [<url>...] [out.png]');
  process.exit(2);
}

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
// ONE page, navigated per url. `--single-process` chromium tears the whole browser
// down with the first `page.close()`, so a newPage-per-url loop dies on url #2 with
// "Target page, context or browser has been closed" — which looks like a site fault.
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});
let worst = 0;

for (const url of urls) {
  {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    // The race streams in; wait for its heading rather than a fixed sleep.
    await page
      .locator('h2', { hasText: /^Division Race ·/ })
      .first()
      .waitFor({ state: 'attached', timeout: 30000 })
      .catch(() => {});

    const read = await page.evaluate(() => {
      const h2 = [...document.querySelectorAll('h2')].find((h) =>
        /^Division Race ·/.test((h.textContent || '').trim()),
      );
      if (!h2) return null;
      const section = h2.closest('section');
      const card = section?.querySelector('.min-w-\\[360px\\]') || section;
      const lines = [...card.children];
      if (lines.length < 2) return { label: h2.textContent.trim(), rows: [], cols: [] };
      // First line is the header row: "Team" then one button per shown column.
      const cols = [...lines[0].querySelectorAll('button')].map((b) =>
        (b.textContent || '').replace(/[↓\s]+$/, '').trim(),
      );
      const rows = lines.slice(1).map((r) => {
        const cells = [...r.children];
        return {
          name: (cells[0]?.textContent || '').trim(),
          values: cells.slice(1).map((c) => (c.textContent || '').trim()),
        };
      });
      return { label: (h2.textContent || '').trim(), cols, rows };
    });

    if (!read) {
      console.log(`SUBJECT MISSING  ${url}  (no "Division Race ·" heading)`);
      worst = Math.max(worst, 4);
      continue;
    }

    const di = read.cols.indexOf('Division');
    const num = (s) => (/^\d+%$/.test(s) ? Number(s.slice(0, -1)) : null);
    const divs = di < 0 ? [] : read.rows.map((r) => num(r.values[di])).filter((v) => v !== null);
    const sum = divs.reduce((a, b) => a + b, 0);
    const leaders = read.rows.filter((r) => di >= 0 && (num(r.values[di]) ?? 0) > 50);
    const bad = leaders.length > 1 || sum > 130;

    console.log(
      `${bad ? 'STACKED ' : 'ONE POOL'}  ${read.label.replace(/\s+/g, ' ')}  ` +
        `ROWS=${read.rows.length} LEADERS=${leaders.length} DIVSUM=${sum.toFixed(1)}%  ${url}`,
    );
    for (const r of read.rows) console.log(`      ${r.name.padEnd(26)} ${r.values.join('  ')}`);
    if (leaders.length > 1) {
      console.log(`      two leaders: ${leaders.map((l) => l.name).join(' + ')}`);
    }
    if (bad) worst = Math.max(worst, 3);

    if (outPng && url === urls[0]) {
      const h2 = page.locator('h2', { hasText: /^Division Race ·/ }).first();
      const box = await h2.boundingBox();
      if (box) {
        await page.evaluate((y) => window.scrollTo(0, y), Math.max(0, box.y - 60));
        await page.waitForTimeout(400);
        await page.screenshot({ path: outPng });
        console.log(`shot ${outPng} at scrollY=${Math.max(0, Math.round(box.y - 60))}`);
      }
    }
  }
}

await browser.close();
process.exit(worst);
