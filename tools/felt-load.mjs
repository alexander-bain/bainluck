// felt-load.mjs — the number Alex feels: SECONDS TO THE FIRST REAL CARD.
//
// WHY THIS EXISTS, next to cold-load.mjs. cold-load.mjs reports FCP/LCP/DCL. None of those is the
// felt number. FCP fires when the *skeleton* paints — the grey placeholder grid is contentful — so a
// page can post a 1.2 s FCP and still show the reader nothing they came for. LCP names the biggest
// element, which on a card page is usually a hero photograph, i.e. a number about imagery. What a
// stranger actually waits for is "when did a real card with a real number appear", and nothing in
// this repo measured that. This does.
//
// THREE NUMBERS PER RUN, all in milliseconds from navigation start:
//   shell   — first contentful paint. The app's chrome is on screen; the reader knows the site works.
//   first   — FIRST REAL CARD. A card-shaped element that is NOT a skeleton and carries real text.
//   fold    — the LAST above-the-fold real card. The first screen has stopped changing.
// Plus `firstNumber` — first real card carrying a probability (`NN%`), because on this product a card
// without its number is only half a card, and the gap between `first` and `firstNumber` is a defect
// class of its own.
//
// 🔴 WHAT COUNTS AS A REAL CARD, stated so it can be argued with. An element is a real card when it
// (a) matches a card-shaped selector, (b) has no `animate-pulse` skeleton on it or inside it, (c) is
// not inside an `aria-hidden` placeholder subtree, (d) is at least 80x40 CSS px, and (e) carries ≥12
// characters of text. `textContent` is used for (e) — NOT `innerText`, which forces a synchronous
// layout on every frame and would let the instrument slow the thing it is timing.
//
// 🔴 ONLY NEWLY-APPEARED ELEMENTS COUNT. Every arm snapshots the cards already in the DOM into a
// WeakSet. On a cold load that set is empty; on a warm SPA tab-switch it is the *previous* tab's
// cards, which linger for a frame or two while Next unmounts. Without this the warm number would be
// the old page's cards re-measured, i.e. ~0 ms, and every warm row would be a lie.
//
// ⚠️ POPULATION. Same caveat as cold-load.mjs (LAT-P188): these run through this machine's session
// egress proxy. They are comparable TO EACH OTHER — before a cut and after a cut, page against page —
// and they are NOT comparable to a stopwatch on Alex's laptop on his own network.
//
// 🔴 PACING IS PART OF THE MEASUREMENT (LAT-P218). Production caps a client at 60 requests/minute.
// How many an Event load spends is NOT one number and the two measurements disagree: live/054 counted
// ~22 while hunting #2783, and this rig counts 7 against `api.bainluck.com` on the settled fixture
// `/events/15293206` (`apiStatus {"200":7}`, measured 2026-09-03). Different pages, different widget
// sets, possibly a different filter — unresolved, so the pacing is sized on the WORSE figure. At ~22
// per load the default 3 s pace puts the Event surface at roughly twice the budget.
// Every run now reports `api429` and `apiCount`, and the summary reports `throttledRuns`; if that
// number is not zero the row is about the battery, not the site. Raise `FELT_PACE_MS` (20000 is the
// measured-safe value) rather than reading a throttled row.
//
// Usage:
//   node tools/felt-load.mjs <surface|url> [runs] [out.json]
//   FELT_MODE=cold|warm   FELT_THROTTLE=slow4g|fast4g|3g   FELT_CPU=4   FELT_PACE_MS=3000
import { createRequire } from 'module';
import { existsSync, readdirSync, writeFileSync } from 'fs';

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

const ORIGIN = process.env.FELT_ORIGIN || 'https://www.bainluck.com';

