// ux1326-boundary-callout-probe-6858.mjs <mode> <out.png>
//
// #6858's AFTER-CHECK on the DEPLOYED bundle, against a manufactured specimen.
//
// WHY MANUFACTURED. The defect's population is "a live game whose favourite is
// past the boundary" — a window of minutes per game. At 05:10Z there were 21
// live events on production and not one carried a probability at all, so the
// population is TRANSIENT, not absent (ux/1324's rail).
//
// WHY THIS IS NOT AN INVENTED PAYLOAD. `GET /api/events/15298678` — the game the
// issue was filed off, Aces at Storm — STILL SERVES `home_probability: 0.001`
// today. Only `status` has moved on to `completed`. So the probe fulfils that
// one route with production's own bytes and `status` put back to `live`: the
// specimen is the filed state restored, not a shape someone drew to match a fix.
//
//   MODE `after`    status -> live. The filed condition. The chart's callout
//                   must print the marked below-one form, not a bare 0%.
//   MODE `control`  no interception at all. Production's real completed game,
//                   proving the rig is photographing the real page and that
//                   SETTLED still prints its literal boundary value — the half
//                   of #6858 that must NOT have moved.
//
// Fulfil ONLY the event detail route: catch-all-ing the API renders the page's
// ErrorBoundary, which reads exactly like a crash in the change under test.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 the chart never
// rendered (NOT a pass), 5 the interception never fired, 1 camera/navigation.
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

const EVENT = 15298678;
const URL = `https://bainluck.com/events/${EVENT}`;

// Read from a file the CALLER fetched with curl, not with node's `fetch`: the
// lane sandbox refuses node's egress with EPERM while curl is allowed, and a
// probe that dies before the browser opens looks like a broken probe rather
// than a blocked socket. Fetch it with:
//   curl -s https://api.bainluck.com/api/events/15298678 -o /tmp/ev.json
const payload = JSON.parse(readFileSync(payloadPath, 'utf8'));
console.log(
  `upstream: status=${payload.status} home_probability=${payload.current_odds?.home_probability} ` +
    `away_probability=${payload.current_odds?.away_probability}`,
);
if (payload.current_odds?.home_probability !== 0.001) {
  console.error('SPECIMEN MOVED: the served home_probability is no longer 0.001 — re-read the issue');
  process.exit(4);
}

// Exactly the fields that make production call this game over. Scores, the
// chart's own history, `current_odds` and every source block are untouched.
//
// 🪤 `status` ALONE IS NOT ENOUGH, and the first run of this probe proved it:
// the page came back reading "Final · 10:00" with a `0% – 100%` hero, because
// the hero does not read `current_odds` at all. Settlement rewrote FOUR more
// fields, and each one has to go back to what it held while the game ran:
//
//   hero_probability        0.0  -> 0.001   the hero's own number, and the one
//   hero_probability_away   1.0  -> 0.999   `chartEdgePin` pins the callout to
//   hero_probability_source "settled" -> "blend"   when it is `blend`
//   espn.period             "Final" -> the quarter
//
// `0.001 / 0.999` is not a guess: it is what `current_odds` on this row STILL
// serves today, which is how the filed state is recoverable at all.
const live = {
  ...payload,
  status: 'live',
  completed_at: null,
  hero_settled_result: null,
  started_without_result: false,
  hero_probability: payload.current_odds.home_probability,
  hero_probability_away: payload.current_odds.away_probability,
  hero_probability_source: 'blend',
  espn: { ...(payload.espn ?? {}), period: '4th Quarter', game_clock: '10:00' },
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

// `networkidle` is the wrong wait for a page that re-polls; wait for the chart's
// own heading instead, then settle.
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page
  .getByText('Win Probability', { exact: false })
  .first()
  .waitFor({ state: 'attached', timeout: 60000 });
await page.waitForTimeout(4000);

// The consent banner is anchored over the lower half of the viewport, which is
// exactly where the chart's edge callout sits. The first run of this probe shot
// a hero that proved the ship and a chart hidden behind a cookie notice.
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

// Read the two numbers the issue put in one screenful, by their own text rather
// than by a class: a class is the thing most likely to have moved.
const read = await page.evaluate(() => {
  const text = (document.body.innerText || '').replace(/\s+/g, ' ');
  const chunk = (needle, before, after) => {
    const i = text.indexOf(needle);
    return i < 0 ? null : text.slice(Math.max(0, i - before), i + after);
  };
  return {
    percents: [...new Set(text.match(/[<>]?\d+%/g) ?? [])],
    aroundChart: chunk('Win Probability', 0, 260),
    hasLive: /\bLive\b/i.test(text),
    hasFinal: /\bFinal\b/i.test(text),
  };
});

console.log(`mode=${mode} fulfilled=${fulfilled}`);
console.log(`live-chrome=${read.hasLive} final-chrome=${read.hasFinal}`);
console.log(`percents seen: ${JSON.stringify(read.percents)}`);
console.log(`around the chart: ${read.aroundChart}`);

if (!read.aroundChart) {
  console.error('NO WIN PROBABILITY CHART IN THE DOM — not a pass');
  await browser.close();
  process.exit(4);
}

await page.screenshot({ path: out, fullPage: false });
console.log(`shot ${out}`);

// The issue's claim is about ONE screenful holding both numbers, so the chart
// gets its own frame rather than a promise that it is further down the page.
const chart = out.replace(/\.png$/, '-chart.png');
const card = page
  .locator('div')
  .filter({ hasText: /^Win Probability/ })
  .first();
await card.scrollIntoViewIfNeeded();
await page.waitForTimeout(1500);
await page.screenshot({ path: chart, fullPage: false });
console.log(`shot ${chart}`);

await browser.close();
