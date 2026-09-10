// grid-name-fit-4558.mjs — why the advancement grid clips player names, measured from the
// layout engine rather than from a screenshot (#4558).
//
// The question a shot cannot answer: WHERE did the name's pixels go? The name cell is
// `avatar + gap + <span class="truncate">name</span> + optional [seed]` inside a
// `minmax(var(--grid-name-w), max-content)` track, and the track sits beside a scroll floor
// (`gridScrollFloorPx`) that can hand it free space. Any of those four can be the short one.
//
// So this reports, per row:
//   trackW      the rendered width of grid track 1 (from gridTemplateColumns, resolved)
//   nameCellW   the name cell's own client box
//   avatarW     what the face takes, including its margin
//   seedW       what the seed badge takes, including its margin
//   textAvail   the truncating span's clientWidth   ← what the name is allowed
//   textWant    the truncating span's scrollWidth   ← what the name asked for
//   short       textWant - textAvail, > 0 == a reader sees an ellipsis
//
// It never selects on `.truncate` (a class the fix removes — a probe keyed on the defect can
// only ever express the FAIL; ux/1165's `a2c32f61`). The name cell is found structurally, by
// `[data-testid="grid-name"]`, and the text span as its widest text-bearing child.
//
// Usage: node grid-name-fit-4558.mjs <url> [widthPx]
// Exit:  0 = no row clips, 1 = at least one row clips, 2 = could not measure.
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
if (!url) { console.error('usage: grid-name-fit-4558.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const local = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])/.test(url);
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  // `<-loopback>` means do NOT bypass the proxy for loopback, which is right for
  // production and fatal for a locally-served pre-merge build: the proxy has
  // never heard of port 4558. Invert it when the URL is local, exactly as
  // `tools/look-local.mjs` does.
  args.push(local ? '--proxy-bypass-list=127.0.0.1;localhost' : '--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });

// A LOCAL BUILD CANNOT REACH THE API, AND THE BYPASS LIST ABOVE IS NOT ENOUGH (#4593).
// Bypassing the proxy for loopback is what makes the local SERVER reachable; it does
// nothing for the page's OWN fetches to `api.bainluck.com`, which this sandbox only
// grants to `curl`. Without this the grid never renders and the tool exits 2 —
// indistinguishable from "wrong URL", which is how it reads as a broken probe rather
// than a missing capability. Same shim as `tools/look-local.mjs`, and deliberately
// scoped to local URLs: a production measurement must stay byte-identical to the one
// the defect was filed with, so no route interception exists on that path at all.
if (local) {
  const { execFileSync } = await import('child_process');
  await page.route('**://api.bainluck.com/**', async (route) => {
    const target = route.request().url();
    let body;
    try {
      // curl, not the browser: this process has the session egress the page does not.
      body = execFileSync('curl', ['-sS', '--max-time', '45', target], {
        maxBuffer: 64 * 1024 * 1024,
        encoding: 'utf8',
      });
    } catch (err) {
      console.error(`  ! upstream failed ${target}: ${err.message}`);
      return route.fulfill({ status: 502, contentType: 'application/json', body: '{}' });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body,
    });
  });
}

// NOT networkidle: a page that polls never idles and `goto` just times out at 90s.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(4000);

// The grid may live behind a tab on the tournament page.
if (!(await page.$('[data-testid="grid-scroller"]'))) {
  for (const label of ['Bracket', 'Draw', 'Advancement']) {
    const tab = await page.$(`text="${label}"`);
    if (tab) { await tab.click().catch(() => {}); await page.waitForTimeout(2500); }
    if (await page.$('[data-testid="grid-scroller"]')) break;
  }
}
try {
  await page.waitForSelector('[data-testid="grid-scroller"]', { timeout: 15000 });
} catch {
  console.error('FATAL: no [data-testid="grid-scroller"] on the page — wrong URL or the grid did not render.');
  await browser.close();
  process.exit(2);
}

const out = await page.evaluate(() => {
  const scroller = document.querySelector('[data-testid="grid-scroller"]');
  const floorBox = scroller.firstElementChild;
  const header = scroller.querySelector('[data-testid="grid-header"]');
  // READ THE TEMPLATE OFF WHOEVER ACTUALLY OWNS THE TRACKS (#4593). Since the grid
  // became one container adopted by subgrid, the header's own computed
  // `grid-template-columns` is the literal word `subgrid` — `parseFloat` turns that
  // into NaN and the tool reported `header name track NaNpx` while measuring a
  // perfectly healthy grid. A NaN is not a defect and must not read as one.
  const trackHolder = scroller.querySelector('[data-testid="grid-tracks"]') || header;
  const headerTemplate = getComputedStyle(header).gridTemplateColumns;
  const subgridded = !/^\d/.test(headerTemplate.trim());
  const template = subgridded ? getComputedStyle(trackHolder).gridTemplateColumns : headerTemplate;
  const tracks = template.split(' ').map((t) => Math.round(parseFloat(t) * 10) / 10);

  const rows = [...scroller.querySelectorAll('[data-testid="grid-row"]')].map((li) => {
    const cell = li.querySelector('[data-testid="grid-name"]');
    const cr = cell.getBoundingClientRect();
    const kids = [...cell.children];
    const isText = (el) => (el.textContent || '').trim().length > 0 && !el.querySelector('img,svg');
    // The name span is the widest text-bearing child that is not the seed badge.
    const seed = kids.find((el) => /^\[\d+\]$/.test((el.textContent || '').trim())) || null;
    const textEls = kids.filter((el) => el !== seed && isText(el));
    const nameEl = textEls.sort((a, b) => b.scrollWidth - a.scrollWidth)[0] || null;
    const avatar = kids.find((el) => el.querySelector('img,svg') || el.tagName === 'IMG') || null;
    const boxOf = (el) => {
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return Math.round((r.width + parseFloat(cs.marginLeft) + parseFloat(cs.marginRight)) * 10) / 10;
    };
    const avail = nameEl ? nameEl.clientWidth : 0;
    const want = nameEl ? nameEl.scrollWidth : 0;
    // How many lines the name actually draws, and where this row's first value
    // column starts — each <li> is its OWN grid container, so a `max-content`
    // name track can resolve to a different width row by row and slide the
    // numbers out of column.
    const lines = nameEl
      ? Math.round(nameEl.getBoundingClientRect().height / parseFloat(getComputedStyle(nameEl).lineHeight))
      : 0;
    const firstValue = li.querySelector('[data-testid="grid-value-cell"]');
    const valueLeft = firstValue
      ? Math.round((firstValue.getBoundingClientRect().left - li.getBoundingClientRect().left) * 10) / 10
      : null;
    return {
      name: (nameEl?.textContent || '').trim(),
      rank: li.dataset.rank ?? null,
      trackW: Math.round(cr.width * 10) / 10,
      lines,
      valueLeft,
      rowH: Math.round(li.getBoundingClientRect().height * 10) / 10,
      avatarW: boxOf(avatar),
      seedW: boxOf(seed),
      textAvail: avail,
      textWant: want,
      short: want - avail,
      overflowHidden: nameEl ? getComputedStyle(nameEl).overflow !== 'visible' : null,
      wraps: nameEl ? getComputedStyle(nameEl).whiteSpace : null,
    };
  });

  // WHERE THE HEADER'S FIRST LABEL STARTS, in the same frame of reference as a row's
  // `valueLeft` (#4593). A column label that does not sit over its own numbers is the
  // same defect as two rows disagreeing, and it was the larger half of it: with the
  // header's name track at 118px and the widest row's at 156.1, `QF` sat 38px left of
  // the QF column. Rows were compared to each other and the header to nothing, so
  // that half was invisible to this tool.
  const firstLabel = header.querySelector('[data-testid="grid-column"]');
  const headerValueLeft = firstLabel
    ? Math.round((firstLabel.getBoundingClientRect().left - header.getBoundingClientRect().left) * 10) / 10
    : null;

  // THE NUMBER `GRID_SCROLL_SNAP` IS TRANSCRIBED FROM (#4593). `scroll-pl-[138px]` is
  // a padding on the SCROLLER, so the only measurement that can confirm or refute it
  // is the first value column's offset from the scroller's own content origin —
  // `valueLeft` above is relative to the ROW, which stops being the same number the
  // moment the horizontal padding moves off the row. Reported so a change that
  // silently desyncs the sticky snap from the layout cannot read as clean.
  const firstRowValue = scroller.querySelector('[data-testid="grid-row"] [data-testid="grid-value-cell"]');
  const sr = scroller.getBoundingClientRect();
  const valueLeftFromScroller = firstRowValue
    ? Math.round((firstRowValue.getBoundingClientRect().left - sr.left + scroller.scrollLeft) * 10) / 10
    : null;

  return {
    viewport: window.innerWidth,
    columns: scroller.querySelectorAll('[data-testid="grid-column"]').length,
    template,
    tracks,
    subgridded,
    headerValueLeft,
    valueLeftFromScroller,
    nameTrack: tracks[0],
    scroller: { client: scroller.clientWidth, scroll: scroller.scrollWidth },
    floorMinWidth: floorBox ? getComputedStyle(floorBox).minWidth : null,
    floorBoxW: floorBox ? Math.round(floorBox.getBoundingClientRect().width * 10) / 10 : null,
    rowNatural: Math.round([...scroller.querySelectorAll('[data-testid="grid-row"]')][0]?.scrollWidth ?? 0),
    rows,
  };
});

const clipped = out.rows.filter((r) => r.short > 0.5);
const lefts = [...new Set(out.rows.map((r) => r.valueLeft))];
console.log(JSON.stringify({ url, ...out, clippedCount: clipped.length, valueLefts: lefts }, null, 2));
console.log(`\n${clipped.length} of ${out.rows.length} name(s) clipped at ${out.viewport}px; header name track ${out.nameTrack}px`);
for (const r of clipped) console.log(`  short ${r.short}px  ${r.textAvail}/${r.textWant}  ${r.name}`);
console.log(
  lefts.length === 1
    ? `columns aligned: every row's first value cell starts at ${lefts[0]}px`
    : `⚠ columns MISALIGNED across rows: first value cell starts at ${lefts.join(' / ')}px`
);
console.log(`first value column sits ${out.valueLeftFromScroller}px from the scroller's origin (GRID_SCROLL_SNAP transcribes this)`);
if (out.headerValueLeft !== null) {
  // Compared against the WIDEST row, because that is the one a `max-content` track
  // resolves to once the tracks are genuinely shared.
  const widest = Math.max(...lefts);
  const gap = Math.round((widest - out.headerValueLeft) * 10) / 10;
  console.log(
    Math.abs(gap) < 0.5
      ? `header aligned: the first column label starts at ${out.headerValueLeft}px, over its own numbers`
      : `⚠ HEADER MISALIGNED: first column label at ${out.headerValueLeft}px but its numbers at ${widest}px (${gap}px out)`
  );
}
console.log(`row heights: ${out.rows.map((r) => `${r.name.split(' ').pop()}=${r.rowH}(${r.lines}L)`).join(' ')}`);
await browser.close();
process.exit(clipped.length > 0 ? 1 : 0);
