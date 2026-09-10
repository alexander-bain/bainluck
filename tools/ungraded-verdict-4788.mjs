// ungraded-verdict-4788.mjs — how many verdicts does a resolved futures page state,
// and how many of them did anyone actually grade? (#4788 / #4783 / #1638 render half)
//
// The rule under test: a `futures_outcomes` row whose `resolution_source IS NULL` is UNGRADED
// and must print NO verdict, whatever `is_winner` says. `is_winner` is `boolean NULL DEFAULT
// false`, so an INSERT that omits it stores an affirmative graded LOSS (CAL-P1004R) — on
// `/futures/59700266` all 24 "graded" legs carry exactly that shape and 0 carry a real source.
//
// This reads the DOM, not pixels, for the same reason `prop-tile-fit-2788.mjs` does: the claim is
// "N rows state a verdict", and counting red pills in a screenshot cannot survive a scroll, a lazy
// section, or a `Show all` collapse. A verdict is detected by the PILL'S TEXT ("Won"/"Lost") and by
// the "Settled" line in the numbers block — never by a colour class, which the fix is allowed to
// change, and never by the red tint, which is a different element.
//
// Rows are found by `[data-testid="outcome-row"]`, which OutcomeRow already emits. Anchoring on the
// verdict class instead would read correctly against the BROKEN arm and return nothing against the
// FIXED one — indistinguishable from "the page failed to render", the single most misleading thing
// an after-measurement can say.
//
// It also fetches the market's own API payload and reports whether `resolution_source` TRAVELS.
// That is the load-bearing precondition: absent the field the render rule cannot be evaluated
// client-side at all, and `.get()`-style reads report the absence as a served null.
//
// Usage: node ungraded-verdict-4788.mjs <url> [widthPx]
//   e.g. node tools/ungraded-verdict-4788.mjs https://bainluck.com/futures/59700266 390
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
import { execFileSync } from 'child_process';

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

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
if (!url) { console.error('usage: ungraded-verdict-4788.mjs <url> [widthPx]'); process.exit(2); }

const marketId = (url.match(/\/futures\/(\d+)/) || [])[1];
const local = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(url);
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push(local ? '--proxy-bypass-list=127.0.0.1;localhost' : '--proxy-bypass-list=<-loopback>');
}

// ---- the payload precondition, read with curl (this process has egress the page does not) ----
let apiLine = 'no /futures/{id} in the URL — payload check skipped';
let apiWinners = null;
if (marketId) {
  try {
    const raw = execFileSync('curl', ['-sS', '--max-time', '45',
      `https://api.bainluck.com/api/futures/${marketId}`], { maxBuffer: 64 * 1024 * 1024, encoding: 'utf8' });
    const d = JSON.parse(raw);
    const outs = d.outcomes || [];
    // `in`, never `?? null`: an ABSENT key and a served null are the same value and not the same fact.
    const travels = outs.length > 0 && Object.prototype.hasOwnProperty.call(outs[0], 'resolution_source');
    apiWinners = {
      status: d.status,
      total: outs.length,
      isWinnerNull: outs.filter((o) => o.is_winner === null || o.is_winner === undefined).length,
      isWinnerTrue: outs.filter((o) => o.is_winner === true).length,
      isWinnerFalse: outs.filter((o) => o.is_winner === false).length,
      travels,
    };
    apiLine = `market ${marketId} status=${d.status} outcomes=${outs.length}  `
      + `is_winner null/true/false = ${apiWinners.isWinnerNull}/${apiWinners.isWinnerTrue}/${apiWinners.isWinnerFalse}\n`
      + `  resolution_source TRAVELS in the payload: ${travels ? 'YES' : 'NO  <-- render rule is not evaluable client-side'}`;
  } catch (err) {
    apiLine = `payload read failed: ${err.message}`;
  }
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

if (local) {
  await page.route('**://api.bainluck.com/**', async (route) => {
    const target = route.request().url();
    let body;
    try {
      body = execFileSync('curl', ['-sS', '--max-time', '45', target], { maxBuffer: 64 * 1024 * 1024, encoding: 'utf8' });
    } catch (err) {
      console.error(`  ! upstream failed ${target}: ${err.message}`);
      return route.fulfill({ status: 502, contentType: 'application/json', body: '{}' });
    }
    return route.fulfill({
      status: 200, contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' }, body,
    });
  });
}

// NOT networkidle: a polling page never idles and `goto` just times out.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(4000);

// Lay out the lazy sections below the fold.
await page.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 400) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 40));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(600);

