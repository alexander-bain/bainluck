// quiet-stall-poll-7621.mjs <eventId> [seconds] [--visible]
//
// #7621 — DOES A LEFT-OPEN EVENT PAGE KEEP ASKING THE SERVER?
//
// ux/1399 measured a page opened once and never reloaded still reading
// "No result reported" thirteen minutes after the final, while a fresh load of
// the same url in the same minute rendered Final. That is a real difference on
// screen, but it does not by itself name a cause, and there are two candidates
// that produce the identical picture:
//
//   (a) THE PRODUCT. The page's poll is running and its result is not reaching
//       the hero — a wiring defect the reader would hit on a phone.
//   (b) THE INSTRUMENT. The page never polled at all because headless Chromium
//       reports `document.visibilityState === "hidden"`, and swr@2.4.1's
//       polling effect is, verbatim:
//
//           if (!getCache().error && (refreshWhenHidden || getConfig().isVisible()) …)
//                revalidate(WITH_DEDUPE).then(next);
//           else next();
//
//       `refreshWhenHidden` is unset app-wide, so a hidden page takes the
//       `else` branch forever. A camera that is structurally invisible to the
//       page cannot photograph the page's polling.
//
// The screenshot cannot tell (a) from (b) — both are a frozen hero — so this
// probe reads the one fact that does: the REQUESTS. It counts calls to
// `/api/events/<id>` on a page held open, and prints the visibility the page
// itself reports, so the two explanations separate.
//
// `--visible` re-runs the same page with `document.visibilityState` forced to
// "visible" (a CDP override, not a monkey-patch of the property, so swr's own
// `isVisible()` reads it through the real API). Running both arms is the
// point: one arm alone proves nothing, because "no requests while hidden" is
// the EXPECTED and correct behaviour, not a defect.
//
// Exit 0 always — this measures, it does not grade.

import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';

// Same resolution `shop-shot.mjs` uses: playwright lives in the npx cache the
// LOOK tooling warms, not in any package.json this file can see.
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

const eventId = process.argv[2];
const seconds = parseInt(process.argv[3] || '200', 10);
const forceVisible = process.argv.includes('--visible');
if (!eventId) {
  console.error('usage: quiet-stall-poll-7621.mjs <eventId> [seconds] [--visible]');
  process.exit(2);
}

const url = `https://bainluck.com/events/${eventId}`;
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy;
const args = ['--single-process', '--no-sandbox', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ args });
const t0 = Date.now();
const hits = [];
try {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    extraHTTPHeaders: { 'x-bainluck-origin': 'ux-probe-7621' },
  });
  const page = await context.newPage();

  if (forceVisible) {
    // Emulate a foregrounded tab at the protocol level. `Emulation.setFocusEmulationEnabled`
    // makes Chromium report the page as focused+visible to the renderer, which is what
    // `document.visibilityState` and therefore swr's `isVisible()` read — as opposed to
    // redefining the property in page script, which swr would still bypass via the real
    // visibilitychange path and which would not un-throttle the timers.
    const cdp = await context.newCDPSession(page);
    await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true });
  }

  // Count only the EVENT payload — the one request whose absence freezes the hero.
  // Sibling fetches (history, markets) kept landing in ux/1399's capture, which is
  // exactly why the page looked alive, so counting "any request" would answer the
  // wrong question.
  const eventRe = new RegExp(`/api/events/${eventId}(?:[?#]|$)`);
  // CONTROL, and it is not optional: "the event endpoint was never re-requested"
  // and "my regex matches nothing" produce the identical count of zero. Every
  // other `/api/` path is tallied beside it, so a page that is demonstrably
  // still talking to the server proves the camera is recording and isolates the
  // silence to the one key that matters.
  const allApi = new Map();
  page.on('request', (req) => {
    const u = req.url();
    if (!u.includes('/api/')) return;
    const at = Math.round((Date.now() - t0) / 1000);
    if (eventRe.test(u)) hits.push(at);
    const path = u.replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    if (!allApi.has(path)) allApi.set(path, []);
    allApi.get(path).push(at);
  });

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);

  const seen = await page.evaluate(() => ({
    visibility: document.visibilityState,
    hasFocus: document.hasFocus(),
    hidden: document.hidden,
  }));

  const deadline = Date.now() + seconds * 1000;
  let lastReport = 0;
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    const el = Math.round((Date.now() - t0) / 1000);
    if (el - lastReport >= 30) {
      console.error(`  t+${el}s  event-requests=${hits.length}`);
      lastReport = el;
    }
  }

  const heroText = await page.evaluate(() => document.body.innerText.slice(0, 400));

  console.log(JSON.stringify({
    url,
    arm: forceVisible ? 'FOCUS-EMULATED (visible)' : 'AS-SHOT (default headless)',
    reportedByPage: seen,
    heldOpenSeconds: seconds,
    eventRequestCount: hits.length,
    eventRequestsAtSeconds: hits,
    allApiPathsByRequestSeconds: Object.fromEntries(
      Array.from(allApi.entries()).sort((a, b) => b[1].length - a[1].length),
    ),
    firstScreenText: heroText.replace(/\n+/g, ' | ').slice(0, 300),
  }, null, 2));
} finally {
  await browser.close();
}
