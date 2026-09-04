// shop-shot.mjs <url> <out.png> [clickText] — headless screenshot of a production page.
//
// Why this exists instead of `npx playwright screenshot`: Chromium's default multi-process
// launch dies in the agent sandbox (`bootstrap_check_in ... Permission denied (1100)`), and the
// browser does not inherit the session egress proxy. Both are fixed by the args below:
//   --single-process        clears the Mach port rendezvous the sandbox blocks
//   --proxy-server=$HTTPS_PROXY --proxy-bypass-list=<-loopback>   gives the browser egress
// --single-process supports exactly ONE context, so this launches a fresh browser per page.
//
// Also dismisses the cookie banner, which otherwise covers real content in every full-page shot.
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
const [url, out, clickText] = process.argv.slice(2);
if (!url || !out) { console.error('usage: shop-shot.mjs <url> <out.png> [clickText]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let ok = false;
try {
  const W = parseInt(process.env.SHOT_W || '1280', 10);
  const H = parseInt(process.env.SHOT_H || '2200', 10);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(7000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(2500);
  } catch { /* no banner on this page */ }
  if (clickText) {
    try {
      await page.getByText(clickText, { exact: true }).first().click({ timeout: 10000 });
      await page.waitForTimeout(6000);
    } catch { console.error(`CLICKFAIL ${clickText}`); }
  }
  await page.screenshot({ path: out, fullPage: true });
  ok = true;
  console.log(out);
} catch (e) {
  console.error(`FAIL ${url} :: ${e.message}`);
} finally {
  await browser.close();
}
process.exit(ok ? 0 : 1);
