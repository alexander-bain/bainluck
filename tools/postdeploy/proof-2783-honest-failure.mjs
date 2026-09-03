// proof-2783-honest-failure.mjs — the deployed event page names its failure honestly (#2783).
//
// WHY NOT A COLD-LOAD BATTERY. The reported symptom ("1 blank in 10") was the rig's own
// rate limiting: ~22 requests per event load against a 60/minute production cap. Paced under
// the cap, production renders 20/20. So a cold-load battery measures the PREMISE and cannot
// see the FIX — the fix only shows up when a load actually fails.
//
// So force the failure instead of waiting for it, and force it deterministically: intercept
// `/api/events/{id}` on the live page and answer with the exact status and body production
// sends. That exercises the REAL DEPLOYED BUNDLE — this is not a jest render — while putting
// no extra load on production and rate-limiting nobody else on this box.
//
// Three arms, and the 404 control is the one that matters: a fix that renames every failure
// would also rename the one failure that really is "not found", and that regression is
// invisible if you only assert the 429.
//
// Usage: node tools/postdeploy/proof-2783-honest-failure.mjs [event-url]
// Exit 0 = all arms pass. Exit 1 = a rendered assertion failed. Exit 2 = the rig broke.
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

const URL = process.argv[2] || 'https://www.bainluck.com/events/15293206';

// Exactly what production sends, so the message arm proves the server's own words survive
// rather than proving a string this file invented.
const ARMS = [
  {
    name: '429 — throttled',
    status: 429,
    body: { detail: 'Rate limit exceeded: 60/minute' },
    mustShow: ['Too many requests', 'Rate limit exceeded: 60/minute'],
    mustNotShow: ['Event not found'],
    wantRetry: true,
  },
  {
    name: '500 — server fault',
    status: 500,
    body: { detail: 'Internal Server Error' },
    mustShow: ["Couldn't load this event"],
    mustNotShow: ['Event not found'],
    wantRetry: true,
  },
  {
    // CONTROL. A real 404 must still say not found, and must still offer no retry — reloading
    // a 404 reloads a 404. If this arm goes green only because everything now says the same
    // thing, the fix went one condition too wide.
    name: '404 — genuinely absent (CONTROL)',
    status: 404,
    body: { detail: 'Event not found' },
    mustShow: ['Event not found'],
    mustNotShow: ['Too many requests', "Couldn't load this event", "Couldn't reach the server"],
    wantRetry: false,
  },
];

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const eventId = URL.split('/').pop();
// Only the event's OWN detail call. The sibling rails are left alone so the page fails the way
// it does in life, with one call down rather than the whole API blacked out.
//
// An exact pathname comparison, NOT a regex built from `eventId`. `eventId` comes from argv, so
// a regex made from it is both injectable and — because `.` is a metacharacter — quietly wider
// than it reads (CodeQL js/regex-injection + js/incomplete-hostname-regexp, both correct). A
// string equality cannot be either, and it is what the check actually means.
const TARGET_PATH = `/api/events/${eventId}`;

let failures = 0;

for (const arm of ARMS) {
  // A FRESH BROWSER PER ARM, not a fresh context. `--single-process` is what makes Chromium
  // survivable in this sandbox, and under it closing a context tears down the whole browser —
  // so a shared instance dies after arm one and the remaining arms report a rig crash rather
  // than a verdict.
  const browser = await chromium.launch({ headless: true, args });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  let intercepted = 0;

  await page.route('**/api/events/**', async (route) => {
    // Query strings are ignored on purpose: `?hours=48` is the history rail, a different call
    // on a path of its own, so pathname equality already excludes it.
    if (new global.URL(route.request().url()).pathname !== TARGET_PATH) {
      return route.continue();
    }
    intercepted += 1;
    await route.fulfill({
      status: arm.status,
      contentType: 'application/json',
      body: JSON.stringify(arm.body),
    });
  });

  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(6000);

  const text = (await page.locator('body').innerText().catch(() => '')) || '';
  const buttons = (await page.locator('button').allInnerTexts().catch(() => [])).join(' | ');
  const hasRetry = /try again|retry/i.test(buttons);

  const problems = [];
  // A rig that intercepted nothing proves nothing — it would report a healthy page as a pass.
  if (intercepted === 0) problems.push('RIG: intercepted 0 requests — the fetch never happened');
  for (const s of arm.mustShow) if (!text.includes(s)) problems.push(`missing: "${s}"`);
  for (const s of arm.mustNotShow) if (text.includes(s)) problems.push(`present but must not be: "${s}"`);
  if (hasRetry !== arm.wantRetry) problems.push(`retry button: got ${hasRetry}, want ${arm.wantRetry}`);

  const ok = problems.length === 0;
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${arm.name}  (intercepted=${intercepted}, retry=${hasRetry})`);
  console.log(`      rendered: ${JSON.stringify(text.replace(/\s+/g, ' ').trim().slice(0, 160))}`);
  for (const p of problems) console.log(`      ✗ ${p}`);

  await browser.close();
}

console.log(`\n${ARMS.length - failures}/${ARMS.length} arms passed against ${URL}`);
process.exit(failures === 0 ? 0 : 1);
