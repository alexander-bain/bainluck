// mnf-live-walk-1426.mjs — the notice-42 live marquee walk, run unattended. (ux, #4460 / notice 42)
//
// ── WHY THIS EXISTS ─────────────────────────────────────────────────────────────────────────
// The MNF walk has been owed across three sessions, each of which ran out of clock rather than
// out of will: kickoff-to-final-plus-ten is ~4 hours and a lane session is not. A background task
// dies with its session (notice 17), so this is `setsid nohup`'d and acts by writing FRAMES AND
// JSON TO DISK — whichever session is alive reads them. It never tries to wake anybody.
//
// 🔴 THE ONE THING A LOOP OF `look.sh` CANNOT DO is the check notice 42 actually names: "10 minutes
// after the final WITHOUT refreshing". Every fresh load is a new page, so a reload-based walk can
// only ever prove that a NEW reader sees the final — never that the reader who was already sitting
// there sees it. So this holds ONE page open from kickoff to the end and shoots from that same
// instance, and takes a fresh-load frame beside it for contrast. Two readers, one game:
//   HELD  — opened once at kickoff, never reloaded. The no-refresh transition evidence.
//   FRESH — a new load each cycle. What somebody arriving at that minute sees.
// A disagreement between them at the same minute is the finding, and it is invisible to either
// one alone.
//
// Completion is read from the API, never from the held page — asking the page would mean touching
// it, and the whole value of the held page is that nothing touched it.
//
// Usage: node mnf-live-walk-1426.mjs <eventId> <outDir> [kickoffISO]
// Exit:  0 walk completed · 2 bad usage · 4 the held page never rendered a chart
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, writeFileSync, appendFileSync } from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';
const execFileAsync = promisify(execFile);

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
const outDir = process.argv[3];
const kickoffISO = process.argv[4] || null;
if (!eventId || !outDir) {
  console.error('usage: mnf-live-walk-1426.mjs <eventId> <outDir> [kickoffISO]');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const URL = `https://bainluck.com/events/${eventId}`;
const API = `https://api.bainluck.com/api/events/${eventId}`;
const WIDTH = 390, HEIGHT = 844;
const CYCLE_MS = 20 * 60 * 1000;      // notice 42: "every ~20 minutes"
const AFTER_FINAL_MS = 10 * 60 * 1000; // notice 42: "10 minutes after the final"
const MAX_MS = 6 * 60 * 60 * 1000;     // a hung game must not hold the camera open forever

const log = (m) => {
  const line = `${new Date().toISOString().slice(11, 19)}Z ${m}`;
  console.log(line);
  appendFileSync(`${outDir}/walk.log`, line + '\n');
};
const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));

// 🔴 NOT `fetch`. Node's global fetch ignores HTTPS_PROXY, and in this sandbox every request it
// makes dies as a bare `TypeError: fetch failed` — which this function would have folded into
// `{error}`, so the walk would have polled a dead instrument for six hours and never fired the
// final frames. Measured on the 21:44Z smoke run. `curl` honours the proxy, so shell out to it.
async function state() {
  try {
    const { stdout } = await execFileAsync('curl', [
      '-s', '--max-time', '20', '-H', `x-bainluck-origin: ${process.env.BL_AGENT || 'ux'}`, API,
    ], { maxBuffer: 64 * 1024 * 1024 });
    if (!stdout.trim()) return { error: 'empty body' };
    const d = JSON.parse(stdout);
    return {
      status: d.status, home_score: d.home_score, away_score: d.away_score,
      completed_at: d.completed_at, period: d.period ?? null, clock: d.clock ?? null,
    };
  } catch (e) { return { error: String(e).slice(0, 120) }; }
}

/** What the chart and hero actually say, read off a page instance. Kept small and comparable so
 *  two frames from different readers can be diffed without opening the PNGs. */
const READ = () => {
  const w = document.querySelector('.recharts-wrapper');
  const lines = w ? [...w.querySelectorAll('.recharts-line-curve')].map((p) => {
    const d = p.getAttribute('d') || '';
    const pts = [...d.matchAll(/([-\d.]+),([-\d.]+)/g)];
    return { stroke: (p.getAttribute('stroke') || '').toLowerCase(), vertices: pts.length };
  }) : [];
  const xTicks = w ? [...w.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map((t) => t.textContent.trim()) : [];
  const refLabels = w ? [...w.querySelectorAll('.recharts-reference-line text')].map((t) => t.textContent.trim()) : [];
  const btns = [...document.querySelectorAll('button')].map((b) => ({
    text: (b.innerText || '').trim().slice(0, 24), disabled: b.disabled,
  })).filter((b) => /^(All|Since Start|1W|1M|Full Game)$/i.test(b.text));
  return {
    chartPresent: !!w,
    lines, totalVertices: lines.reduce((n, l) => n + l.vertices, 0),
    xFirst: xTicks[0] ?? null, xLast: xTicks[xTicks.length - 1] ?? null, xCount: xTicks.length,
    refLabels, rangeButtons: btns,
    bodyHead: document.body.innerText.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 24),
  };
};

/** The consent banner is fixed-position and sits over the bottom third of the page, so on an
 *  un-dismissed page it covers whatever the shot was aimed at. Dismissed once per page, right
 *  after load — a walk whose every frame has a cookie card stapled across it is not a LOOK. */