// The surfaces the charter names: every top-level tab and the pages under them.
// `warmClick` is the selector of the REAL <Link> a reader would press to reach this surface from
// Discover. Where there is no such link (a deep URL a reader arrives at from search or a bookmark),
// `warmClick` is null and the warm row is measured as a warm-cache RELOAD instead — labelled as such,
// because a full document reload and an SPA transition are different experiences and averaging them
// would invent a number nobody feels.
const SURFACES = {
  discover:    { url: `${ORIGIN}/`,                       tab: 'Discover',   warmClick: 'a[href="/"]' },
  sports:      { url: `${ORIGIN}/sports`,                 tab: 'Sports',     warmClick: 'a[href="/sports"]' },
  usopen:      { url: `${ORIGIN}/tournaments/us-open`,    tab: 'Browse',     warmClick: null },
  search:      { url: `${ORIGIN}/search?q=chiefs`,        tab: 'Search',     warmClick: null },
  // Warm = tapping a card on Discover. Both link shapes are accepted: game cards
  // use `/events/:id`, concept cards use `/event/:key`, and a selector that knows
  // only one of them silently fails on whatever the feed happens to rank first.
  // An event page's first real content is its HERO, not a card list. The default
  // card vocabulary happened to match on the cold URL (the related-markets rail
  // renders card links) and matched nothing after a warm tap-through — which
  // reported a page showing ten live probabilities as "nothing ever appeared".
  // Warm origin is /sports, not Discover, ON PURPOSE. Tapping "the first card on
  // Discover" lands on a different KIND of page every run — a concept hub, a
  // futures market, a game — so the row measured a different surface each time
  // and four of five runs reported nothing because the destination did not speak
  // the event page's vocabulary. /sports lists game cards, so the destination is
  // always an event page and the five runs are five samples of ONE thing.
  event:       { url: `${ORIGIN}/events/15293206`,        tab: 'Discover',
                 warmFrom: `${ORIGIN}/sports`, warmClick: 'a[href^="/events/"]',
                 cardSel: '[data-testid="event-hero-probability"], [data-testid="event-hero-settled"], [data-testid="futures-hero-probability"], [data-testid="discover-card"], a[href^="/event/"], a[href^="/events/"], a[href^="/futures/"], article' },
  politics:    { url: `${ORIGIN}/politics`,               tab: 'Browse',     warmClick: 'a[href="/politics"]', warmPre: 'button:has-text("Browse")' },
  // Calibration's "first real card" is its first plotted curve. A recharts path
  // that exists but has no drawn series is the blank-chart failure this repo has
  // hit before, so the selector demands a `d` attribute with real coordinates.
  calibration: { url: `${ORIGIN}/calibration`,            tab: 'Browse',     warmClick: null,
                 cardSel: 'path.recharts-curve[d], .recharts-surface, table tbody tr' },
  // Signed out, Profile renders a sign-in panel, not cards — so its "first real
  // card" is that panel's call to action. Scoped to `main` deliberately: an
  // unscoped `button` matches the header's Browse control, which paints with the
  // chrome and would report Profile as instant on every run.
  profile:     { url: `${ORIGIN}/my-stuff`,               tab: 'Profile',    warmClick: 'a[href="/my-stuff"]',
                 cardSel: 'main [data-testid="discover-card"], main a[href^="/event/"], main a[href^="/events/"], main a[href^="/futures/"], main article, main button' },
};

const [target, runsArg, outJson] = process.argv.slice(2);
if (!target) {
  console.error(`usage: felt-load.mjs <surface|url> [runs] [out.json]\nsurfaces: ${Object.keys(SURFACES).join(', ')}`);
  process.exit(2);
}
const surface = SURFACES[target] || { url: target, tab: 'ad-hoc', warmClick: null };
const surfaceKey = SURFACES[target] ? target : 'url';
const RUNS = parseInt(runsArg || '5', 10);
const PACE_MS = parseInt(process.env.FELT_PACE_MS || '3000', 10);
const MODE = (process.env.FELT_MODE || 'cold').toLowerCase();

