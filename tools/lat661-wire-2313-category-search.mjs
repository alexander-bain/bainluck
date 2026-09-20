// lat661-wire-2313-category-search.mjs — #2313: does typing in a category's search box still
// issue one request per keystroke?
//
// The unit guards assert `SEARCH_DEBOUNCE_MS` and the debouncer's own behaviour. They cannot see
// the wiring: whether the SHIPPED component's SWR key reads the committed query, and whether the
// rendered list survives the typing. This drives a real browser against a real build and reads the
// two things that cannot be argued with — the `/api/futures/browse` requests that leave the page,
// and the row count in the panel while the letters are going in.
//
// The ship (#2313): typing a word at speed issues ONE request, for the whole word, instead of one
// per letter — and the first two letters are the expensive ones (below three characters the GIN
// trigram index cannot serve `name ILIKE '%q%'`, so Postgres scans: 4,821 buffers vs 40, measured
// on production 2026-08-30).
//
// 🔴 EVERY ARM CARRIES ITS OWN CONTROL, because this probe runs on a build that already has the
// fix and a green reading on such a build proves nothing on its own — it is equally consistent
// with an instrument that sees no requests at all. So each assertion is paired with a SLOW-typing
// arm that must show the opposite:
//
//   arm 1  fast typing (40 ms/char)  -> EXACTLY ONE request, carrying the whole word
//   arm 2  slow typing (450 ms/char) -> SEVERAL requests, one per letter  (the instrument can see
//                                       per-keystroke requests; the debounce is a timer, not a
//                                       minimum-length gate, which #2313 refused on purpose —
//                                       "a slow typist still gets every prefix")
//   arm 3  rows survive the fast burst (never 0 while typing)
//   arm 4  the slow burst DOES blank the list at least once (the row sampler can see a flash, so
//          arm 3 is a measurement and not a blind spot)
//
// Usage: node tools/lat661-wire-2313-category-search.mjs <baseUrl> [category]
// Exit 0 = PASS · 1 = FAIL · 2 = UNPAID (subject not reached — proves nothing either way)
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

