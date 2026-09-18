// ux1335-wire-6948-history-range.mjs — #6948: what does the event page actually PUT ON THE WIRE?
//
// The unit guards state the rule; they cannot see the wiring. This drives a real browser against a
// real build and reads the only thing that cannot be argued with: the `/history` requests the page
// issues, in order, with their query strings.
//
// It asserts the whole of the ship:
//   1. FIRST PAINT sends `range=since_start` — exactly once, no duplicate (the boot URL and the
//      app's URL agree, which is LAT-P171/P172's failure mode).
//   2. Tapping "All" issues a SECOND request WITHOUT the parameter — the deferral is lossless only
//      if the head can still be asked for.
//   3. It then SETTLES. A third request on the same range would be the oscillation the one-way
//      latch exists to prevent, and no unit test of a pure function can prove the component wired
//      it that way.
//   4. The chart still draws after the tap (keepPreviousData — a tap that ADDS points must not
//      blank the chart to its skeleton).
//
// Usage: node tools/ux1335-wire-6948-history-range.mjs <baseUrl> <eventId>
// Exit 0 = PASS · 1 = FAIL · 2 = UNPAID (could not reach the subject — proves nothing either way)
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

const [baseUrl, eventId] = process.argv.slice(2);
if (!baseUrl || !eventId) {
  console.error('usage: ux1335-wire-6948-history-range.mjs <baseUrl> <eventId>');
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  // 🔴 `<-loopback>` REMOVES Chrome's built-in localhost bypass, so the house spelling sends
  // 127.0.0.1 to the proxy and the page never loads — which this probe reports as "subject not
  // reached", i.e. indistinguishable from a broken build. Against a local serve the app still has
  // to reach api.bainluck.com through the proxy, so the proxy stays ON and only loopback is exempt.
  const local = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(baseUrl);
  args.push(`--proxy-server=${proxy}`);
  args.push(local ? '--proxy-bypass-list=localhost;127.0.0.1' : '--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

// ── SERVING api.bainluck.com TO A LOCAL BUILD ─────────────────────────────────────────────────
// A local serve is the only way to exercise a build that is not deployed yet, and the browser
// cannot call the production API from a `http://localhost` origin: the API's CORS allowlist does
// not carry it, so every call dies as `net::ERR_FAILED`. That is indistinguishable from a broken
// build, and `apiFetch` retries twice, so it also inflates the request count and reads like a
// fetch loop. (Both of those misread this probe before the bridge existed.)
//
// So node fetches the REAL production payload — same URL, same query string, so the real route
// does the real trimming — and fulfils the browser's request with it. Only the transport is
// substituted; nothing about the payload or the component's behaviour is modelled.
if (/^https?:\/\/(localhost|127\.0\.0\.1)/.test(baseUrl)) {
  const { execFile } = await import('child_process');
  const { promisify } = await import('util');
  const run = promisify(execFile);
  await page.route('**://api.bainluck.com/**', async (route) => {
    try {
      // curl, not node's fetch: it honours the sandbox's HTTPS_PROXY the way every other tool here
      // does, and the payloads run to megabytes.
      const { stdout } = await run('curl', ['-s', '--max-time', '60', route.request().url()], {
        maxBuffer: 256 * 1024 * 1024,
      });
      await route.fulfill({
        status: 200,
        headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
        body: stdout,
      });
    } catch (e) {
      await route.abort();
    }
  });
}

const historyCalls = [];
page.on('request', (req) => {
  const u = req.url();
  if (/\/api\/events\/\d+\/history/.test(u)) {
    historyCalls.push(u);
    console.log(`   wire: ${u.replace(/^https?:\/\/[^/]+/, '')}`);
  }
});

let exitCode = 0;
const fail = (msg) => { console.log(`🔴 FAIL: ${msg}`); exitCode = 1; };

try {
  console.log(`\n== loading ${baseUrl}/events/${eventId} at 390px ==`);
  await page.goto(`${baseUrl}/events/${eventId}`, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForTimeout(3000);

  if (historyCalls.length === 0) {
    console.log('\n⚠️  UNPAID: the page issued no /history request at all — subject not reached.');
    await browser.close();
    process.exit(2);
  }

  // ── 1. FIRST PAINT ──────────────────────────────────────────────────────────────────────────
  const firstPaint = [...historyCalls];
  console.log(`\n1. first paint: ${firstPaint.length} /history request(s)`);
  const trimmed = firstPaint.filter((u) => u.includes('range=since_start'));
  const untrimmed = firstPaint.filter((u) => !u.includes('range=since_start'));

  if (trimmed.length !== 1) fail(`expected exactly 1 trimmed request on first paint, got ${trimmed.length}`);
  else console.log('   ✅ sends range=since_start exactly once');

  if (untrimmed.length !== 0) {
    fail(`first paint also asked for the FULL body ${untrimmed.length}x — the saving is gone and this is a duplicate fetch`);
    untrimmed.forEach((u) => console.log(`      ${u}`));
  } else console.log('   ✅ no un-parameterized request on first paint (no duplicate)');

  // Is this specimen even capable of proving anything? A payload that omitted nothing cannot
  // exercise the re-fetch, and calling that a pass is how a broken fix gets signed off.
  //
  // Asked from NODE, not from the page: a `page.evaluate` fetch is itself a request and lands in
  // the wire log this probe is counting, which made an earlier run report a phantom extra call.
  const { execFile: ex2 } = await import('child_process');
  const { promisify: p2 } = await import('util');
  const run2 = p2(ex2);
  const { stdout: specimenJson } = await run2(
    'curl',
    ['-s', '--max-time', '60', `https://api.bainluck.com/api/events/${eventId}/history?hours=48&range=since_start`],
    { maxBuffer: 256 * 1024 * 1024 }
  );
  const specimenBody = JSON.parse(specimenJson);
  const probe = {
    omitted: specimenBody.pre_window_omitted,
    points: (specimenBody.history || []).length,
  };
  console.log(`   specimen: pre_window_omitted=${probe.omitted}, trimmed points=${probe.points}`);
  if (probe.omitted !== true) {
    console.log('\n⚠️  UNPAID: this event omits nothing, so the "All" re-fetch is correctly a no-op here.');
    console.log('   That is the scheduled-game cohort — it proves the no-duplicate arm and nothing else.');
    await browser.close();
    process.exit(exitCode === 0 ? 2 : 1);
  }

  // ── 2. THE TAP ──────────────────────────────────────────────────────────────────────────────
  const before = historyCalls.length;
  const allBtn = page.getByRole('button', { name: 'All', exact: true }).first();
  if (await allBtn.count() === 0) {
    // Distinguish "the chart never rendered" from "the control is missing", because a local serve
    // whose JS chunks 400 (a stale `next start` against a fresh build) looks exactly like the
    // latter and is really the former.
    const anyBtn = (await page.locator('button').allTextContents()).filter((t) => t.trim());
    console.log('\n⚠️  UNPAID: no "All" control found on the page.');
    console.log(`   buttons present: ${JSON.stringify(anyBtn.slice(0, 12))}`);
    console.log('   (only nav buttons here means the app never hydrated — check the server build.)');
    await browser.close();
    process.exit(2);
  }
  console.log('\n2. tapping "All"');
  await allBtn.click();
  await page.waitForTimeout(6000);

  const afterTap = historyCalls.slice(before);
  console.log(`   ${afterTap.length} new /history request(s) after the tap`);
  const refetch = afterTap.filter((u) => !u.includes('range='));
  if (refetch.length !== 1) {
    fail(`expected exactly 1 un-parameterized re-fetch after the tap, got ${refetch.length} — ` +
         `${refetch.length === 0 ? 'the reader is looking at a SHORTENED "All"' : 'this is re-fetching'}`);
  } else console.log('   ✅ re-fetched WITHOUT the range parameter — the head can still be asked for');

  // ── 3. IT SETTLES ───────────────────────────────────────────────────────────────────────────
  const settleMark = historyCalls.length;
  await page.waitForTimeout(8000);
  const extra = historyCalls.length - settleMark;
  console.log(`\n3. settling: ${extra} further /history request(s) in 8s`);
  if (extra > 0) {
    fail(`the page kept fetching after the re-fetch — this is the oscillation the latch must prevent`);
    historyCalls.slice(settleMark).forEach((u) => console.log(`      ${u}`));
  } else console.log('   ✅ settled — the latch held');

  // ── 4. THE CHART IS STILL DRAWN ─────────────────────────────────────────────────────────────
  const paths = await page.locator('svg .recharts-line-curve, svg path.recharts-curve').count();
  console.log(`\n4. chart curves drawn after the tap: ${paths}`);
  if (paths === 0) fail('the chart is blank after the tap — keepPreviousData is not holding the body');
  else console.log('   ✅ chart still drawn');

  await page.screenshot({ path: `/tmp/ux1335-6948-after-all-${eventId}.png`, fullPage: false });
  console.log(`\n   frame: /tmp/ux1335-6948-after-all-${eventId}.png`);
} catch (e) {
  console.log(`\n⚠️  UNPAID: probe threw — ${e.message}`);
  await browser.close();
  process.exit(2);
}

await browser.close();
console.log(exitCode === 0 ? '\n✅ PASS\n' : '\n🔴 FAIL\n');
process.exit(exitCode);