// 🔴 EVERY FELT NUMBER EVER TAKEN IS A FIRST-EVER VISIT (latency/137).
//
// `chromium.launch()` below passes no `userDataDir` and every run gets a fresh `newPage()`, so
// localStorage is empty on every single sample the board has ever contained. That is not a neutral
// default: the parse-time boot rail (`lib/discover/feedBoot.ts`, LAT-P184) switches ITSELF OFF when
// any key in `BOOT_BLOCKING_KEYS` is present, and `bainluck_session_id` — written unconditionally by
// `getSessionId()` on the first visit and never expired — is one of them. So the rig has only ever
// measured the one population for which the optimisation fires.
//
// `FELT_SEED_LS` is a JSON object of localStorage entries written BEFORE any page script runs, which
// is the only place it can go: the boot script is inline in the document `<head>` and reads storage
// synchronously at parse time, so a seed applied after navigation would arrive too late to be the
// thing under test. Values are written verbatim — the caller decides what a returning reader looks
// like, because "returning" is exactly the definition in question here.
//
//   arm A (first visit)    — unset. Today's board, the control.
//   arm B (returning anon) — '{"bainluck_session_id":"sess_felt_b"}'
//   arm C (auth key)       — '{"firebase:authUser:felt:[DEFAULT]":"{}"}'
//
// ⚠️ ARM C IS A PARSE-TIME PROXY, NOT A SIGNED-IN SESSION. The boot script tests only the KEY PREFIX,
// so a synthetic value reproduces the suppression faithfully; Firebase will then fail to restore the
// bogus user and the page settles as signed-out. It therefore measures what the suppression COSTS,
// and it does NOT measure an authenticated feed fetch. Read it as such or not at all.
let SEED_LS = null;
if (process.env.FELT_SEED_LS) {
  try {
    SEED_LS = JSON.parse(process.env.FELT_SEED_LS);
    if (!SEED_LS || typeof SEED_LS !== 'object' || Array.isArray(SEED_LS)) throw new Error('not an object');
  } catch (e) {
    // Fail LOUD. A silently-ignored seed makes arm B a second copy of arm A, and two identical arms
    // reported as a comparison is the exact shape of a measurement that says nothing while looking
    // like it says something.
    console.error(`FELT_SEED_LS is not a JSON object: ${e.message}`);
    process.exit(2);
  }
}
const SEED_ARM = process.env.FELT_ARM || (SEED_LS ? 'seeded' : 'first-visit');

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const baseArgs = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) baseArgs.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

// Chrome DevTools' own presets, by their DevTools names. "Slow 4G" is what DevTools calls the profile
// that used to be labelled Fast 3G — 1.6 Mbit/s at 562.5 ms RTT — and it is the one the charter asks
// for as iPhone-class. Getting this label wrong would put a 3x-faster link in a row headed "Slow 4G".
const PROFILES = {
  slow4g: { downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8, latency: 562.5 },
  fast4g: { downloadThroughput: 9 * 1024 * 1024 / 8, uploadThroughput: 1.5 * 1024 * 1024 / 8, latency: 170 },
  '3g':   { downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8, latency: 300 },
};

// The default card vocabulary. Two surfaces do not speak it and it would be
// dishonest to report them as blank: Calibration's first real content is a
// plotted curve, and a signed-out Profile's is a sign-in panel. Reporting
// "no card ever appeared" for a page that is working perfectly would put a
// false red in the table and send the next ship at the wrong row.
const DEFAULT_CARD_SEL = [
  '[data-testid="discover-card"]',
  'a[href^="/event/"]', 'a[href^="/events/"]', 'a[href^="/futures/"]',
  'a[href^="/sport/"]', 'a[href^="/tournaments/"]', 'a[href^="/categories/"]',
  'a[href^="/hub/"]', 'a[href^="/playoffs/"]',
  'article',
].join(',');

// 🔴 THE 12-CHARACTER FLOOR MADE THE EVENT PAGE'S HERO INVISIBLE (LAT-P216).
//
// `isReal` required >=12 characters of text, which is right for a card — a skeleton has almost no
// text — and exactly wrong for a hero. `EventHeroProbabilityPair` renders `99%-1%`: SIX characters.
// So on every cold Event run the hero was rejected, the detector fell through to the first
// related-futures link (long text), and the felt table reported the Event page's number as the
// arrival of the RELATED-MARKETS RAIL — a chained second-wave request — while calling it "seconds to
// the first real card". Every one of the five 2026-09-02 cold runs logged `firstDesc` as an anonymous
// `A :: MLB World Series Winner...`, and nobody read it.
//
// A hero is not a card and cannot borrow a card's realness test. Its placeholder is not a grey block
// with no text, it is the SAME element printing an em-dash where the number goes. So the honest
// predicate for a hero is "does it print a number yet", and that is what is used here.
const HERO_SEL = [
  '[data-testid="event-hero-probability"]',
  '[data-testid="event-hero-settled"]',
  '[data-testid="futures-hero-probability"]',
].join(',');

// Writes the arm's localStorage BEFORE any page script runs. Registered ahead of INIT so the keys
// are already in storage when the document's inline boot script reads them synchronously.
const SEED_INIT = (seed) => `
(() => {
  const SEED = ${JSON.stringify(seed || {})};
  try { for (const k in SEED) window.localStorage.setItem(k, SEED[k]); } catch (e) {}
})()`;

