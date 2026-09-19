// ux1344-settlement-banner-after-7060.mjs — the after-check for #7060 (+ #7058's frontend half),
// written so it can be re-run by anyone and cannot pass by accident.
//
// The claim to prove on production:
//   ARM 1 (#7060)  an OPEN market whose scheduled `resolution_date` has passed renders NO
//                  settlement banner at all.
//   ARM 2 (#7058)  a RESOLVED market renders exactly "This market has been settled." and states
//                  NO date — in particular not its scheduled one.
//
// 🔴 SUBJECT DETECTION IS NOT KEYED ON THE DEFECT'S MARKUP. A probe that looks for the banner in
// order to decide whether it found the page reports a working fix as "subject missing" — the
// failure and the pass are the same reading. So the subject is proved from things the fix cannot
// touch: the page's own H1, and the market's `status` read from the API in the same run. Only
// once the subject is proved is the banner looked for.
//
// It also refuses to grade a stale deployment: `/api/frontend-build` must report a commit that
// CONTAINS the sha under test (pass it as SHA=...), because "merged" is not "live".
//
// usage:
//   SHA=04a91cf1f node tools/ux1344-settlement-banner-after-7060.mjs <openId> <resolvedId>
// exit 0 = both arms PASS · 3 = an arm FAILED (the defect is on production) ·
//      4 = subject not found / deployment not carrying the sha — NOT a pass.
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
import { execFileSync } from 'child_process';
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) for (const d of readdirSync(npx)) { const p = `${npx}/${d}/node_modules/`; if (existsSync(`${p}playwright`)) return p; }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');

let [openId, resolvedId] = process.argv.slice(2);
const SHA = process.env.SHA || '';
const SITE = 'https://bainluck.com';
const API = process.env.BAINLUCK_API || 'https://api.bainluck.com';
const ADMIN = process.env.ADMIN_TOKEN || '';

const SETTLED_SENTENCE = 'This market has been settled.';
/** Any sentence that asserts settlement. Deliberately broader than what we ship. */
const SETTLEMENT_CLAIM = /(has been settled|resolved on|final probabilities|Resolved \d)/i;
/** A date a reader would read as one: 9/18/2026, Sep 18, 2026-09-18. */
const A_DATE = /\d{1,4}[/-]\d{1,2}[/-]\d{1,4}|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b/;

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

// 🪤 Node's own `fetch` ignores HTTPS_PROXY, and this sandbox's egress needs it — a bare
// fetch dies with `connect EPERM`, which reads as "the site is down" rather than "I cannot
// dial out". `curl` honours the session proxy, so every HTTP read goes through it.
function getJSON(url) {
  const out = execFileSync('curl', ['-sSL', '-H', 'x-bainluck-origin: ux', url], {
    encoding: 'utf8', timeout: 30000,
  });
  try {
    return JSON.parse(out);
  } catch {
    throw new Error(`${url} did not answer JSON: ${out.slice(0, 200)}`);
  }
}

const api = (path) => getJSON(`${API}${path}`);

/**
 * Pick the specimens rather than making the caller find them.
 *
 * ARM 1's population TURNS OVER CONTINUOUSLY — every in-game market crosses its scheduled date
 * while trading and is settled an hour later — so a hardcoded id rots within the hour and the
 * probe then grades a market that no longer meets its own precondition. It asks production
 * instead, and `preconditions` below re-checks the answer against the SERVED payload, so a bad
 * pick reports SUBJECT-NOT-VALID rather than a pass.
 */
function pickSpecimens() {
  if (!ADMIN) {
    throw new Error('No ADMIN_TOKEN and no ids given. `source ~/.claude/.env` first, or pass <openId> <resolvedId>.');
  }
  const ask = (sql) => {
    const out = execFileSync('curl', ['-sS', '-X', 'POST', '-H', `Authorization: Bearer ${ADMIN}`,
      '-H', 'Content-Type: application/json', '-d', JSON.stringify({ sql, limit: 5 }),
      `${API}/api/admin/db-query`], { encoding: 'utf8', timeout: 30000 });
    const rows = JSON.parse(out).rows ?? [];
    if (!rows.length) throw new Error(`no specimen for: ${sql}`);
    return String(rows[0][0]);
  };
  return {
    open: ask("SELECT id FROM futures_markets WHERE status = 'open' AND resolution_date < now() - interval '20 minutes' ORDER BY resolution_date DESC LIMIT 1"),
    // A FUTURE scheduled date is the sharpest #7058 specimen: the old banner printed it as history.
    resolved: ask("SELECT id FROM futures_markets WHERE status = 'resolved' AND resolution_date > now() + interval '3 days' ORDER BY updated_at DESC LIMIT 1"),
  };
}

