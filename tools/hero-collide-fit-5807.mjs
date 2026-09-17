// hero-collide-fit-5807.mjs — can the event hero survive a colliding team pair? (#5807)
//
// #5807's specimen (Southeastern Louisiana Lions v North Alabama Lions, live, 390px) has
// completed, and production carries no live fixture of that shape today: every colliding pair
// on the wire is soccer, and the longest is `Hapoel Ramat Gan Givatayim FC` on a page with no
// movement chip. A defect whose population is seasonal has no natural specimen, so this
// MANUFACTURES one — it serves a real live event's real payload with two fields replaced.
//
// It is `tools/hero-clip-probe.mjs`'s measurement (same anchor, same three-child flex row, same
// budget/used/headroom triple) against a LOCAL build, plus the two things that probe cannot see
// because production never renders them together:
//
//   * `nameWrapLines` — a team label broken over N lines is the reader's real complaint on the
//     filed frame ("wrapped over three lines"), and it costs no horizontal pixels, so
//     `awayOffscreenPx` stays 0 while the card gets taller and worse.
//   * `chipClippedPx` — the `{team} 65% → 69% since open` sentence's own overflow past its
//     column, which is what "sinc…" in the filed frame is.
//
// PASS = awayColumnPresent AND awayOffscreenPx === 0 AND headroomPx >= 0 AND chipClippedPx === 0.
//
// Usage: node hero-collide-fit-5807.mjs <baseUrl> <eventId> <scenarioJson> [widthPx]
//   scenarioJson: {"home":"...","away":"...","homeProb":0.69,"openingHomeProb":0.65}
//   e.g. node tools/hero-collide-fit-5807.mjs http://localhost:3311 15312049 \
//          '{"home":"Southeastern Louisiana Lions","away":"North Alabama Lions",
//            "homeProb":0.69,"openingHomeProb":0.65}'
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
import { execFile } from 'child_process';

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

const baseUrl = process.argv[2];
const eventId = process.argv[3];
const scenario = JSON.parse(process.argv[4] || '{}');
const width = Number(process.argv[5] || 390);
if (!baseUrl || !eventId) {
  console.error('usage: hero-collide-fit-5807.mjs <baseUrl> <eventId> <scenarioJson> [widthPx]');
  process.exit(2);
}

// The page fetches api.bainluck.com from the BROWSER, and a local origin cannot: the response
// carries no CORS header for localhost and the page renders "Couldn't reach the server". Neither
// can `route.fetch()` — it runs on the Playwright driver, outside the sandbox's proxy, and EPERMs.
// `curl` in a child process is the one route that reaches the API, so every API request is served
// by shelling out and fulfilled with an open CORS header. (ux/1312 paid for all three.)
const curlJson = (url) =>
  new Promise((resolve) => {
    execFile('curl', ['-sS', '--max-time', '30', url], { maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => {
      resolve(err ? null : stdout);
    });
  });

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const localTarget = /localhost|127\.0\.0\.1/.test(baseUrl);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!localTarget) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 1000 }, deviceScaleFactor: 2 });