const INIT = (cardSel, heroSel) => `
(() => {
  const CARD_SEL = ${JSON.stringify(cardSel)};
  const HERO_SEL = ${JSON.stringify(heroSel)};

  const S = {
    origin: 0,            // performance.now() at the start of THIS arm
    label: 'cold',
    first: null, firstNumber: null, fold: null,
    hero: null, heroDesc: null,
    foldCount: 0, total: 0,
    firstDesc: null,
    skeletonSeen: false,
  };
  const seen = new WeakSet();
  // Counted cards, kept as a real Set so ancestry can be tested. A discover card CONTAINS an
  // <a href="/events/..."> and often an <article>, so a naive querySelectorAll counts one card three
  // times and the "cards above the fold" column inflates by ~2.5x. Only the OUTERMOST match counts;
  // document order guarantees the outer element is visited first within a frame.
  const counted = new Set();
  window.__FELT = S;

  function hasCountedAncestor(el) {
    for (let p = el.parentElement; p; p = p.parentElement) if (counted.has(p)) return true;
    return false;
  }

  // textContent, not innerText: innerText forces layout every frame and the instrument would then be
  // part of what it is measuring. A skeleton has almost no text, so textContent separates them fine.
  function isHero(el) { return HERO_SEL && el.matches && el.matches(HERO_SEL); }

  // 🔴 A ZERO-SIZE BOX IS NOT AN ABSENT CARD (LAT-P216). The 80x40 floor is there to reject
  // furniture, and it silently rejected the US Open page instead. Its result rows are anchors that
  // generate no box of their own — display:contents, or a wrapper whose children carry the layout —
  // so getBoundingClientRect() returns 0x0 on an element holding 87 characters of visible scoreline.
  // In the afternoon the page also had LIVE match cards, which do have boxes, so the surface measured
  // fine and the blindness only appears at night once the live cards are gone. That is the worst
  // possible failure shape: an instrument that works exactly until the population changes under it.
  // When an element has no box, its visible extent is its children's; that union is what gets tested.
  function boxOf(el) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return r;
    let top = Infinity, left = Infinity, bottom = -Infinity, right = -Infinity;
    for (const k of el.children) {
      const kr = k.getBoundingClientRect();
      if (kr.width <= 0 || kr.height <= 0) continue;
      top = Math.min(top, kr.top); left = Math.min(left, kr.left);
      bottom = Math.max(bottom, kr.bottom); right = Math.max(right, kr.right);
    }
    if (bottom === -Infinity) return r;
    return { top, left, bottom, right, width: right - left, height: bottom - top };
  }

  function isReal(el) {
    if (el.classList && el.classList.contains('animate-pulse')) return false;
    if (el.closest('.animate-pulse')) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    if (el.querySelector('.animate-pulse')) return false;
    const t = (el.textContent || '').trim();
    // A hero is real when it prints ITS OWN ANSWER, and the two heroes have two different answers.
    // Neither is a character count and neither is a box size:
    //   - the live hero answers with a number, and its unresolved state is the SAME element printing
    //     an em-dash, so only the number test separates them;
    //   - the settled hero answers with a WINNER ("settled means settled: heroes show winners"), so a
    //     number test would reject it forever. It declares its own readiness in data-winner, which is
    //     empty until the outcome is known — that attribute IS the contract, so it is what is used.
    // The 80x40 floor is skipped for heroes: the settled hero measures 70x55 on production and would
    // be rejected as furniture by a rule written for cards.
    if (isHero(el)) {
      const settled = el.getAttribute('data-winner');
      if (settled !== null) { if (!settled.trim()) return false; }
      else if (!/\\d{1,3}\\s?%/.test(t)) return false;
      return true;
    }
    if (t.length < 12) return false;
    const r = boxOf(el);
    if (r.width < 80 || r.height < 40) return false;
    return true;
  }

  function tick() {
    const now = performance.now() - S.origin;
    // Cheap pre-check: has a skeleton ever been on screen? Tells us whether "first" was preceded by a
    // placeholder (the reader waited looking at grey) or by nothing (the reader waited looking at white).
    if (!S.skeletonSeen && document.querySelector('.animate-pulse')) S.skeletonSeen = true;
    // The hero is scanned SEPARATELY from the card loop, on purpose. Folding it in would leave it at
    // the mercy of two card-shaped rules that have nothing to do with it: it would be skipped by
    // hasCountedAncestor whenever a card-shaped wrapper happened to be counted first, and it would
    // be missed entirely on any surface whose cardSel does not happen to name it. A hero is the one
    // element on the page the reader actually came for; it gets its own clock.
    if (S.hero === null && HERO_SEL) {
      for (const h of document.querySelectorAll(HERO_SEL)) {
        if (!isReal(h)) continue;
        S.hero = now;
        S.heroDesc = (h.getAttribute('data-testid') || h.tagName) + ' :: ' + (h.textContent || '').trim().slice(0, 40);
        break;
      }
    }
    const nodes = document.querySelectorAll(CARD_SEL);
    for (const el of nodes) {
      if (seen.has(el)) continue;
      if (!isReal(el)) continue;      // not marked seen: a skeleton can become real in place
      if (hasCountedAncestor(el)) { seen.add(el); continue; }
      seen.add(el);
      counted.add(el);
      S.total++;
      if (S.first === null) {
        S.first = now;
        S.firstDesc = (el.getAttribute('data-testid') || el.tagName) + ' :: ' + (el.textContent || '').trim().slice(0, 70);
      }
      if (S.firstNumber === null && /\\d{1,3}\\s?%/.test(el.textContent || '')) S.firstNumber = now;
      const r = boxOf(el);
      if (r.top < window.innerHeight && r.bottom > 0) { S.fold = now; S.foldCount++; }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // Re-arm for a warm transition. Everything already on screen belongs to the PREVIOUS tab and must
  // not be counted as this tab's first card.
  window.__feltArm = (label) => {
    // Only ALREADY-REAL cards belong to the previous screen. A skeleton mounted
    // at arm time is the INCOMING screen's, and React upgrades it in place — so
    // excluding it here would hide the very card we are timing.
    for (const el of document.querySelectorAll(CARD_SEL)) if (isReal(el)) seen.add(el);
    counted.clear();
    S.origin = performance.now();
    S.label = label || 'warm';
    S.first = S.firstNumber = S.fold = null;
    S.hero = null; S.heroDesc = null;
    S.foldCount = 0; S.total = 0; S.firstDesc = null; S.skeletonSeen = false;
    return S.origin;
  };
})();
`;

