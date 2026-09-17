// progression-col-fit-6722.mjs — where do the progression grid's columns actually land? (#6722)
//
// The screenshot says "36 nameless bars" at 390px and the same page is correct at 1280px. A
// screenshot cannot grade an ALLOCATION claim, so this reads the layout engine instead:
//
//   * the scroll container's clientWidth / scrollWidth        -> how much is off-screen, and why
//   * each <th>'s client rect, in CONTAINER coordinates       -> which header crosses the clip edge
//   * the same for one body row's <td>s                       -> the numbers a reader can actually see
//   * the table's resolved `min-width`                        -> the constant that sets the floor
//
// A column is reported VISIBLE only when its whole box is inside the container's client box at
// scrollLeft 0 — the reader has not scrolled, and a column whose left edge is inside while its
// text is not is exactly the defect being measured.
//
// Usage: node progression-col-fit-6722.mjs <url> [widthPx]
//
// ═══ WHAT IT ANSWERED, 2026-09-17 (ux/1312) ═══
//
// Run across the fleet at 390px (scroller clientW=350), it named the cause, and the cause is one
// step back from the filing's "the single-column case keeps the wide Team column":
//
//     grid  cols  tableW  Team   first data col  row-1 numbers visible
//     nfl    4     542    148px  x=199           2 of 4
//     epl    3     500    182px  x=242           1 of 3
//     mls    2     500    211px  x=271           1 of 2
//     ucl    1     500    285px  x=345           0 of 1
//
// `min-w-[500px]` forced 500px into a 350px scroller. `table-layout: auto` splits a table's
// SURPLUS across columns in proportion to their existing widths, and the sticky Team column is
// always the widest, so it took the lion's share: +34px at three columns, +137px at one, over a
// natural width of 148px. The fix was to delete the floor, not to narrow a column — a floor on
// the TABLE is a floor on the widest CELL. Full reasoning and the rejected alternative live in
// the component comment and in
// `frontend/__tests__/components/progressionTableNoFixedWidthFloor6722.test.tsx`.
//
// Kept because it is the instrument, not the answer: it re-measures any grid at any width, and
// the next allocation question on this table should be put to it rather than to a screenshot.
// (It was written once at 02:31 and rebuilt from scratch at 14:10 by the next session in the same
// lane, because it was left untracked. That is why it is committed.)
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

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
if (!url) { console.error('usage: progression-col-fit-6722.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 40)); }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1500);

const out = await page.evaluate(() => {
  const r1 = (n) => Math.round(n * 10) / 10;
  // The grid is the table that carries the rank header "#" — selected structurally, never by the
  // min-width class, which is the defect's own value and would not survive the fix.
  const table = [...document.querySelectorAll('table')].find(
    (t) => (t.querySelector('thead th')?.textContent || '').trim() === '#',
  );
  if (!table) return { found: false };
  const scroller = table.closest('[class*="overflow-x-auto"]') || table.parentElement;
  const sb = scroller.getBoundingClientRect();
  const cs = getComputedStyle(table);

  const box = (el) => {
    const b = el.getBoundingClientRect();
    return { left: r1(b.left - sb.left), right: r1(b.right - sb.left), w: r1(b.width) };
  };
  const visible = (bx) => bx.left >= -0.5 && bx.right <= sb.width + 0.5;

  const ths = [...table.querySelectorAll('thead th')].map((th) => {
    const bx = box(th);
    return { text: (th.textContent || '').trim().slice(0, 24) || '(blank)', ...bx, visible: visible(bx) };
  });
  const row = table.querySelector('tbody tr');
  const tds = row ? [...row.querySelectorAll('td')].map((td) => {
    const bx = box(td);
    return { text: (td.textContent || '').trim().slice(0, 24) || '(blank)', ...bx, visible: visible(bx) };
  }) : [];

  return {
    found: true,
    viewport: window.innerWidth,
    scroller: { clientWidth: r1(scroller.clientWidth), scrollWidth: r1(scroller.scrollWidth), overflow: r1(scroller.scrollWidth - scroller.clientWidth) },
    table: { minWidth: cs.minWidth, width: r1(table.getBoundingClientRect().width), layout: cs.tableLayout },
    stageColumns: ths.length - 2,
    headers: ths,
    firstRow: tds,
  };
});
console.log(JSON.stringify(out, null, 1));
await browser.close();
