// cal-datagolf-promise-1219.mjs — does the page keep the promise it makes to the reader?
//
// In the default cohort the DataGolf provider row reads:
//   "No outcomes in this cohort — see “Include untraded (+295,994)”."
// That sentence sends the reader to a specific control. This walks that exact path — read the
// DataGolf row, tap the cohort toggle, read it again — and prints every provider row both sides
// so the 36-outcome source can be compared with its 300k-outcome peers as a reader would see it.
//
// exits: 0 read OK · 2 not payable · 3 the toggle never landed
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
const ok = await page.waitForSelector('[data-testid="calibration-provider-row"]', { timeout: 60000 })
  .then(() => true).catch(() => false);
if (!ok) { await browser.close(); console.log('NOT PAYABLE'); process.exit(2); }
await page.waitForTimeout(1500);

const read = () => page.evaluate(() => {
  const txt = el => (el.textContent || '').replace(/\s+/g, ' ').trim();
  const rows = [...document.querySelectorAll('[data-testid="calibration-provider-row"]')]
    .map(tr => [...tr.querySelectorAll('th,td')].map(td => txt(td)));
  const toggle = document.querySelector('[data-testid="calibration-cohort-toggle"]');
  const tile = document.querySelector('[data-testid="calibration-stat-sources"]');
  const resolved = document.querySelector('[data-testid="calibration-stat-resolved"]');
  return {
    rows,
    toggle: toggle ? txt(toggle) : null,
    toggleData: toggle ? { ...toggle.dataset } : null,
    sourcesTile: tile ? txt(tile) : null,
    resolvedTile: resolved ? txt(resolved) : null,
  };
});

const before = await read();
console.log('=== DEFAULT (untraded excluded) ===');
console.log('SOURCES tile :', JSON.stringify(before.sourcesTile));
console.log('RESOLVED tile:', JSON.stringify(before.resolvedTile));
console.log('cohort banner:', JSON.stringify(before.toggle));
console.log('partition data:', JSON.stringify(before.toggleData));
console.log('provider rows:');
for (const r of before.rows) console.log('  ', JSON.stringify(r));

// The reader follows the row's own instruction and taps the toggle it names.
const btn = page.locator('[data-testid="calibration-cohort-toggle"] button').first();
if (!(await btn.count())) { await browser.close(); console.log('TOGGLE NOT FOUND'); process.exit(3); }
await btn.click();
await page.waitForTimeout(1800);

const after = await read();
console.log('\n=== AFTER TAPPING THE TOGGLE THE ROW NAMES ===');
console.log('SOURCES tile :', JSON.stringify(after.sourcesTile));
console.log('RESOLVED tile:', JSON.stringify(after.resolvedTile));
console.log('cohort banner:', JSON.stringify(after.toggle));
console.log('provider rows:');
for (const r of after.rows) console.log('  ', JSON.stringify(r));
await browser.close();