const COLLECT = `(() => {
  const S = window.__FELT || {};
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paint = Object.fromEntries(performance.getEntriesByType('paint').map(p => [p.name, p.startTime]));
  const res = performance.getEntriesByType('resource');
  const byKind = {};
  for (const r of res) {
    const k = r.initiatorType || 'other';
    byKind[k] = byKind[k] || { count: 0, transfer: 0 };
    byKind[k].count++; byKind[k].transfer += r.transferSize || 0;
  }
  // Which API calls the first screen waited on, and how long each took. This is the "where do the
  // seconds go" column: a slow /api/feed and a slow bundle look identical in FCP and nothing alike here.
  //
  // 🔴 THE STATUS COLUMN IS NOT DECORATION (LAT-P218). One /events/{id} cold load fires ~22 requests
  // and production caps a client at 60/minute, so an unpaced battery throttles itself and then reports
  // the throttling as a blank page: the "blank event page" of #2783 turned out to be the app rendering
  // "Rate limit exceeded: 60/minute", 673 body chars, indistinguishable from an empty render in every
  // column this table used to have. responseStatus is what tells them apart, and without it an
  // UNATTENDED watcher can bank its own 429s as a reader-visible regression. ?? null because the
  // field is only populated for same-origin or CORS-visible responses; a null is "not reported", never 200.
  // (No backticks anywhere in this block: it lives inside a template literal.)
  const apiRes = res.filter(r => /api\\.bainluck\\.com/.test(r.name));
  const api = apiRes
    .map(r => ({ url: r.name.replace(/^https?:\\/\\/[^/]+/, ''), start: Math.round(r.startTime), end: Math.round(r.responseEnd), dur: Math.round(r.duration), status: r.responseStatus ?? null }))
    .sort((a, b) => a.start - b.start).slice(0, 12);
  const statusCounts = {};
  for (const r of apiRes) { const s = r.responseStatus ?? 'unreported'; statusCounts[s] = (statusCounts[s] || 0) + 1; }
  const scriptMs = res.filter(r => r.initiatorType === 'script' || /\\.js(\\?|$)/.test(r.name))
    .reduce((a, r) => Math.max(a, r.responseEnd), 0);
  return {
    shell: paint['first-contentful-paint'] ?? null,
    first: S.first, firstNumber: S.firstNumber, fold: S.fold,
    hero: S.hero, heroDesc: S.heroDesc,
    heroPresent: document.querySelectorAll(${JSON.stringify(HERO_SEL)}).length,
    foldCards: S.foldCount, totalCards: S.total, firstDesc: S.firstDesc, skeletonSeen: S.skeletonSeen,
    ttfb: nav.responseStart ?? null, dcl: nav.domContentLoadedEventEnd ?? null, load: nav.loadEventEnd ?? null,
    lastScriptEnd: Math.round(scriptMs),
    api,
    apiCount: apiRes.length,
    // When the first API request left, in ms from navigation start. Useful colour on a throttled run.
    //
    // ⚠️ THIS IS NOT A BOOT-RAIL SIGNAL, THOUGH IT LOOKS EXACTLY LIKE ONE (latency/137). It is tempting
    // to read "firstApiStart < lastScriptEnd" as "the parse-time boot fired" — it is wrong, and it was
    // measured wrong before it was caught. lastScriptEnd is when the last script finished DOWNLOADING,
    // not executing, and on an unthrottled link the entry graph hydrates long before the final lazy
    // chunk lands: a /sports run with the boot PROVABLY suppressed still put its feed request on the
    // wire at 143 ms against a 532 ms lastScriptEnd, which the heuristic scores as "fired". Use
    // tools/boot-rail-probe.mjs, which reads whether the boot slot was ever parked and whether the
    // request carried an x-session-id header. Neither of those can be argued with.
    firstApiStart: api.length ? api[0].start : null,
    // Proof the arm's seed actually landed. An unapplied seed makes arm B a silent duplicate of arm A.
    lsKeys: (() => { try { const o = []; for (let i = 0; i < localStorage.length; i++) o.push(localStorage.key(i)); return o.sort(); } catch (e) { return null; } })(),
    apiStatus: statusCounts,
    api429: statusCounts['429'] || 0,
    api5xx: Object.entries(statusCounts).filter(([s]) => /^5\\d\\d$/.test(s)).reduce((a, [, n]) => a + n, 0),
    byKind,
    proof: {
      title: document.title,
      cards: document.querySelectorAll('[data-testid="discover-card"], a[href^="/futures/"], a[href^="/event/"], a[href^="/events/"]').length,
      pct: (document.body.innerText.match(/\\d+%/g) || []).length,
      bodyChars: document.body.innerText.length,
      // The rate-limit page is a REAL render of a REAL error, so pct=0 and bodyChars~673 look exactly
      // like an empty page. Its own words are the only unambiguous signal, and they are cheap to read.
      rateLimitText: /Rate limit exceeded/i.test(document.body.innerText),
    },
  };
})()`;

