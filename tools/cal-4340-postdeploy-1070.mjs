// cal-4340-postdeploy-1070.mjs — the OTHER half of #4340, measured on production.
//
// #4340 removed grey method prose from /calibration's body. Removing prose is easy to LOOK at and
// a screenshot proves it. The half a screenshot CANNOT prove is the one notice 34's
// failing-self-audit clause actually turns on: the numbers that prose carried must still travel as
// data, or the fix has quietly made the page less measurable than it was.
//
// So this asks the rendered DOM two questions, and grades BOTH:
//
//   1. Is the banned prose gone from what a reader is handed?  (innerText, folds closed)
//   2. Is every fact it carried still readable as an attribute or an existing hook?
//
// A pass on (1) alone is not a pass. That is the whole point.
//
// Deliberately NOT reusing 1068's leaf-only DOM census: a probe written before a fix goes blind to
// the elements the fix adds. This one names its own targets.
//
// exits: 0 PASS · 1 REOPEN (a graded condition failed) · 2 not payable (page never rendered)
//
// Usage: node cal-4340-postdeploy-1070.mjs [url] [widthPx]
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

const url = process.argv[2] || 'https://bainluck.com/calibration';
const width = Number(process.argv[3] || 390);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

// Payable only once the page has actually drawn its data. An all-clear read off a page that never
// rendered is the failure mode this exit code exists for (gotcha #53: an empty 200 is a shape).
const rendered = await page
  .waitForSelector('[data-testid="calibration-by-source-section"]', { timeout: 60000 })
  .then(() => true)
  .catch(() => false);
if (!rendered) {
  await browser.close();
  console.log('NOT PAYABLE — By Source never rendered; nothing to grade.');
  process.exit(2);
}
await page.waitForTimeout(1500);

const out = await page.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const attr = (s, a) => q(s)?.getAttribute(a) ?? null;
  // What a READER is handed: innerText does not return a closed <details>, which is precisely why
  // it is the right instrument here — it sees exactly what the fold hides.
  const visible = (document.body.innerText || '').replace(/\s+/g, ' ');
  return {
    visible,
    docHeight: document.body.scrollHeight,
    thinFloor: attr('[data-testid="calibration-by-source-section"]', 'data-thin-floor'),
    shapeProviders: attr('[data-testid="calibration-by-source-section"]', 'data-shape-breakdown-providers'),
    withheld: attr('[data-testid="calibration-by-source-section"]', 'data-withheld-sources'),
    movedN: attr('[data-testid="calibration-cohort-toggle"]', 'data-moved-n'),
    notApplicableN: attr('[data-testid="calibration-cohort-toggle"]', 'data-not-applicable-n'),
    unchangedN: attr('[data-testid="calibration-cohort-toggle"]', 'data-unchanged-n'),
    cohortN: attr('[data-testid="calibration-population-count"]', 'data-cohort-n'),
    fullN: attr('[data-testid="calibration-population-count"]', 'data-full-n'),
    hasKeyFold: !!q('[data-testid="calibration-panels-key"]'),
    hasBreakOut: (document.body.innerText || '').includes('Break out the shapes'),
    captionText: q('[data-testid="calibration-by-source-caption"]')?.textContent?.replace(/\s+/g, ' ').trim() ?? null,
  };
});
await browser.close();

const BANNED = [
  ['the 28x justification', 'because the providers differ by more than 28x'],
  ['the reviewer-answering clause', 'so you can see exactly how much data stands behind each point'],
  ['the hollow-dot key', 'faded hollow dots with wide error'],
  ['the CI key', 'Error bars are the 95% CI'],
  ['the partition arithmetic', 'carry no price-moved flag and need none'],
  ['the mix-shift clause', 'predicted-probability mix fixed'],
];

const n = (v) => (v === null ? NaN : Number(v));
const moved = n(out.movedN), na = n(out.notApplicableN), unchanged = n(out.unchangedN);
const cohort = n(out.cohortN), full = n(out.fullN);

const checks = [];
for (const [label, clause] of BANNED) {
  checks.push([`prose gone — ${label}`, !out.visible.includes(clause), clause]);
}
checks.push(['the caption is still there', !!out.captionText, out.captionText]);
checks.push(['and it is short', (out.captionText || '').length < 200, `${(out.captionText || '').length} chars`]);
checks.push(['the drawing key is reachable, not deleted', out.hasKeyFold, 'calibration-panels-key']);
checks.push(['the affordance the folded note announced is still visible', out.hasBreakOut, 'Break out the shapes']);
checks.push(['data-thin-floor travels', Number.isFinite(n(out.thinFloor)), out.thinFloor]);
// Empty string is a VALUE ("none withheld"), null is an absence. Only the second is a failure.
checks.push(['data-shape-breakdown-providers travels', out.shapeProviders !== null, JSON.stringify(out.shapeProviders)]);
checks.push(['data-withheld-sources travels', out.withheld !== null, JSON.stringify(out.withheld)]);
checks.push(['every term of the folded arithmetic is readable',
  [moved, na, unchanged, cohort, full].every(Number.isFinite),
  `moved=${moved} sportsbook=${na} untraded=${unchanged} cohort=${cohort} full=${full}`]);
checks.push(['and it still reconciles', moved + na + unchanged === full,
  `${moved} + ${na} + ${unchanged} = ${moved + na + unchanged} vs full ${full}`]);
checks.push(['the cohort is the traded side', cohort === moved + na || cohort === full,
  `cohort ${cohort} vs moved+sportsbook ${moved + na}, full ${full}`]);

console.log(`# ${url} @ ${width}px — doc ${out.docHeight}px\n`);
let failed = 0;
for (const [label, ok, detail] of checks) {
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}\n        ${detail}`);
}
console.log(`\n${failed === 0 ? 'PASS — the prose is gone AND every fact it carried still travels.'
  : `REOPEN #4340 — ${failed} graded condition(s) failed.`}`);
process.exit(failed === 0 ? 0 : 1);