// A no-match and a failed fetch present as the same empty page, so both are counted and printed.
let apiSeen = 0;
let apiFailed = 0;
let patched = 0;
await page.route(
  (u) => u.hostname === 'api.bainluck.com',
  async (route) => {
    apiSeen += 1;
    const url = route.request().url();
    const body = await curlJson(url);
    if (body === null) {
      apiFailed += 1;
      return route.fulfill({ status: 502, body: '{}', headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' } });
    }
    let out = body;
    // Only the event detail document is rewritten. Everything else — markets, history, the
    // register — is the venue's own answer, untouched, so the page around the hero is real.
    if (new URL(url).pathname === `/api/events/${eventId}`) {
      try {
        const d = JSON.parse(body);
        if (scenario.home) d.home_team = scenario.home;
        if (scenario.away) d.away_team = scenario.away;
        if (scenario.homeProb != null) {
          d.current_odds = { ...(d.current_odds || {}), home_probability: scenario.homeProb, home_rendered_percent: null, away_probability: 1 - scenario.homeProb, away_rendered_percent: null };
          d.hero_probability = scenario.homeProb;
          d.hero_probability_away = 1 - scenario.homeProb;
        }
        if (scenario.openingHomeProb != null) {
          d.opening_odds = { ...(d.opening_odds || {}), home_probability: scenario.openingHomeProb, away_probability: 1 - scenario.openingHomeProb };
        }
        out = JSON.stringify(d);
        patched += 1;
      } catch { /* leave the real body alone rather than serve a broken one */ }
    }
    return route.fulfill({ status: 200, body: out, headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' } });
  },
);

await page.goto(`${baseUrl}/events/${eventId}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForSelector('[data-testid="event-hero-probability"], [data-testid="settled-outcome-hero"]', { timeout: 60000 }).catch(() => {});
await page.waitForTimeout(4000);

const out = await page.evaluate(() => {
  const r2 = (n) => Math.round(n * 10) / 10;
  const vw = document.documentElement.clientWidth;

  const anchor = document.querySelector('[data-testid="event-hero-probability"]')
    || document.querySelector('[data-testid="settled-outcome-hero"]');
  if (!anchor) return { viewportWidth: vw, heroRowFound: false, reason: 'no hero anchor' };

  let row = anchor;
  while (row && row !== document.body) {
    const cs = getComputedStyle(row);
    if (row.children.length === 3 && cs.display === 'flex' && cs.flexDirection === 'row') break;
    row = row.parentElement;
  }
  if (!row || row === document.body) return { viewportWidth: vw, heroRowFound: false, reason: 'no 3-child flex row above the anchor' };

  const rb = row.getBoundingClientRect();
  const raw = [...row.children].map((k) => k.getBoundingClientRect());
  const col = (i) => ({
    w: r2(raw[i].width), left: r2(raw[i].left), right: r2(raw[i].right),
    flex: getComputedStyle(row.children[i]).flex,
    text: (row.children[i].textContent || '').trim().slice(0, 80),
  });
  const [home, centre, away] = [0, 1, 2].map(col);

  // How many lines did each team label take? `Range.getClientRects()` over the text node gives one
  // rect per rendered line, which is the only way to see a wrap — the element's own rect is a
  // single box whatever it contains.
  const lineCount = (el) => {
    if (!el) return null;
    const r = document.createRange();
    r.selectNodeContents(el);
    const tops = new Set([...r.getClientRects()].map((k) => Math.round(k.top)));
    return tops.size || null;
  };
  const nameEl = (colEl) => colEl.querySelector('a[href*="/team/"]') || colEl.querySelector('a');
  const homeNameLines = lineCount(nameEl(row.children[0]));
  const awayNameLines = lineCount(nameEl(row.children[2]));

  // The `{team} 65% → 69% since open` sentence. Found by its own text so the probe does not depend
  // on a class name that a fix is allowed to change.
  const chip = [...row.children[1].querySelectorAll('span')]
    .find((s) => /since open/.test(s.textContent || ''));
  const chipRect = chip ? chip.getBoundingClientRect() : null;
  const centreRect = raw[1];
  const chipClippedPx = chipRect
    ? r2(Math.max(0, chipRect.right - centreRect.right) + Math.max(0, centreRect.left - chipRect.left))
    : 0;

  const budget = rb.width - raw[0].width - raw[2].width;
  return {
    viewportWidth: vw,
    heroRowFound: true,
    rowWidth: r2(rb.width), rowRight: r2(rb.right),
    home, centre, away,
    homeNameLines, awayNameLines,
    awayColumnPresent: (row.children[2].textContent || '').trim().length > 0,
    chipText: chip ? (chip.textContent || '').trim() : null,
    chipWidthPx: chipRect ? r2(chipRect.width) : null,
    chipClippedPx,
    centreBudgetPx: r2(budget),
    centreUsedPx: r2(raw[1].width),
    headroomPx: r2(budget - raw[1].width),
    awayOffscreenPx: r2(Math.max(0, raw[2].right - vw)),
    heroHeightPx: r2(rb.height),
    docScrollWidth: document.documentElement.scrollWidth,
  };
});

if (process.env.SHOT) {
  await page.screenshot({ path: process.env.SHOT, clip: { x: 0, y: 0, width, height: Number(process.env.SHOT_H || 700) } });
  out.screenshot = process.env.SHOT;
}
out.apiRequestsSeen = apiSeen;
out.apiRequestsFailed = apiFailed;
out.eventDocumentsPatched = patched;
console.log(JSON.stringify(out, null, 1));
await browser.close();
const pass = out.heroRowFound && out.awayColumnPresent && out.awayOffscreenPx === 0
  && out.headroomPx >= 0 && out.chipClippedPx === 0;
process.exit(pass ? 0 : 1);
