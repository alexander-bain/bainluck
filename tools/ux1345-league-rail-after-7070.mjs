// ux1345-league-rail-after-7070.mjs — the AFTER-CHECK for #7070, two modes.
//
// THE CLAIM UNDER TEST. `/sport/tennis/atp` printed "No result reported · Sep
// 18" on six rail cards whose own detail payloads named a winner in the same
// minute, under a heading that said the same thing. The consumer half reads
// `venue_settled`/`venue_settled_result` off the league envelope through
// `venueSettledSummary` — the function the event hero has used since #6381 —
// and reads the rail's heading off the rail's own rows.
//
//   MODE `injected`  payable the moment MY sha is deployed, with or without the
//                    producer. The league payload is fetched for real and the
//                    two keys are added to the FIRST TWO unreported rows only —
//                    so the same frame proves BOTH halves: those two cards name
//                    the winner, the rest still deny, and the heading above a
//                    mixed rail no longer denies. The keys are exactly what PR
//                    #7071 sends; nothing else in the payload is touched.
//   MODE `live`      payable once the producer is released. No interception at
//                    all: the served payload's own graded rows must print their
//                    own verdicts. EXITS 4 (not payable) rather than passing
//                    when no row carries the keys — a producer that has not
//                    shipped is not a fix that works.
//
// 🪤 WHY `injected` IS NOT A FIXTURE. The page, the bundle, the mapper and the
// card are production's; only two keys on two rows are ours, and they are the
// bytes the producer's own test file pins. A jest render cannot see the built
// bundle, a stale CDN copy, or a page that never reaches the suspended branch.
//
// 🪤 NODE'S `fetch` DIES `connect EPERM` IN THE LANE SANDBOX and the error reads
// as "production is down", so every API read here shells out to curl.
//
// EXIT CODES ARE A STORY (gotcha #124):
//   0  pass · 2 usage · 3 THE DEFECT IS ON PRODUCTION · 4 not payable (sha not
//   deployed / no specimen / producer absent in `live` mode — NOT a pass) ·
//   5  the interception never fired · 1 camera or navigation.
//
//   cd ~/bainluck-dev/ux && SHA=<merged sha> node tools/ux1345-league-rail-after-7070.mjs injected
import { createRequire } from 'module';
import { execFileSync } from 'child_process';
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

const mode = process.argv[2];
if (!['injected', 'live'].includes(mode)) {
  console.error('usage: SHA=<sha> node tools/ux1345-league-rail-after-7070.mjs <injected|live>');
  process.exit(2);
}

const LEAGUE_KEY = process.env.LEAGUE_KEY || 'tennis_atp';
const PAGE_PATH = process.env.PAGE_PATH || '/sport/tennis/atp';
const API = 'https://api.bainluck.com';
// `SITE` exists for ONE job: photographing the fix on a local `next start`
// before it is merged. It skips the deployed-commit gate below and says so
// LOUDLY — a local frame is a picture, never an after-check.
//
// 🪤 AND IT DOES NOT WORK IN THE LANE SANDBOX — measured, so nobody re-spends
// the hour. A page served from `localhost` cannot reach `api.bainluck.com` from
// this VM: every XHR returns `net::ERR_ACCESS_DENIED` with the proxy, without
// it, and with every bypass-list shape (`<-loopback>` sends 127.0.0.1 through
// the proxy, which answers an SSL decode error that reads like a page crash).
// The page renders "Couldn't reach the server" and no league call is ever made,
// which this probe correctly reports as exit 5. Keep the flag for a laptop with
// open egress; on a lane, the `injected` mode against PRODUCTION is the picture.
const SITE = process.env.SITE || 'https://bainluck.com';
// HOSTNAME EQUALITY, NOT A PREFIX (CodeQL `js/incomplete-url-substring-sanitization`,
// which refused the first cut of this line): `startsWith('https://bainluck.com')`
// is also true of `https://bainluck.com.example.net`, so the check that decides
// whether to SKIP the deployed-commit gate could be satisfied by a host that is
// not ours. Parse it and compare the host.
const SITE_HOST = new URL(SITE).hostname;
const LOCAL = SITE_HOST !== 'bainluck.com' && SITE_HOST !== 'www.bainluck.com';

