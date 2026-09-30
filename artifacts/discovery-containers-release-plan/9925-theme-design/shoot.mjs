// shoot.mjs <url> <out.png> — phone-width screenshot helper for the #9925 design artifacts.
// Same sandbox launch args as tools/shop-shot.mjs (single-process + proxy; loopback keeps
// the implicit bypass). Env: SHOT_W/SHOT_H (default 390x844), SHOT_TEXT (scroll the first
// element whose text contains this into view, 12px from the top), SHOT_FULL=1 (whole page),
// SHOT_CLICK (exact text to tap before shooting), SHOT_WAIT (ms, default 2500).
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
const [url, out] = process.argv.slice(2);
if (!url || !out) { console.error('usage: shoot.mjs <url> <out.png>'); process.exit(2); }
const local = /^(file:|https?:\/\/(localhost|127\.0\.0\.1))/.test(url);
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy && !url.startsWith('file:')) {
  args.push(`--proxy-server=${proxy}`);
  if (!local) args.push('--proxy-bypass-list=<-loopback>');
}
const browser = await chromium.launch({ args });
try {
  const W = parseInt(process.env.SHOT_W || '390', 10);
  const H = parseInt(process.env.SHOT_H || '844', 10);
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, deviceScaleFactor: 2,
    extraHTTPHeaders: local ? {} : { 'x-bainluck-origin': 'agent-discover' },
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(parseInt(process.env.SHOT_WAIT || '2500', 10));
  for (const t of ['Accept', 'Got it', 'OK']) {
    const b = page.getByRole('button', { name: t, exact: true });
    if (await b.count()) { await b.first().click().catch(() => {}); }
  }
  if (process.env.SHOT_TEXT) {
    const loc = page.getByText(process.env.SHOT_TEXT, { exact: false }).first();
    let found = false;
    for (let i = 0; i < 30 && !found; i++) {
      if (await loc.count()) { found = true; break; }
      await page.mouse.wheel(0, 900); await page.waitForTimeout(700);
    }
    if (!found) { console.error(`SHOT_TEXT not found: ${process.env.SHOT_TEXT}`); process.exit(3); }
    await loc.evaluate((el, off) => { const y = el.getBoundingClientRect().top + window.scrollY - off; window.scrollTo(0, y); }, parseInt(process.env.SHOT_OFFSET || "12", 10));
    await page.waitForTimeout(900);
  }
  if (process.env.SHOT_CLICK) {
    const c = page.getByText(process.env.SHOT_CLICK, { exact: true }).first();
    if (!(await c.count())) { console.error(`SHOT_CLICK not found: ${process.env.SHOT_CLICK}`); process.exit(3); }
    await c.click(); await page.waitForTimeout(1200);
  }
  await page.screenshot({ path: out, fullPage: process.env.SHOT_FULL === '1' });
  console.log(`shot ${out} ${W}x${H} scrollY=${await page.evaluate(() => Math.round(window.scrollY))} docH=${await page.evaluate(() => document.documentElement.scrollHeight)}`);
} finally {
  await browser.close();
}
