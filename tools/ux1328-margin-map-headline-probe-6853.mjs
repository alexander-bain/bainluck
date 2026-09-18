// ux1328-margin-map-headline-probe-6853.mjs <after|control> <payload.json> <out.png>
//
// #6853's AFTER-CHECK on the DEPLOYED bundle, against a restored specimen.
//
// THE CLAIM UNDER TEST. `MarketMapSection`'s margin-map headline was an inline
// `Math.round(favoredProb * 100)`, so a live game at 0.999 printed `BUF 100%`
// one screen below a hero reading `>99%` off the same number. The fix routes it
// through `formatProbability`, the function the hero already uses.
//
// WHY A RESTORED SPECIMEN, AND WHY THIS ONE IS STRONG. The population is "a live
// game whose favourite is past 0.995 AND that carries a Kalshi cover ladder" —
// minutes per game. ux/1326 spent a session finding none: the one candidate past
// the threshold served Polymarket-shaped `spreads[]` with no per-outcome cover
// text, so `parseSpreadOutcome` returned nothing and the card never rendered.
// At 06:30Z tonight production carried 19 live events, all tennis plus one
// soccer fixture, and not one had a cover ladder.
//
// But `/api/events/14638444` — THE GAME THE ISSUE WAS FILED OFF, at the very
// minute it was filed — still serves `current_odds.home_probability: 0.999`,
// the exact number in the issue body, and still serves its own 25-rung Kalshi
// ladder (`"Buffalo wins by over 9.5 points"`) on a SEPARATE route this probe
// does not touch. So the defect's two inputs are both production's own bytes.
// Only settlement has moved on, and settlement is what this probe puts back.
//
// 🪤 WHAT IS AND IS NOT MANUFACTURED. Restored: the five fields settlement
// rewrote (below). Untouched and real: the 0.999 that DRIVES the headline, the
// ladder that makes the card render, scores, and every other block. Weaker than
// #6858's check in one respect and it must be said plainly: the ladder's rungs
// have since been GRADED to 0.0/1.0, so the band this card draws is a settled
// shape rather than the live one. That changes the picture's density, NOT the
// claim — the headline reads `current_odds`, never the ladder. The ladder's only
// job here is to clear `parsed.length === 0` so the card exists to be read.
//
// 🪤 `status: 'live'` ALONE IS NOT ENOUGH — ux/1326 lost a frame to this and the
// trap is identical here. The hero does not read `current_odds`; settlement also
// rewrote `hero_probability`, `hero_probability_away`, `hero_probability_source`
// and `espn.period`. Without those the page comes back reading `Final · 0:00`
// over a `100% – 0%` hero, which reads exactly like a failed fix.
//
//   MODE `after`    the filed condition restored. The margin map headline must
//                   print the marked above-boundary form, not a bare 100%.
//   MODE `control`  no interception at all. Production's real settled game,
//                   which pins the half of #6853 that must NOT have moved: a
//                   graded card prints NO headline here (#5206's `isDone` arm).
//
// WHY A POSITIVE RESULT NEEDS NO BUNDLE MARKER. `Math.round(0.999 * 100)` is
// 100 and can be nothing else, so the pre-fix code cannot print `>99%` at any
// input. Observing that string on the live page IS the marker. (The deployment
// id is recorded anyway, from the page's own asset query string.)
//
// Fulfil ONLY the event detail route: catch-all-ing the API renders the page's
// ErrorBoundary, which reads exactly like a crash in the change under test.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 the margin map
// never rendered (NOT a pass), 5 the interception never fired, 6 the specimen
// moved, 1 camera/navigation.
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

const [mode, payloadPath, out] = process.argv.slice(2);
if (!['after', 'control'].includes(mode) || !payloadPath || !out) {
  console.error('usage: … <after|control> <payload.json> <out.png>');
  process.exit(2);
}

const EVENT = 14638444;
const URL = `https://www.bainluck.com/events/${EVENT}`;

// Read from a file the CALLER fetched with curl, not with node's `fetch`: the
// lane sandbox refuses node's egress with EPERM while curl is allowed, and a
// probe that dies before the browser opens looks like a broken probe rather
// than a blocked socket. Fetch it with:
//   curl -s https://api.bainluck.com/api/events/14638444 -o /tmp/ev6853.json
const payload = JSON.parse(readFileSync(payloadPath, 'utf8'));
const hp = payload.current_odds?.home_probability;
console.log(
  `upstream: status=${payload.status} home_probability=${hp} ` +
    `away_probability=${payload.current_odds?.away_probability}`,
);

// The specimen IS the filed number. If it has moved, this probe is measuring a
// different question and must say so rather than quietly grading a new one.
if (hp !== 0.999) {
  console.error(`SPECIMEN MOVED: served home_probability is ${hp}, not the filed 0.999 — re-read the issue`);
  process.exit(6);
}

// Exactly the fields that make production call this game over. `current_odds`,
// the scores, the ladder route and every source block are untouched.
const live = {
  ...payload,
  status: 'live',
  completed_at: null,
  hero_settled_result: null,
  started_without_result: false,
  hero_probability: payload.current_odds.home_probability,
  hero_probability_away: payload.current_odds.away_probability,
  hero_probability_source: 'blend',
  espn: { ...(payload.espn ?? {}), period: '4th Quarter', game_clock: '2:50' },
};

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width: 390, height: 900 },
  deviceScaleFactor: 2,
});
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });

// The deployment the page actually served, read off its own asset URLs.
let deployment = null;
page.on('request', (r) => {
  const m = /[?&]dpl=(dpl_[A-Za-z0-9]+)/.exec(r.url());
  if (m && !deployment) deployment = m[1];
});