async function newBrowser() {
  return chromium.launch({ args: baseArgs });
}

async function armPage(page, coldCache) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  if (coldCache) await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const prof = PROFILES[(process.env.FELT_THROTTLE || '').toLowerCase()];
  if (prof) await cdp.send('Network.emulateNetworkConditions', { offline: false, ...prof });
  const cpu = parseFloat(process.env.FELT_CPU || '1');
  if (cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
  return cdp;
}

// Wait until the first real card exists, or the budget expires. Polling in Node rather than exposing a
// promise keeps the page's own timeline untouched.
async function waitFirstCard(page, budgetMs) {
  const deadline = Date.now() + budgetMs;
  while (Date.now() < deadline) {
    const got = await page.evaluate('window.__FELT && window.__FELT.first');
    if (got !== null && got !== undefined) return true;
    await page.waitForTimeout(60);
  }
  return false;
}

const results = [];
for (let i = 0; i < RUNS; i++) {
  if (i > 0 && PACE_MS > 0) await new Promise((r) => setTimeout(r, PACE_MS));
  const browser = await newBrowser();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    if (SEED_LS) await page.addInitScript(SEED_INIT(SEED_LS));
    await page.addInitScript(INIT(surface.cardSel || DEFAULT_CARD_SEL, HERO_SEL));

    let m;
    if (MODE === 'warm') {
      // A warm tab-switch is not a page load. Load Discover first, let it settle — that is the reader
      // who has been on the site for a minute — and only then time the transition.
      await armPage(page, true);
      // 🔴 Start from a DIFFERENT tab than the one under test. Measuring a switch
      // to Discover while already on Discover clicks a link to the current route,
      // React re-renders nothing, and the run reports "no card ever appeared" for
      // the fastest surface on the site. Measured, not reasoned: the first warm
      // pass did exactly that on 4 of 5 Discover runs.
      const warmOrigin = surface.warmFrom || (surface.url === `${ORIGIN}/` ? `${ORIGIN}/sports` : `${ORIGIN}/`);
      await page.goto(warmOrigin, { waitUntil: 'load', timeout: 120000 });
      try { await page.waitForLoadState('networkidle', { timeout: 30000 }); } catch {}
      await page.waitForTimeout(500);

      const t0 = Date.now();
      let how;
      if (surface.warmClick) {
        if (surface.warmPre) { try { await page.click(surface.warmPre, { timeout: 3000 }); await page.waitForTimeout(200); } catch {} }
        await page.evaluate('window.__feltArm("warm-spa")');
        await page.click(surface.warmClick, { timeout: 10000 });
        how = 'spa-click';
      } else {
        // No nav link to this surface: the honest warm equivalent is a reload with a warm HTTP cache.
        const cdp2 = await page.context().newCDPSession(page);
        await cdp2.send('Network.enable');
        await cdp2.send('Network.setCacheDisabled', { cacheDisabled: false });
        await page.evaluate('window.__feltArm("warm-reload")');
        await page.goto(surface.url, { waitUntil: 'commit', timeout: 120000 });
        how = 'warm-reload';
      }
      await waitFirstCard(page, 45000);
      try { await page.waitForLoadState('networkidle', { timeout: 30000 }); } catch {}
      m = await page.evaluate(COLLECT);
      m.how = how;
      m.wallTransition = Date.now() - t0;
      // A warm-reload restarts the document, so its own FCP is meaningful; an SPA click does not, so
      // the navigation-timing `shell` belongs to Discover and must not be reported as this tab's.
      if (how === 'spa-click') { m.shell = null; m.ttfb = null; m.dcl = null; m.load = null; }
    } else {
      await armPage(page, true);
      const t0 = Date.now();
      await page.goto(surface.url, { waitUntil: 'load', timeout: 120000 });
      await waitFirstCard(page, 45000);
      try { await page.waitForLoadState('networkidle', { timeout: 45000 }); } catch {}
      m = await page.evaluate(COLLECT);
      m.how = 'cold-load';
      m.wallTransition = Date.now() - t0;
    }

    m.run = i + 1;
    m.surface = surfaceKey;
    m.url = surface.url;
    m.arm = SEED_ARM;
    // 🔴 A SEED THAT DID NOT LAND IS NOT A CONTROL, IT IS A LIE (latency/137). Arm B differs from arm A
    // by exactly one localStorage key; if that key is missing at collect time the two arms are the same
    // arm and any difference between them is noise being read as a finding.
    if (SEED_LS) {
      const want = Object.keys(SEED_LS);
      const got = Array.isArray(m.lsKeys) ? m.lsKeys : [];
      const missing = want.filter(k => !got.includes(k));
      m.seedApplied = missing.length === 0;
      if (!m.seedApplied) console.error(`   🔴 run ${i + 1} SEED DID NOT APPLY — missing ${JSON.stringify(missing)}; run is INVALID for arm ${SEED_ARM}`);
    }
    // 🔴 A page that rendered nothing still posts a plausible — and faster — FCP (LAT-P202). A run
    // with no first card is not a fast run, it is a failed run, and averaging it in reports the
    // failure as an improvement.
    // Validity IS "the surface's own detector found real content". `proof.cards`
    // must NOT be part of this test: it counts card-shaped links, and a signed-out
    // Profile legitimately has none — it shows a sign-in panel. Requiring it
    // marked five perfectly healthy 0.15 s Profile loads INVALID, i.e. it turned
    // "this surface is not made of cards" into "this surface never rendered".
    // The LAT-P202 empty-render guard is unaffected: those runs had `first`
    // null, because nothing real ever appeared by any definition.
    m.valid = m.first !== null && m.seedApplied !== false;
    // 🔴 A SELF-THROTTLED RUN IS NEITHER A PASS NOR A BLANK (LAT-P218). It is the battery measuring its
    // own 60/min budget, and it has to be its own outcome: counted as valid it drags the medians with a
    // number nobody experiences, counted as invalid it becomes a false "reader saw nothing" — which is
    // exactly how #2783 was filed. So it is excluded from medians and reported on its own line.
    m.throttled = (m.api429 || 0) > 0 || !!m.proof?.rateLimitText;
    if (!m.valid && !m.throttled) console.error(`   ⚠️ run ${i + 1} INVALID — no real card ever appeared; excluded from medians`);
    if (m.throttled) console.error(`   🔴 run ${i + 1} SELF-THROTTLED — ${m.api429} of ${m.apiCount} API responses were 429; excluded from medians and NOT a blank`);
    results.push(m);
    console.error(
      `run ${i + 1}/${RUNS} ${surfaceKey.padEnd(11)} ${String(m.how).padEnd(12)} ` +
      `shell=${m.shell == null ? '   -' : Math.round(m.shell)} first=${m.first == null ? 'NONE' : Math.round(m.first)} ` +
      `hero=${m.hero == null ? (m.heroPresent ? 'NEVER-REAL' : 'ABSENT') : Math.round(m.hero)} ` +
      `firstNum=${m.firstNumber == null ? 'NONE' : Math.round(m.firstNumber)} fold=${m.fold == null ? 'NONE' : Math.round(m.fold)} ` +
      `foldCards=${m.foldCards} cards=${m.proof.cards} pct=${m.proof.pct} skel=${m.skeletonSeen} ` +
      `api=${m.apiCount}${m.throttled ? ` 🔴429x${m.api429}` : ''}${m.api5xx ? ` 5xx×${m.api5xx}` : ''}`
    );
  } catch (e) {
    console.error(`run ${i + 1}/${RUNS} FAILED :: ${e.message}`);
    results.push({ run: i + 1, surface: surfaceKey, error: e.message, valid: false });
  } finally {
    await browser.close();
  }
}

