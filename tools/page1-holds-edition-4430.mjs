// page1-holds-edition-4430.mjs — #4430 after-check: does a background tick still yank the
// reader's cards?
//
// 🔴 WHY THIS IS NOT "PARK AND WATCH". The harm is CONDITIONAL on the served ranking changing
// between two ticks, and the feed endpoint is 60 s-cached — ux/1159 measured 0 churn across a
// 90 s window. Watching a quiet feed and seeing nothing move proves nothing at all: it cannot
// tell a fixed client from a broken client that was never provoked.
//
// So this probe MAKES the precondition true against the DEPLOYED bundle. It passes the first
// /api/feed response through untouched (that is the reader's edition), then rewrites every
// subsequent one to be a payload the pre-fix code would visibly obey:
//
//     * page one REVERSED, and
//     * the reader's first card REMOVED.
//
// Pre-fix (`setPage1Items(data.items ?? [])`) the rendered order flips and the first card
// disappears. Post-fix the reader's order and membership are held; only in-place updates land.
//
// Usage: node page1-holds-edition-4430.mjs <url> [waitSeconds]
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
const waitSeconds = Number(process.argv[3] || 150);
if (!url) { console.error('usage: page1-holds-edition-4430.mjs <url> [waitSeconds]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width: 390, height: 900 }, deviceScaleFactor: 2 });

/** The title that exists ONLY in the mutated tick — the proof the tick was consumed. */
const MARKER = 'PROBE-4430 appended card';

let droppedHref = null;
let feedCalls = 0;
let mutatedCalls = 0;
let captured = null; // the first page-one payload, read off the BROWSER's own response

// `route.fetch()` is not usable here: it issues the request from node, and node egress to
// api.bainluck.com is EPERM in this sandbox while the browser's own request goes through fine.
// So the first call is simply continued and its body captured from the response event; every
// later call is fulfilled from that capture, mutated. Nothing is fetched node-side.
page.on('response', async (res) => {
  if (captured || !/\/api\/feed/.test(res.url())) return;
  const body = await res.json().catch(() => null);
  if (body?.items?.length) captured = body;
});

await page.route('**/api/feed*', async (route) => {
  feedCalls += 1;
  // Only page one — a paginated request carries an offset and is not what this is about.
  const isPageOne = !/offset=[1-9]/.test(route.request().url());
  if (feedCalls === 1 || !captured || !isPageOne) return route.continue();
  // Mutation is bisectable on purpose: when the whole thing fails you need to know WHICH of
  // reverse / drop / append the client actually reacted to. MUT=reverse,drop,append (default all).
  const MUT = (process.env.MUT || 'reverse,drop,append').split(',');
  const items = MUT.includes('reverse') ? [...captured.items].reverse() : [...captured.items];
  // Drop the first item that has a CHECKABLE detail link. A `concept` card has no /futures/ href,
  // so dropping whatever happens to be first leaves the ship assertion with nothing to look for.
  let dropped = null;
  if (MUT.includes('drop')) {
    const at = items.findIndex((i) => i?.type === 'futures' && i?.data?.id != null);
    if (at >= 0) [dropped] = items.splice(at, 1);
  }
  droppedHref = dropped ? `/futures/${dropped.data.id}` : null;
  console.log(`  [probe] mutations=${MUT.join('+')} · tick OMITS ${droppedHref} "${(dropped?.data?.name || '').slice(0, 46)}"`);
  console.log(`  [probe] dropped from the tick: type=${dropped?.type} id=${dropped?.data?.id} name=${(dropped?.data?.name || dropped?.headline || '').slice(0, 50)}`);
  // 🔴 THE POSITIVE CONTROL, and the probe is worthless without it. "Nothing moved" is also
  // what you see when the client REFUSED the payload outright (the page gates a tick behind
  // `decision.acceptItems`), so a held order on its own cannot tell a working reconcile from a
  // tick that never landed. The fix appends what is genuinely new, so a card that exists ONLY
  // in the mutated payload must appear — and appear LAST, not in place of anything.
  const seed = MUT.includes('append') ? captured.items.find((i) => i.type === 'futures') : null;
  if (seed) {
    const probe = JSON.parse(JSON.stringify(seed));
    probe.data.id = 999000001;
    probe.data.name = MARKER;
    probe.headline = MARKER;
    items.push(probe);
  }
  mutatedCalls += 1;
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify({ ...captured, items }),
  });
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForTimeout(3000);

// The reader's edition: every card's detail link, in DOM order.
//
// NOT a headline slice. The first cut of this probe read the first 12 `<h3>`s and reported
// ORDER-HELD false — an artifact of its own cap, because one appended card pushes the twelfth
// title out of the window and every comparison after it slips by one. It also missed collapsed
// bundles entirely (their peek rows are not `<h3>`s). An href is a stable per-card identity that
// survives a re-render, and reading ALL of them means an append cannot masquerade as a removal.
const readOrder = () =>
  page.evaluate(() =>
    [...document.querySelectorAll('a[href^="/futures/"], a[href^="/events/"], a[href^="/event/"]')]
      .map((a) => a.getAttribute('href'))
      .filter((h, i, all) => h && all.indexOf(h) === i)
  );

const before = await readOrder();
console.log(`URL        ${url}`);
console.log(`BEFORE     ${before.length} card links on screen`);

console.log(`\nwaiting ${waitSeconds}s for a background revalidation tick (page revalidates every 120s)…`);
await page.waitForTimeout(waitSeconds * 1000);

const after = await readOrder();
console.log(`\nfeed calls ${feedCalls}, of which MUTATED ${mutatedCalls}`);
console.log(`AFTER      ${after.length} card links on screen`);
console.log(`APPENDED   ${JSON.stringify(after.filter((h) => !before.includes(h)))}`);
console.log(`PROBE CARD at index ${after.indexOf('/futures/999000001')} of ${after.length}`);
console.log(`BEFORE tail  ${JSON.stringify(before.slice(-4))}`);
console.log(`AFTER  tail  ${JSON.stringify(after.slice(-4))}`);

if (mutatedCalls === 0) {
  console.log('\n🔴 NO SPECIMEN — no second /api/feed call arrived, so the reader was never');
  console.log('   provoked. This is NOT a pass; re-run with a longer wait.');
  await browser.close();
  process.exit(1);
}

// ── VERDICT ────────────────────────────────────────────────────────────────
//
// 🔴 THE RENDER WINDOW IS NOT A REMOVAL, and conflating the two is how the first three runs of
// this probe reported a FAIL that was its own doing. The feed renders a bounded number of cards,
// so the single synthetic card appended above pushes exactly one card off the TAIL. That card
// has not been taken from the reader — the list it is in is longer than the window. The ship is
// about a card the SERVER STOPPED LISTING, so the ship arm names that card and looks for it.
const consumed = (await page.content()).includes(MARKER);
const held = droppedHref != null && after.includes(droppedHref);
// Order: the reader's cards that are still rendered must appear in the same relative order.
const stillRendered = before.filter((h) => after.includes(h));
const heldOrder = stillRendered.every(
  (h, i) => after.indexOf(h) > (i === 0 ? -1 : after.indexOf(stillRendered[i - 1]))
);
const displaced = before.filter((h) => !after.includes(h));
const tailDisplaced = displaced.every((h) => before.indexOf(h) >= before.length - displaced.length);

console.log(`\nCONSUMED   ${consumed}  (the appended card reached the DOM — the tick was not refused)`);
console.log(`HELD       ${held}  (${droppedHref}, the card the tick omitted, is still on screen)`);
console.log(`ORDER      ${heldOrder}  (the reader's remaining cards kept their relative order)`);
console.log(`DISPLACED  ${displaced.length} off the tail of the render window: ${JSON.stringify(displaced)} (tail-only: ${tailDisplaced})`);

if (!consumed) {
  console.log('\n🔴 NO SPECIMEN — the mutated tick was served but never reached the list, so a held');
  console.log('   order proves nothing about the reconcile. This is NOT a pass.');
  await browser.close();
  process.exit(1);
}
if (droppedHref == null) {
  console.log('\n🔴 NO SPECIMEN — the tick omitted nothing checkable. This is NOT a pass.');
  await browser.close();
  process.exit(1);
}
const pass = held && heldOrder && tailDisplaced;
console.log(pass
  ? '\n✅ PASS — the tick stopped listing a card the reader was holding, and the reader kept it,'
  + '\n   in place, while a genuinely new card was appended.'
  : '\n🔴 FAIL — the background tick removed or reordered a card under the reader.');
await browser.close();
process.exit(pass ? 0 : 1);
