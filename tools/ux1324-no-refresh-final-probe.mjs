// ux1324-no-refresh-final-probe.mjs <url> <outPrefix> [waitMinutes=10]
//
// NOTICE 42's LAST TWO SHOTS, IN ONE PAGE LIFETIME.
//
// The rule asks for a frame at the final AND one ten minutes later **without
// refreshing** — the second is the whole point, because it is the only one that
// can catch a page that only tells the truth on a reload. `look.sh` navigates
// every time, so two `look.sh` runs ten minutes apart are two refreshes and
// cannot answer the question. This loads once and photographs twice off the same
// page object: no `goto`, no reload, no cache bust. Whatever changes between the
// frames is the page's own polling.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 both frames, 2 usage, 1 camera.
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

const [url, prefix, minutesArg] = process.argv.slice(2);
if (!url || !prefix) { console.error('usage: … <url> <outPrefix> [waitMinutes]'); process.exit(2); }
const waitMs = (Number(minutesArg) || 10) * 60_000;

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

const stamp = () => new Date().toISOString().slice(11, 16).replace(':', '') + 'Z';

const browser = await chromium.launch({ args });
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(6000);
// 🪤 Compare against where we LANDED, not against what was typed. `bainluck.com`
// 307s to `www.bainluck.com`, so checking `page.url() === url` printed
// `url-unchanged false` on a run that never navigated once — a rig artifact that
// reads exactly like the thing this probe exists to rule out.
const landedUrl = page.url();

// The status line the reader reads first — captured as TEXT beside each frame so
// the pair is comparable without reopening the PNGs.
const statusLine = () =>
  page.evaluate(() => (document.body.innerText || '').split('\n').slice(0, 14).join(' | '));

const a = `${prefix}-A-${stamp()}.png`;
await page.screenshot({ path: a });
console.log(`A ${a}`);
console.log(`A-text ${JSON.stringify(await statusLine())}`);

console.log(`waiting ${waitMs / 60000} minutes — NO navigation, NO reload`);
await page.waitForTimeout(waitMs);

const b = `${prefix}-B-${stamp()}.png`;
await page.screenshot({ path: b });
console.log(`B ${b}`);
console.log(`B-text ${JSON.stringify(await statusLine())}`);
console.log(`url-unchanged ${page.url() === landedUrl}`);

await browser.close();