// Medians are taken over runs that both rendered AND were not self-throttled. `valid` still means
// "the detector found real content" — the two counts are reported side by side so a table can never
// silently average a 429 into a felt number.
const ok = results.filter(r => r.valid && !r.throttled);
const pct = (xs, p) => {
  const s = xs.filter(x => typeof x === 'number' && isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  // Nearest-rank. With n=5 this is an honest order statistic and not an interpolation that invents a
  // value between two runs; p95 of five runs IS the worst run and is reported as such.
  const idx = Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1);
  return s[Math.max(0, idx)];
};
const summ = (key) => ({
  p50: pct(ok.map(r => r[key]), 50),
  p95: pct(ok.map(r => r[key]), 95),
  worst: pct(ok.map(r => r[key]), 100),
});
const summary = {
  surface: surfaceKey, url: surface.url, tab: surface.tab,
  mode: MODE, throttle: process.env.FELT_THROTTLE || 'none', cpu: process.env.FELT_CPU || '1',
  runs: RUNS, valid: ok.length,
  throttledRuns: results.filter(r => r.throttled).length,
  medianApiCalls: pct(results.map(r => r.apiCount), 50),
  shell: summ('shell'), first: summ('first'), firstNumber: summ('firstNumber'), fold: summ('fold'),
  // `hero` is reported next to `first` rather than replacing it, because the gap between them is
  // itself the finding: on the Event page `first` is the related-markets rail and `hero` is the
  // number in 48px type. A row that quotes only one of them is quoting the wrong page.
  hero: summ('hero'),
  heroRuns: ok.filter(r => typeof r.hero === 'number').length,
  heroPresentRuns: ok.filter(r => r.heroPresent > 0).length,
  medianFoldCards: pct(ok.map(r => r.foldCards), 50),
  medianLastScriptEnd: pct(ok.map(r => r.lastScriptEnd), 50),
  skeletonSeen: ok.length ? ok.every(r => r.skeletonSeen) : null,
};
console.log(JSON.stringify({ summary, results }, null, 2));
if (outJson) writeFileSync(outJson, JSON.stringify({ summary, results }, null, 2));
if (!ok.length) process.exit(1);