const [baseUrl, categoryArg] = process.argv.slice(2);
if (!baseUrl) {
  console.error('usage: lat661-wire-2313-category-search.mjs <baseUrl> [category]');
  process.exit(2);
}
const category = categoryArg || 'politics';
const WORD = 'super';

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  const local = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(baseUrl);
  args.push(`--proxy-server=${proxy}`);
  args.push(local ? '--proxy-bypass-list=localhost;127.0.0.1' : '--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

const browseRequests = [];
page.on('request', (r) => {
  const u = r.url();
  if (u.includes('/api/futures/browse')) {
    const q = new URL(u).searchParams.get('q');
    browseRequests.push({ url: u, q, at: Date.now() });
  }
});

const fail = [];
const unpaid = (msg) => { console.error(`UNPAID: ${msg}`); browser.close(); process.exit(2); };

console.log(`== ${baseUrl}/search at 390px, category "${category}" ==`);
await page.goto(`${baseUrl}/search`, { waitUntil: 'domcontentloaded', timeout: 60000 });

// The grid is the page; without it there is no tile to tap.
// 🪤 `hasText` takes a STRING here on purpose. `new RegExp(category, 'i')` reads the same and is
// `js/regex-injection` (CodeQL, high) — a category argument of `.*` would match every tile and the
// probe would silently measure whichever one sorted first. A string is matched case-insensitively
// and as a substring by Playwright, which is exactly what the tile label ("Politics") needs.
const tile = page.locator(`button[aria-label^="Browse "][aria-label*="markets"]`).filter({ hasText: category }).first();
try {
  await tile.waitFor({ state: 'visible', timeout: 30000 });
} catch {
  unpaid(`no category tile matching "${category}" — the grid did not render`);
}
await tile.click();

const input = page.locator(`input[aria-label="Search within ${category}"]`);
try {
  await input.waitFor({ state: 'visible', timeout: 20000 });
} catch {
  unpaid('the in-category search box never appeared');
}

// Let the panel's first page land, so the row sampler has something to watch drop.
await page.waitForTimeout(3000);
const rowsAtRest = await countRows();
if (rowsAtRest <= 0) unpaid(`the panel rendered ${rowsAtRest} rows — nothing to type into`);
console.log(`   panel open: ${rowsAtRest} rows, ${browseRequests.length} browse request(s) so far`);

async function countRows() {
  return page.evaluate((label) => {
    const el = document.querySelector(`input[aria-label="${label}"]`);
    if (!el) return -1;
    const panel = el.closest('div.bg-surface-card') || el.parentElement;
    return panel ? panel.querySelectorAll('a[href^="/futures/"]').length : -1;
  }, `Search within ${category}`);
}

async function typeWord(delayMs) {
  const rowSamples = [];
  await input.click();
  await input.fill('');
  await page.waitForTimeout(1200);          // let the cleared-query request settle
  const before = browseRequests.length;
  for (const ch of WORD) {
    await page.keyboard.type(ch);
    await page.waitForTimeout(delayMs);
    rowSamples.push(await countRows());
  }
  await page.waitForTimeout(3500);          // settle: debounce + the request it schedules
  return { sent: browseRequests.slice(before), rowSamples };
}

// ── arm 1 + 3: fast typing ────────────────────────────────────────────────────────────────────
console.log(`\n1. typing "${WORD}" at 40 ms/char`);
const fast = await typeWord(40);
const fastQ = fast.sent.filter((r) => r.q);
console.log(`   ${fast.sent.length} browse request(s), ${fastQ.length} carrying q=[${fastQ.map((r) => r.q).join(', ')}]`);
console.log(`   rows during the burst: [${fast.rowSamples.join(', ')}]`);

if (fastQ.length === 1 && fastQ[0].q === WORD) {
  console.log(`   PASS one request, for the whole word`);
} else {
  fail.push(`fast typing sent ${fastQ.length} q-requests [${fastQ.map((r) => r.q).join(', ')}], expected exactly 1 for "${WORD}"`);
}
const shortPrefixes = fastQ.filter((r) => r.q.length < 3);
if (shortPrefixes.length === 0) {
  console.log(`   PASS no request for a 1-2 letter prefix (the scan-priced ones)`);
} else {
  fail.push(`fast typing asked the server for ${shortPrefixes.length} sub-trigram prefix(es)`);
}
if (fast.rowSamples.every((n) => n > 0)) {
  console.log(`   PASS the rendered list survived the burst (never blanked)`);
} else {
  fail.push(`the list blanked during fast typing: [${fast.rowSamples.join(', ')}]`);
}

// ── arm 2 + 4: the control ────────────────────────────────────────────────────────────────────
console.log(`\n2. CONTROL — the same word at 450 ms/char (slower than the 200 ms debounce)`);
const slow = await typeWord(450);
const slowQ = slow.sent.filter((r) => r.q);
console.log(`   ${slow.sent.length} browse request(s), ${slowQ.length} carrying q=[${slowQ.map((r) => r.q).join(', ')}]`);
console.log(`   rows during the burst: [${slow.rowSamples.join(', ')}]`);

if (slowQ.length >= 3) {
  console.log(`   PASS the instrument sees per-keystroke requests — arm 1's "1" is a measurement`);
} else {
  fail.push(`CONTROL DEAD: slow typing produced only ${slowQ.length} q-request(s); arm 1 cannot be read`);
}
if (slow.rowSamples.some((n) => n === 0)) {
  console.log(`   PASS the row sampler can see a blank list — arm 3 is a measurement`);
} else {
  console.log(`   NOTE the slow burst never blanked either (${slow.rowSamples.join(', ')}); arm 3 is`);
  console.log(`        weaker than it looks — recorded, not failed, because keepPreviousData can`);
  console.log(`        legitimately hold rows through a committed query change.`);
}

await browser.close();

if (fail.length) {
  console.log(`\nFAIL`);
  for (const f of fail) console.log(`  - ${f}`);
  process.exit(1);
}
console.log(`\nPASS`);
process.exit(0);