const curl = (url) =>
  execFileSync('curl', ['-sSL', '--max-time', '45', url], { encoding: 'utf8', maxBuffer: 64e6 });

// ── 1. IS THIS EVEN PAYABLE? THE DEPLOYED FRONTEND COMMIT DECIDES ────────────
// `/api/frontend-build` is the frontend's own answer to "merged is not live".
// Without this gate a green run could be scoring the pre-fix bundle.
const SHA = process.env.SHA;
if (LOCAL) {
  console.log(`⚠️  SITE=${SITE} — LOCAL RENDER, NOT AN AFTER-CHECK. No deployed-commit gate.`);
} else if (!SHA) {
  console.error('SHA is required — it is what makes a green run mean anything');
  process.exit(2);
}
if (!LOCAL) {
  let deployed;
  try {
    deployed = JSON.parse(curl(`${SITE}/api/frontend-build`)).commit;
  } catch (e) {
    console.error(`could not read /api/frontend-build: ${e.message}`);
    process.exit(1);
  }
  let carriesSha = false;
  try {
    execFileSync('git', ['merge-base', '--is-ancestor', SHA, deployed], { stdio: 'ignore' });
    carriesSha = true;
  } catch {
    carriesSha = false;
  }
  console.log(`deployed frontend commit: ${deployed} · carries ${SHA.slice(0, 9)}: ${carriesSha}`);
  if (!carriesSha) {
    console.error('NOT PAYABLE: the deployed bundle does not contain this sha (fetch origin first).');
    process.exit(4);
  }
}

// ── 2. THE SPECIMENS, OFF THE LIVE ENVELOPE ──────────────────────────────────
const envelope = JSON.parse(curl(`${API}/api/leagues/${LEAGUE_KEY}`));
const rail = envelope.unreported_games || [];
if (rail.length < 2) {
  console.error(`NOT PAYABLE: ${LEAGUE_KEY}'s unreported rail holds ${rail.length} rows.`);
  process.exit(4);
}

const graded = new Map(); // id -> the verdict the card must print
if (mode === 'injected') {
  // The verdict comes from each row's OWN detail payload — the sentence the
  // page one tap away already prints — so the injected bytes are the producer's
  // answer and not a string this probe made up. A row the detail route does not
  // grade is skipped rather than fabricated.
  for (const row of rail) {
    if (graded.size === 2) break;
    const detail = JSON.parse(curl(`${API}/api/events/${row.id}`));
    if (detail.venue_settled && detail.venue_settled_result) {
      graded.set(row.id, detail.venue_settled_result);
    }
  }
  if (graded.size < 1) {
    console.error('NOT PAYABLE: no unreported row is graded on its own detail payload.');
    process.exit(4);
  }
} else {
  for (const row of rail) {
    if (row.venue_settled && row.venue_settled_result) graded.set(row.id, row.venue_settled_result);
  }
  if (graded.size === 0) {
    console.error(
      'NOT PAYABLE: no rail row carries `venue_settled` — the producer (#6739) is not live yet. ' +
        'This is NOT a pass.',
    );
    process.exit(4);
  }
}
const denied = rail.filter((r) => !graded.has(r.id)).map((r) => r.id);
console.log(
  `${mode}: ${graded.size} graded row(s) [${[...graded.keys()].join(', ')}], ` +
    `${denied.length} still denied [${denied.join(', ')}]`,
);

// ── 3. THE PAGE ──────────────────────────────────────────────────────────────
const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
// 🪤 `<-loopback>` REMOVES loopback from the bypass list — it sends 127.0.0.1
// through the proxy, which answers a local `next start` with an SSL decode
// error that reads exactly like the page crashing. Production needs it; a local
// render must never have it.
// A local render still needs the proxy for `api.bainluck.com` (the sandbox
// refuses direct egress, `ERR_ACCESS_DENIED`) — it must bypass loopback ONLY.
if (proxy && !LOCAL) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
else if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=localhost,127.0.0.1');

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 900 }, deviceScaleFactor: 2 });
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });

let fulfilled = 0;
if (mode === 'injected') {
  const patched = {
    ...envelope,
    unreported_games: rail.map((row) =>
      graded.has(row.id)
        ? { ...row, venue_settled: true, venue_settled_result: graded.get(row.id) }
        : { ...row, venue_settled: false, venue_settled_result: null },
    ),
  };
  await page.route(`**/api/leagues/${LEAGUE_KEY}*`, (route) => {
    fulfilled += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(patched),
    });
  });
}

await page.goto(`${SITE}${PAGE_PATH}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page
  .locator(`a[href="/events/${rail[0].id}"]`)
  .first()
  .waitFor({ state: 'attached', timeout: 60000 })
  .catch(() => {});
await page.waitForTimeout(3000);

const decline = page.getByRole('button', { name: /^Decline$/ });
if (await decline.count()) {
  await decline.first().click();
  await page.waitForTimeout(800);
}

if (mode === 'injected' && fulfilled === 0) {
  console.error('INTERCEPTION NEVER FIRED — the page did not fetch the league route.');
  await browser.close();
  process.exit(5);
}

// Read each card STRUCTURALLY — by its own `/events/<id>` link, then the
// heading of the section it sits in. Scraping page text would let a sentence
// printed anywhere else on the page score a card that never changed.
const read = await page.evaluate((ids) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const out = {};
  for (const id of ids) {
    const card = document.querySelector(`a[href="/events/${id}"]`);
    if (!card) {
      out[id] = null;
      continue;
    }
    const section = card.closest('section');
    out[id] = {
      text: norm(card.textContent),
      heading: norm(section?.querySelector('h2')?.textContent),
      flagged: !!card.querySelector('[data-venue-settled="true"]'),
    };
  }
  return out;
}, rail.map((r) => r.id));

await page.screenshot({ path: `artifacts/ux-1345/AFTER-7070-${mode}-${LEAGUE_KEY}.png` }).catch(() => {});
await browser.close();

// ── 4. THE VERDICT ───────────────────────────────────────────────────────────
const DENIAL = 'No result reported';
const fails = [];
let seen = 0;
for (const [id, verdict] of graded) {
  const card = read[id];
  if (!card) continue; // below the rail's cap or re-railed between the two reads
  seen += 1;
  if (!card.text.includes(`Settled · ${verdict}`)) {
    fails.push(`${id}: card does not print "Settled · ${verdict}" — it reads "${card.text}"`);
  }
  if (card.text.includes(DENIAL)) fails.push(`${id}: card STILL denies — "${card.text}"`);
  if (!card.flagged) fails.push(`${id}: the sentence span is not flagged data-venue-settled`);
  if (card.heading === DENIAL) {
    fails.push(`${id}: the heading above it still reads "${DENIAL}"`);
  }
}
for (const id of denied) {
  const card = read[id];
  if (!card) continue;
  // The other direction, in the same frame: a fix one condition too wide would
  // print "Settled" over a row nothing graded, and that is the worse defect.
  if (!card.text.includes(DENIAL)) {
    fails.push(`${id}: an UNGRADED row stopped denying — "${card.text}"`);
  }
  if (card.flagged) fails.push(`${id}: an UNGRADED row is flagged data-venue-settled`);
}
if (seen === 0) {
  console.error('NOT PAYABLE: none of the graded rows rendered a card on the page.');
  process.exit(4);
}

for (const [id, card] of Object.entries(read)) {
  if (card) console.log(`  ${id}  [${card.heading}]  ${card.text.slice(0, 110)}`);
}
if (fails.length) {
  console.error(`\nFAIL (${fails.length}):`);
  for (const f of fails) console.error(`  - ${f}`);
  process.exit(3);
}
console.log(`\nPASS — ${seen} graded card(s) name their winner, ${denied.length} ungraded still deny.`);
process.exit(0);