if (!openId || !resolvedId) {
  const picked = pickSpecimens();
  openId = openId || picked.open;
  resolvedId = resolvedId || picked.resolved;
  console.error(`specimens picked from production: open=${openId} resolved=${resolvedId}`);
}

// ── The deployment must carry the sha under test ─────────────────────────────
//
// 🪤 ANCESTRY, NOT A PREFIX. The first cut compared the deployed commit to the
// BRANCH sha with `startsWith`, which can never be true once the desk merges:
// production serves the MERGE COMMIT, so a fix that was live and correct was
// reported NOT-LIVE (exit 4) by its own after-check. ux/1345 hit this the first
// time it ran — `7980bbbdc` vs `04a91cf1f`, with the branch sha a plain
// ancestor of it. The question is "does the deployed tree CONTAIN this commit",
// and only git can answer that.
const build = getJSON(`${SITE}/api/frontend-build`);
let deployedCarriesSha = false;
if (SHA && build.commit) {
  try {
    execFileSync('git', ['merge-base', '--is-ancestor', SHA, build.commit], { stdio: 'ignore' });
    deployedCarriesSha = true;
  } catch {
    deployedCarriesSha = false;
  }
}
if (SHA && !deployedCarriesSha) {
  console.log(JSON.stringify({ verdict: 'NOT-LIVE', deployed: build.commit, expected: SHA }, null, 2));
  console.error(`\nDeployment is on ${build.commit}, not ${SHA}. Merged is not live; nothing graded.`);
  process.exit(4);
}

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, extraHTTPHeaders: { 'x-bainluck-origin': 'ux' } });

/** Read one market's page, proving the subject before reading the banner. */
async function readMarket(id) {
  const payload = api(`/api/futures/${id}`);
  await page.goto(`${SITE}/futures/${id}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2500);

  // SUBJECT: the page rendered THIS market. Keyed on the H1, which the fix never touches.
  const heading = (await page.locator('h1').first().textContent().catch(() => null))?.trim() || null;
  const body = (await page.locator('body').innerText()).trim();
  const subjectFound = !!heading && heading.length > 0 && !/Market not found|Rate limit/i.test(body);

  // The banner is the first block under the back link. Read the whole body for any settlement
  // claim rather than one selector, so a claim that MOVED still counts against us.
  const claim = body.match(SETTLEMENT_CLAIM)?.[0] ?? null;
  const bannerLine = body.split('\n').find((l) => SETTLEMENT_CLAIM.test(l))?.trim() ?? null;

  return { id, status: payload.status, resolution_date: payload.resolution_date,
           settled_at: payload.settled_at ?? null, heading, subjectFound, claim, bannerLine };
}

const results = { deployed: build.commit, arms: [] };
let failed = false, unresolvedSubject = false;

// ── ARM 1 — #7060: an OPEN market with a passed date says nothing ────────────
{
  const m = await readMarket(openId);
  const datePassed = !!m.resolution_date && new Date(m.resolution_date) < new Date();
  const preconditions = m.status === 'open' && datePassed;
  const pass = preconditions && m.subjectFound && m.claim === null;
  if (!m.subjectFound || !preconditions) unresolvedSubject = true; else if (!pass) failed = true;
  results.arms.push({ arm: '#7060 open + passed date renders NO banner', ...m, datePassed,
                      preconditions, verdict: !m.subjectFound || !preconditions ? 'SUBJECT-NOT-VALID' : pass ? 'PASS' : 'FAIL' });
}

// ── ARM 2 — #7058's frontend half: settled says so, and states no date ───────
{
  const m = await readMarket(resolvedId);
  const preconditions = m.status === 'resolved';
  const saysSettled = m.bannerLine?.includes(SETTLED_SENTENCE) ?? false;
  const statesADate = !!m.bannerLine && A_DATE.test(m.bannerLine);
  const pass = preconditions && m.subjectFound && saysSettled && !statesADate;
  if (!m.subjectFound || !preconditions) unresolvedSubject = true; else if (!pass) failed = true;
  results.arms.push({ arm: '#7058 settled says so with NO date', ...m, preconditions, saysSettled,
                      statesADate, verdict: !m.subjectFound || !preconditions ? 'SUBJECT-NOT-VALID' : pass ? 'PASS' : 'FAIL' });
}

await browser.close();
console.log(JSON.stringify(results, null, 2));
if (unresolvedSubject) { console.error('\nSUBJECT NOT VALID — pick fresh specimens. This is not a pass.'); process.exit(4); }
if (failed) { console.error('\nAT LEAST ONE ARM FAILED — the defect is on production.'); process.exit(3); }
console.error('\nBOTH ARMS PASS.');
process.exit(0);