let fulfilled = 0;
if (mode === 'after') {
  await page.route(`**/api/events/${EVENT}`, (route) => {
    fulfilled += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(live),
    });
  });
}

// `networkidle` is the wrong wait for a page that re-polls; wait for the card's
// own title instead, then settle. `MarketMapSection` is `ssr: false`, so it is
// not in the HTML and only exists after its chunk loads.
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page
  .getByText(/Margin map|Margin: expected vs final/)
  .first()
  .waitFor({ state: 'attached', timeout: 60000 })
  .catch(() => {});
await page.waitForTimeout(4000);

// The consent banner is `fixed` to the viewport bottom, so it lands ON whatever
// band gets framed. ux/1327 photographed the cookie notice twice before this.
const decline = page.getByRole('button', { name: /^Decline$/ });
if (await decline.count()) {
  await decline.first().click();
  await page.waitForTimeout(1200);
}

if (mode === 'after' && fulfilled === 0) {
  console.error('INTERCEPTION NEVER FIRED — the page did not fetch the route this probe pins');
  await browser.close();
  process.exit(5);
}

// Read the headline STRUCTURALLY, off the card's own header row, rather than by
// scraping percents out of the page text: this page prints dozens of percents
// and the one under test is defined by its position beside the card title.
const read = await page.evaluate(() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // The title div, then its grandparent header row, whose LAST child is the
  // headline slot (MarketMap.tsx: title+subtitle in one column, headline in the
  // sibling). Anchored on the exact title so a neighbouring card cannot match.
  //
  // 🪤 THE TWO ARMS DO NOT SHARE A TITLE, which cost this probe a run. The card
  // renames itself when it grades: `live` -> the sport's declared `marginTitle`
  // ("Margin map"), `done` -> "Margin: expected vs final". Matching only the
  // live form reported the settled control as "card absent" (exit 4) on a page
  // whose card was plainly there — a rig failure wearing a product verdict.
  const TITLES = /^(Margin map|Goal margin map|Game margin map|Margin: expected vs final)$/;
  let titleEl = null;
  for (const el of document.querySelectorAll('div')) {
    if (el.children.length === 0 && TITLES.test(norm(el.textContent))) {
      titleEl = el;
      break;
    }
  }
  let headline = null;
  let subtitle = null;
  if (titleEl) {
    const col = titleEl.parentElement;
    subtitle = norm(col?.lastElementChild?.textContent);
    const headerRow = col?.parentElement;
    const last = headerRow?.lastElementChild;
    if (last && last !== col) headline = norm(last.textContent);
  }

  const text = norm(document.body.innerText);

  /* The hero's OWN pair — the number the map is supposed to agree with, and the
     whole point of the issue ("one probability, one page, two renderings").
     🪤 NOT the first `N% – M%` in the page text: that regex returns `68% – 32%`,
     which is the PRE-GAME pair this page also prints, so a naive read reports a
     disagreement between the map and a number the map was never about. Anchor
     on position instead — the hero is the topmost pair on the page — and report
     every pair seen so the choice is auditable rather than asserted. */
  const pairs = [];
  for (const el of document.querySelectorAll('div,span,p')) {
    if (el.children.length) continue;
    const t = norm(el.textContent);
    if (/^[<>]?\d+%$/.test(t)) {
      const r = el.getBoundingClientRect();
      const top = r.top + window.scrollY;
      pairs.push({ t, top: Math.round(top), left: Math.round(r.left) });
    }
  }
  pairs.sort((a, b) => a.top - b.top || a.left - b.left);
  const heroTop = pairs.length ? pairs[0].top : null;
  const heroRow = pairs.filter((p) => heroTop != null && Math.abs(p.top - heroTop) <= 24).map((p) => p.t);

  return {
    cardPresent: titleEl != null,
    subtitle,
    headline,
    heroRow,
    firstPercents: pairs.slice(0, 8),
    hasLive: /\bLive\b/i.test(text),
    hasFinal: /\bFinal\b/i.test(text),
    percents: [...new Set(text.match(/[<>]?\d+%/g) ?? [])].slice(0, 14),
  };
});

console.log(`mode=${mode} fulfilled=${fulfilled} deployment=${deployment}`);
console.log(`live-chrome=${read.hasLive} final-chrome=${read.hasFinal}`);
console.log(`margin-map present=${read.cardPresent} subtitle=${JSON.stringify(read.subtitle)}`);
console.log(`MARGIN MAP HEADLINE: ${JSON.stringify(read.headline)}`);
console.log(`HERO ROW (topmost percents): ${JSON.stringify(read.heroRow)}`);
console.log(`first percents by position: ${JSON.stringify(read.firstPercents)}`);
console.log(`percents on page: ${JSON.stringify(read.percents)}`);

if (!read.cardPresent) {
  console.error('NO MARGIN MAP IN THE DOM — not a pass (check the ladder shape, not the fix)');
  await browser.close();
  process.exit(4);
}

// Frame the card itself: the claim is about what this header row prints, so the
// card gets its own shot rather than a promise that it is somewhere below.
const card = page
  .locator('div')
  .filter({ hasText: /^(Margin map|Margin: expected vs final)/ })
  .last();
await card.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(1200);
await page.screenshot({ path: out, fullPage: false });
console.log(`shot ${out}`);

// The hero gets its own frame: the ship is that these two AGREE, and a reader
// cannot see both in one 390px screenful, so the pair of frames is the claim.
const hero = out.replace(/\.png$/, '-hero.png');
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(1200);
await page.screenshot({ path: hero, fullPage: false });
console.log(`shot ${hero}`);

await browser.close();