async function dismissConsent(page) {
  try {
    const b = page.locator('button', { hasText: /^(Accept|Accept all)$/i }).first();
    if (await b.count()) { await b.click({ timeout: 4000 }); await page.waitForTimeout(600); return true; }
  } catch { /* absent once the cookie is set; that is a result, not an error */ }
  return false;
}

async function shoot(page, tag, label) {
  try {
    // Aim at the CHART, not at a pixel offset. The offset that framed it on one build lands on
    // "Margin maps" on the next; `scrollIntoView` survives the page growing above it.
    await page.evaluate(() => {
      const w = document.querySelector('.recharts-wrapper');
      if (w) w.scrollIntoView({ block: 'center' }); else window.scrollTo(0, 700);
    });
    await page.waitForTimeout(1200);
    const read = await page.evaluate(READ);
    const png = `${outDir}/${tag}.png`;
    await page.screenshot({ path: png });
    writeFileSync(`${outDir}/${tag}.json`, JSON.stringify({ tag, label, at: new Date().toISOString(), url: URL, ...read }, null, 2));
    log(`  ${label}: chart=${read.chartPresent} vertices=${read.totalVertices} x=[${read.xFirst}..${read.xLast}] markers=${JSON.stringify(read.refLabels)} range=${JSON.stringify(read.rangeButtons)}`);
    return read;
  } catch (e) { log(`  ${label}: SHOT FAILED ${String(e).slice(0, 140)}`); return null; }
}

/** A fresh reader, in its OWN throwaway browser, that cannot take the walk down with it: a failed
 *  load costs one frame, never the held page — the only thing here that cannot be re-created. */
async function freshShot(tag, label) {
  let b = null;
  try {
    b = await chromium.launch({ headless: true, args });
    const fr = await b.newPage({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1 });
    await fr.goto(URL, { waitUntil: 'networkidle', timeout: 90000 });
    await fr.waitForTimeout(2500);
    await dismissConsent(fr);
    await shoot(fr, tag, label);
  } catch (e) {
    log(`  ${label}: FRESH load failed ${String(e).slice(0, 140)}`);
  } finally {
    if (b) { try { await b.close(); } catch { /* already gone */ } }
  }
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
// 🔴 TWO BROWSERS, NOT TWO TABS — and neither half of that is optional here.
// Under `--single-process` the second `newPage()` kills the whole browser ("Target page, context
// or browser has been closed"); WITHOUT `--single-process` this sandbox will not launch Chromium
// at all. Both measured, 21:46Z and 21:48Z. So the held reader keeps its own browser for the whole
// walk and every fresh reader gets a throwaway one. Worth stating because both catch blocks would
// have swallowed the first failure into a log line: the walk would have run four hours and banked
// HELD frames only, losing exactly the FRESH-vs-HELD comparison it exists to make.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

if (kickoffISO) {
  const wait = new Date(kickoffISO).getTime() - Date.now();
  if (wait > 0) { log(`waiting ${Math.round(wait / 60000)} min for kickoff ${kickoffISO}`); await sleep(wait); }
}

const browser = await chromium.launch({ headless: true, args });

// THE HELD READER. Opened once. Never reloaded, never navigated, not even asked whether the game
// ended — that question goes to the API.
const held = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1 });
await held.goto(URL, { waitUntil: 'networkidle', timeout: 90000 });
await held.waitForTimeout(2500);
const heldConsent = await dismissConsent(held);
log(`HELD page opened at ${URL} (consent dismissed: ${heldConsent})`);

const first = await shoot(held, 'c00-held-kickoff', 'HELD @ kickoff');
if (!first || !first.chartPresent) log('⚠️  held page rendered no chart at kickoff — continuing, the frames still record it');

const started = Date.now();
let cycle = 0, finalSeen = null, lastState = null;

while (Date.now() - started < MAX_MS) {
  const s = await state();
  lastState = s;
  log(`state: ${JSON.stringify(s)}`);

  // No `&& !finalSeen` guard: this block ends in `break`, so the loop cannot come back round with
  // it set, and CodeQL (js/trivial-conditional) correctly read the negation as always-true. The
  // `break` IS the guard; `finalSeen` survives only to stamp the summary.
  if (s.status === 'completed' || s.completed_at) {
    finalSeen = Date.now();
    log('FINAL detected — shooting held + fresh, then holding 10 min WITHOUT refreshing');
    await shoot(held, 'f1-held-at-final', 'HELD @ final (never reloaded)');
    await freshShot('f2-fresh-at-final', 'FRESH @ final');

    await sleep(AFTER_FINAL_MS);
    await shoot(held, 'f3-held-final-plus-10', 'HELD @ final+10 (still never reloaded)');
    await freshShot('f4-fresh-final-plus-10', 'FRESH @ final+10');
    break;
  }

  cycle += 1;
  const tag = `c${String(cycle).padStart(2, '0')}`;
  await shoot(held, `${tag}-held`, `HELD cycle ${cycle}`);
  await freshShot(`${tag}-fresh`, `FRESH cycle ${cycle}`);

  await sleep(CYCLE_MS);
}

writeFileSync(`${outDir}/walk-summary.json`, JSON.stringify({
  eventId, url: URL, startedAt: new Date(started).toISOString(),
  endedAt: new Date().toISOString(), cycles: cycle,
  finalDetectedAt: finalSeen ? new Date(finalSeen).toISOString() : null,
  timedOut: !finalSeen, lastState,
}, null, 2));
log(`walk finished — cycles=${cycle} finalSeen=${!!finalSeen}`);
await browser.close();
process.exit(0);
