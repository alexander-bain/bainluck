// dashboard-two-leg-cards-6766.mjs — does a two-leg dashboard card print the SERVED second
// number, or one it derived as `100 − first` (#6766)?
//
// THE DEFECT. `/politics` `BinaryCard` and `/entertainment`'s two `YesNoBar` call sites compute
// the second number as `100 - prob` and label it with `top_outcomes[1].name`. On a genuine Yes/No
// binary that is exactly right. On a two-RUNG market — "John Thune announces departure?" priced
// `Before Nov 3, 2026` 2.5% and `Before Oct 1, 2026` 1.0% — the two legs are not complements, and
// the card printed **98%** beside the name of a leg the venue prices at **1%**.
//
// SUBJECT DETECTION IS NOT KEYED ON THE DEFECT. The subject is "a card for a market the payload
// serves with exactly two outcome legs" — a fact about the DATA, true before and after any render
// change. A probe that looked for, say, two percents summing to 100 would report the fixed page as
// "no subjects found", which is ux/1314's lesson and this file's reason for existing.
//
// THE PAYLOAD IS READ THROUGH `curl`, not `fetch`: node's fetch is not reliably routed in the lane
// sandbox, and the page's own origin is not always the API's.
//
// Usage:
//   node tools/dashboard-two-leg-cards-6766.mjs [origin] [apiOrigin] [width]
//   node tools/dashboard-two-leg-cards-6766.mjs https://bainluck.com https://api.bainluck.com 390
//   CARD_JSON=/path/rows.json  banks every measured card
//   SHOT_DIR=/path             clips a PNG of every card that disagrees
//
// Exit: 0 every two-leg card prints its served legs · 3 at least one disagrees ·
//       4 no two-leg card was measured at all (NOT a pass — the population moved) ·
//       2 usage/harness.
import { createRequire } from 'module';
import { existsSync, readdirSync, writeFileSync, mkdirSync } from 'fs';
import { execFileSync } from 'child_process';

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

const origin = process.argv[2] || 'https://bainluck.com';
const apiOrigin = process.argv[3] || 'https://api.bainluck.com';
const width = parseInt(process.argv[4] || '390', 10);
const shotDir = process.env.SHOT_DIR || null;
if (shotDir) mkdirSync(shotDir, { recursive: true });

// A printed number may legitimately differ from the served one by a rounding step. Anything
// beyond a point is not rounding.
const TOLERANCE = 1.5;

function servedMarkets(path) {
  const raw = execFileSync('curl', ['-s', `${apiOrigin}${path}`], { maxBuffer: 64 * 1024 * 1024 });
  const data = JSON.parse(raw.toString());
  const byId = new Map();
  const walk = (o) => {
    if (Array.isArray(o)) return o.forEach(walk);
    if (!o || typeof o !== 'object') return;
    if (o.market_id && Array.isArray(o.top_outcomes)) {
      byId.set(String(o.market_id), { q: o.q, prob: o.prob, legs: o.top_outcomes });
    }
    Object.values(o).forEach(walk);
  };
  walk(data);
  return byId;
}

const SURFACES = [
  { page: '/politics', api: '/api/politics' },
  { page: '/entertainment', api: '/api/entertainment' },
];

const local = origin.includes('localhost') || origin.includes('127.0.0.1');
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy && !local) {
  args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
}

const rows = [];
let disagreements = 0;
let measured = 0;

for (const surface of SURFACES) {
  let served;
  try {
    served = servedMarkets(surface.api);
  } catch (e) {
    console.error(`🔴 ${surface.api}: could not read the payload — ${e.message}`);
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: true, args });
  const page = await browser.newPage({ viewport: { width, height: 900 } });

  // AGAINST A LOCAL BUILD, the page's own fetch cannot reach the API: the origin
  // is `localhost` and `route.fetch()` EPERMs outside the sandbox proxy. Each API
  // call is served through a `curl` child with an open CORS header, so the AFTER
  // arm renders the SAME payload the BEFORE arm measured against production.
  if (local) {
    await page.route('**/api.bainluck.com/**', async (route) => {
      const target = route.request().url();
      try {
        const body = execFileSync('curl', ['-s', target], { maxBuffer: 64 * 1024 * 1024 });
        await route.fulfill({
          status: 200,
          headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
          body,
        });
      } catch {
        await route.abort();
      }
    });
  }

  await page.goto(origin + surface.page, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('a[href^="/futures/"]', { timeout: 30000 }); } catch {}
  await page.waitForTimeout(parseInt(process.env.SETTLE_MS || '4000', 10));

  const cards = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href^="/futures/"]').forEach((el, index) => {
      const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
      out.push({
        index,
        id: (el.getAttribute('href') || '').split('/').pop(),
        text,
        percents: (text.match(/(?<!\d)(\d{1,3}(?:\.\d)?)%/g) || []).map((s) => parseFloat(s)),
      });
    });
    return out;
  });

  const handles = await page.$$('a[href^="/futures/"]');

  for (const card of cards) {
    const market = served.get(card.id);
    if (!market || market.legs.length !== 2) continue;   // subject = a TWO-LEG market
    if (card.percents.length < 2) continue;              // this card prints one number only
    measured += 1;

    const second = market.legs[1].prob;
    const printedSecond = card.percents[1];
    const off = Math.abs(printedSecond - second);
    const complement = Math.abs(100 - market.legs[0].prob - printedSecond) <= 0.51;
    const bad = off > TOLERANCE;
    if (bad) disagreements += 1;

    rows.push({
      surface: surface.page,
      id: card.id,
      q: market.q,
      served: market.legs.map((l) => `${l.name} ${l.prob}%`),
      printed: card.percents,
      printedSecond,
      servedSecond: second,
      looksLikeComplement: complement,
      verdict: bad ? 'DISAGREES' : 'ok',
      text: card.text.slice(0, 120),
    });

    if (bad) {
      console.log(`🔴 ${surface.page} /futures/${card.id} — printed ${printedSecond}% where the payload says ${second}% (${market.legs[1].name})`);
      console.log(`     served: ${market.legs.map((l) => `${l.name} ${l.prob}%`).join(' | ')}`);
      console.log(`     card:   ${card.text.slice(0, 120)}`);
      if (shotDir) {
        const file = `${shotDir}/card-${card.id}.png`;
        try { await handles[card.index].screenshot({ path: file }); console.log(`     shot:   ${file}`); } catch (e) { console.log(`     shot:   failed (${e.message})`); }
      }
    }
  }

  await browser.close();
}

if (process.env.CARD_JSON) writeFileSync(process.env.CARD_JSON, JSON.stringify(rows, null, 1));

console.log(`\n${origin} @ ${width}px · ${measured} two-leg cards measured · ${disagreements} printing a number the payload does not carry`);

if (measured === 0) {
  console.log('🔴 0 two-leg cards measured — that is NOT a pass. Re-check the payload and the selector.');
  process.exit(4);
}
process.exit(disagreements > 0 ? 3 : 0);
