// blank-event-hunt.mjs — catch the ~1-in-10 cold event-page render that draws nothing (#2783).
//
// WHY IT IS NOT felt-load.mjs. felt-load reports THAT the page stayed empty. It does not say WHY,
// because it captures no console output, no page errors and no DOM. This does: every run records
// every console message, every uncaught error and every unhandled rejection, and the moment a run
// comes back with zero cards it dumps the whole record plus the rendered text and the section
// landmarks it can find.
//
// The measurement in #2783 is not repeated here — the numbers are in the issue. This is a
// diagnostic, and it is deliberately a separate file so the instrument in the latency lane's hands
// is not edited by the lane chasing a bug with it.
//
// Usage: node tools/blank-event-hunt.mjs [url] [runs] [out.json]
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

const URL = process.argv[2] || 'https://www.bainluck.com/events/15293206';
const RUNS = parseInt(process.argv[3] || '20', 10);
const OUT = process.argv[4] || '/tmp/blank-event-hunt.json';
const SETTLE_MS = parseInt(process.env.HUNT_SETTLE_MS || '9000', 10);
// A page load fires ~22 requests at api.bainluck.com, and production rate-limits
// at 60/minute per client. Unpaced, this instrument trips that limit and then
// measures its own throttling — which is exactly the trap #2783 fell into. The
// pace is a first-class parameter for that reason, not a politeness setting.
const PACE_MS = parseInt(process.env.HUNT_PACE_MS || '0', 10);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

// Same card vocabulary felt-load uses, so "cards=0" means the same thing in both instruments.
const CARD_SEL = [
  '[data-testid="discover-card"]',
  'a[href^="/event/"]', 'a[href^="/events/"]', 'a[href^="/futures/"]',
  'a[href^="/sport/"]', 'a[href^="/tournaments/"]', 'a[href^="/categories/"]',
  'a[href^="/hub/"]', 'a[href^="/playoffs/"]',
  'article',
].join(',');

const results = [];

for (let run = 1; run <= RUNS; run++) {
  if (run > 1 && PACE_MS > 0) await new Promise((r) => setTimeout(r, PACE_MS));
  // A FRESH BROWSER per run. A reused context carries the previous run's module registry and
  // React state, and this bug is about a first render.
  const browser = await chromium.launch({ headless: true, args });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  const console_ = [];
  const errors = [];
  page.on('console', (m) => console_.push({ type: m.type(), text: m.text().slice(0, 1200) }));
  page.on('pageerror', (e) => errors.push({ kind: 'pageerror', message: String(e && e.message).slice(0, 2000), stack: String(e && e.stack).slice(0, 4000) }));
  page.on('requestfailed', (r) => errors.push({ kind: 'requestfailed', url: r.url(), failure: r.failure()?.errorText }));
  page.on('response', (r) => { if (r.status() >= 400) errors.push({ kind: 'http', url: r.url(), status: r.status() }); });

  await page.addInitScript(() => {
    window.__HUNT = { rejections: [] };
    window.addEventListener('unhandledrejection', (e) => {
      window.__HUNT.rejections.push(String((e.reason && (e.reason.stack || e.reason.message)) || e.reason).slice(0, 2000));
    });
  });

  await page.goto(URL, { waitUntil: 'commit', timeout: 60000 });

  // Sampled, not just settled. "Never drew a card" and "drew cards and then lost
  // them" are different bugs and the end-state proof cannot tell them apart.
  const timeline = [];
  const t0 = Date.now();
  while (Date.now() - t0 < SETTLE_MS) {
    try {
      timeline.push(
        await page.evaluate((sel) => ({
          t: Math.round(performance.now()),
          cards: document.querySelectorAll(sel).length,
          chars: (document.body.innerText || '').length,
        }), CARD_SEL),
      );
    } catch { /* mid-navigation evaluate */ }
    await page.waitForTimeout(500);
  }

  const proof = await page.evaluate((sel) => {
    const text = (document.body.innerText || '').replace(/\s+/g, ' ').trim();
    const cards = Array.from(document.querySelectorAll(sel)).filter((el) => {
      if (el.closest('.animate-pulse') || el.querySelector('.animate-pulse')) return false;
      if (el.closest('[aria-hidden="true"]')) return false;
      const t = (el.textContent || '').trim();
      if (t.length < 12) return false;
      const r = el.getBoundingClientRect();
      return r.width >= 80 && r.height >= 40;
    });
    // The landmarks that say WHICH part of the page is missing.
    const has = (s) => !!document.querySelector(s);
    return {
      chars: text.length,
      pct: (text.match(/\d+%/g) || []).length,
      cards: cards.length,
      skeletons: document.querySelectorAll('.animate-pulse').length,
      landmarks: {
        spinner: /Loading event/i.test(text),
        errorMessage: /Event not found|Loading timed out|Something went wrong/i.test(text),
        hero: has('[data-testid="event-hero-suspended"]') || /Win Probability|Pregame|LIVE|Final/i.test(text),
        h1: (document.querySelector('h1') || {}).textContent || null,
        headings: Array.from(document.querySelectorAll('h2,h3')).map((h) => (h.textContent || '').trim()).slice(0, 20),
      },
      rejections: (window.__HUNT && window.__HUNT.rejections) || [],
      textHead: text.slice(0, 1500),
    };
  }, CARD_SEL);

  const row = { run, url: URL, ...proof, timeline, console: console_, errors };
  results.push(row);

  const bad = proof.cards === 0;
  // Counted and printed on EVERY row, not just the bad ones. A throttled run that
  // still rendered is the evidence that separates "the rig is over the limit" from
  // "the page dropped data it had".
  const throttled = errors.filter((e) => e.kind === 'http' && e.status === 429).length;
  row.throttled = throttled;
  console.log(`run ${run}/${RUNS} cards=${proof.cards} pct=${proof.pct} chars=${proof.chars} skel=${proof.skeletons} http429=${throttled} errors=${errors.length} rejections=${proof.rejections.length}${bad ? '   <<< BLANK' : ''}`);
  if (bad) {
    console.log('  headings:', JSON.stringify(proof.landmarks.headings));
    console.log('  timeline:', timeline.map((s) => `${s.t}:${s.cards}/${s.chars}`).join(' '));
    console.log('  text:', proof.textHead.slice(0, 900));
    for (const e of errors) console.log('  ERROR', JSON.stringify(e).slice(0, 900));
    for (const r of proof.rejections) console.log('  REJECTION', r.slice(0, 900));
    for (const c of console_) if (c.type === 'error' || c.type === 'warning') console.log(`  CONSOLE.${c.type}`, c.text.slice(0, 900));
  }

  await browser.close();
}

writeFileSync(OUT, JSON.stringify({ url: URL, runs: RUNS, settleMs: SETTLE_MS, results }, null, 2));
const blanks = results.filter((r) => r.cards === 0);
const throttledRuns = results.filter((r) => r.throttled > 0);
console.log(`\n${blanks.length}/${results.length} blank, ${throttledRuns.length}/${results.length} saw a 429. wrote ${OUT}`);