// The results table collapses to a handful of rows behind "Show all N". Counting the visible
// rows without expanding measures the COLLAPSE, not the rule.
const expanded = await page.evaluate(async () => {
  const hits = [...document.querySelectorAll('button,a')].filter((b) =>
    /show all/i.test((b.textContent || '').trim()));
  for (const b of hits) { b.click(); await new Promise((r) => setTimeout(r, 300)); }
  return hits.map((b) => (b.textContent || '').replace(/\s+/g, ' ').trim());
});
await page.waitForTimeout(1200);

const out = await page.evaluate(() => {
  // Null-safe: the verdict testid is absent on any bundle older than #4788, and this
  // tool has to run against the DEPLOYED page to say what it is doing today.
  const txt = (el) => ((el && el.textContent) || '').replace(/\s+/g, ' ').trim();
  const rows = [...document.querySelectorAll('[data-testid="outcome-row"]')];
  const seen = rows.map((r) => {
    const name = txt(r.querySelector('[data-testid="outcome-name"]')) || txt(r).slice(0, 40);
    const nums = txt(r.querySelector('[data-testid="outcome-numbers"]'));
    // The verdict is read from its OWN element, never from the row's concatenated
    // text. `textContent` joins adjacent elements with no separator, so a row reads
    // "Jaxon Smith-Njigba: 7+LostOPEN51%…" and `/\bLost\b/` finds no boundary after
    // "Lost" — this tool reported `Lost 0` while the same page said `Settled 24`,
    // i.e. it would have read the same before and after the fix it exists to check.
    // Falls back to an exact leaf-text scan so it still works against a deployed
    // bundle older than the testid.
    const pill =
      txt(r.querySelector('[data-testid="outcome-verdict"]')) ||
      [...r.querySelectorAll('span')]
        .map((s) => txt(s))
        .find((t) => t === 'Won' || t === 'Lost') ||
      '';
    const won = pill === 'Won';
    const lost = pill === 'Lost';
    const settled = /Settled/.test(nums);
    return { name, verdict: won ? 'Won' : lost ? 'Lost' : null, settled, nums };
  });
  return {
    rowsFound: rows.length,
    statesVerdict: seen.filter((r) => r.verdict !== null).length,
    saysSettled: seen.filter((r) => r.settled).length,
    won: seen.filter((r) => r.verdict === 'Won').length,
    lost: seen.filter((r) => r.verdict === 'Lost').length,
    sample: seen.filter((r) => r.verdict !== null).slice(0, 12),
  };
});

await browser.close();

console.log(`\n${url}  @${width}px`);
console.log(`API   ${apiLine}\n`);
console.log(`expanded: ${expanded.length ? expanded.join(' | ') : '(no "Show all" control found)'}`);
console.log(`rows rendered            ${out.rowsFound}`);
console.log(`rows STATING a verdict   ${out.statesVerdict}   (Won ${out.won} / Lost ${out.lost})`);
console.log(`rows saying "Settled"    ${out.saysSettled}`);
if (out.sample.length) {
  console.log('\nrows that state a verdict:');
  for (const r of out.sample) console.log(`  ${r.verdict.padEnd(5)} ${r.name}   [${r.nums}]`);
}

// The headline number: verdicts stated for which nobody wrote a grade.
if (apiWinners && !apiWinners.travels) {
  console.log(`\n⚠ resolution_source is ABSENT from the payload, so the page CANNOT tell a real grade`);
  console.log(`  from a defaulted one. ${out.statesVerdict} verdicts are stated on this page.`);
}
console.log('');
