// ungraded-verdict-shot-4788.mjs — render the #4788 fix against the specimen's REAL grading state.
//
// Why this exists rather than a plain production LOOK: the fix is deliberately
// FAIL-OPEN on an ABSENT `resolution_source` (Vercel deploys ahead of Heroku, so the
// new bundle must not blank every verdict on the site while the old payload is still
// being served — see `outcomeRowVerdict`). Production has not shipped the serialiser
// half yet, so a local build pointed at the live API renders the OLD page, correctly.
//
// So: run the LOCAL build, intercept the market's own API call, and inject exactly what
// the database says — `POST /api/admin/db-query` on 2026-09-10 returns, for market
// 59700266, `(is_winner=false, resolution_source=NULL) x 24` and `(NULL, NULL) x 51`,
// i.e. NOBODY graded that market. Injecting `resolution_source: null` on every outcome
// is therefore not a convenient fiction; it is the row state the fixed serialiser will
// send once it deploys.
//
// The `before` arm deletes the key instead, which is what the current serialiser sends.
// One page, one code path, one difference — the field.
//
// The payload is served from a FILE captured once with curl, not re-fetched per arm:
// this sandbox denies Playwright direct egress (`route.fetch` -> EPERM), and serving one
// captured body to both arms is better evidence anyway — the two pictures then differ by
// the injected field and by nothing else, not even a re-poll of a moving price.
// Capture it with:
//   source ~/.claude/.env && curl -s "$BAINLUCK_API/api/futures/59700266" -o payload.json
//
// Usage: node tools/ungraded-verdict-shot-4788.mjs <base> <marketId> <before|after> <out.png> <payload.json> [scrollPx]
import { createRequire } from 'module';
import { existsSync, readdirSync, readFileSync } from 'fs';

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

const [base, marketId, arm, out, payloadPath, scrollPx] = process.argv.slice(2);
if (!base || !marketId || !arm || !out || !payloadPath) {
  console.error('usage: <base> <marketId> <before|after> <out.png> <payload.json> [scrollPx]');
  process.exit(2);
}
// Every API call the page makes, captured with curl into a fixture dir keyed by
// `path?query` (see the sibling capture step). Serving ALL of them — not just the
// market — is what makes this a real page: stubbing the others with `{}` tripped the
// page's error boundary and rendered "Something went wrong", i.e. zero rows on both
// arms again.
const fixtureDir = payloadPath;
const index = JSON.parse(readFileSync(`${fixtureDir}/index.json`, 'utf8'));
const MARKET_PATH = `/api/futures/${marketId}`;

const browser = await chromium.launch({
  args: ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-dev-shm-usage'],
});
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

let patched = 0;
// ONE handler for every API call. Two handlers is the trap: Playwright matches the
// MOST RECENTLY registered route first, so a catch-all added second silently swallows
// the specific route added first — which is exactly how the first run of this script
// reported `patchedOutcomes=0` on BOTH arms, i.e. a differential rig that renders
// nothing on either side and reads as a clean diff.
const json200 = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body,
  });

await page.route('**/api.bainluck.com/**', async (route) => {
  const u = new URL(route.request().url());
  const key = index[u.pathname + u.search] ?? index[u.pathname];
  if (!key) {
    console.error('UNFIXTURED ' + u.pathname + u.search);
    return json200(route, '{}');
  }
  const raw = readFileSync(`${fixtureDir}/${key}`, 'utf8');
  if (u.pathname !== MARKET_PATH) return json200(route, raw);

  // The one call under test. The arms differ here and nowhere else.
  const body = JSON.parse(raw);
  for (const o of body.outcomes ?? []) {
    if (arm === 'after') o.resolution_source = null; // what the DB says: ungraded
    else delete o.resolution_source; // what today's serialiser sends
    patched++;
  }
  return json200(route, JSON.stringify(body));
});

await page.goto(`${base}/futures/${marketId}`, { waitUntil: 'networkidle', timeout: 90000 });
// The verdict rows live in the "Final Results" table; wait for the rows themselves.
await page.waitForSelector('[data-testid="outcome-row"]', { timeout: 30000 }).catch(() => {});

// The table opens COLLAPSED at 25 of 75 rows, and the fabricated legs are not all in
// the top 25 by price — a count taken on the collapsed table silently measures a third
// of the market. Expand before counting.
const showAll = page.getByText(/Show all \d+/).first();
if (await showAll.count()) await showAll.click().catch(() => {});
await page.waitForTimeout(1500);

// Count what the page STATES, by text, not by colour class (the fix is allowed to
// change classes). NOT `\bLost\b`: `textContent` concatenates sibling elements with no
// separator, so a row reads "...7+LostOPEN51%..." and the word boundary after "Lost"
// does not exist. That regex reported 0 `Lost` on the arm that was printing them.
const counts = await page.evaluate(() => {
  const rows = [...document.querySelectorAll('[data-testid="outcome-row"]')];
  const txt = (r) => r.textContent || '';
  return {
    rows: rows.length,
    lost: rows.filter((r) => txt(r).includes('Lost')).length,
    won: rows.filter((r) => txt(r).includes('Won')).length,
    settled: rows.filter((r) => txt(r).includes('Settled')).length,
    latest: rows.filter((r) => txt(r).toUpperCase().includes('LATEST')).length,
  };
});
console.error(`arm=${arm} patchedOutcomes=${patched} ${JSON.stringify(counts)}`);

// Removed from the DOM rather than clicked: the click raced the banner's own mount and
// left it sitting over the rows in both arms. Anchored on its heading text, and it drops
// the whole fixed/sticky ancestor, since the visible panel is a parent of that text.
await page.evaluate(() => {
  for (const el of document.querySelectorAll('div,section,aside')) {
    if (!/We value your privacy/i.test(el.textContent || '')) continue;
    let node = el;
    while (node?.parentElement) {
      const pos = getComputedStyle(node).position;
      if (pos === 'fixed' || pos === 'sticky') break;
      node = node.parentElement;
    }
    (node ?? el).remove();
    break;
  }
});

// `rows` = frame the verdict rows themselves, which is the only part of this page the
// change can touch. A fixed pixel offset would drift between the arms the moment a row
// grows or loses a line, and would then be comparing two different parts of the page.
if (scrollPx === 'rows') {
  await page
    .locator('[data-testid="outcome-row"]')
    .first()
    .scrollIntoViewIfNeeded()
    .catch(() => {});
  // Push the first row to the TOP of the frame so the rows below it are in shot;
  // `scrollIntoViewIfNeeded` alone leaves it on the last line of the viewport.
  await page.evaluate(() => window.scrollBy(0, 250));
  await page.waitForTimeout(700);
} else if (scrollPx) {
  await page.evaluate((y) => window.scrollTo(0, y), Number(scrollPx));
  await page.waitForTimeout(600);
}
await page.screenshot({ path: out });
console.log(out);
await browser.close();
