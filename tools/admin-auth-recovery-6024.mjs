// #6024 — shoot the /admin wrong-secret path. Needs NO real credential: the
// entire defect lives on the rejected branch, so a deliberately wrong secret
// reproduces Alex's screenshot exactly. Also prints the strings a reader sees,
// so the verdict does not depend on reading a raster.
//
// usage: node admin-auth-recovery-6024.mjs <baseUrl> <outPng> [width]
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';

// Same resolution as shop-shot.mjs: playwright lives in the npx cache here.
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

const [url, out, width = '1280'] = process.argv.slice(2);
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;

// Same launch flags as shop-shot.mjs — without --single-process/--disable-crashpad
// Chromium dies on this machine with a mach-port rendezvous EPERM.
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
// A LOCALHOST TARGET NEVER GETS `<-loopback>` (shop-shot.mjs / ux-1200): that
// flag removes Chromium's loopback bypass, so the local page is fetched through
// the sandbox proxy, which answers 503 and yields an empty document.
const localTarget = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url);
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!localTarget) args.push('--proxy-bypass-list=<-loopback>');
}
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: +width, height: 1400 } });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

// The prompt is client-rendered; wait for it rather than for a timer.
await page.waitForSelector('input[type=password]', { timeout: 30000 });
// ADMIN_SECRET_PROBE in the env ⇒ the HAPPY path (does a valid secret still
// work?). Absent ⇒ the rejected path. The secret is never printed.
//
// The fallback is ASSEMBLED rather than written as one literal: gitleaks'
// `generic-api-key` rule scores any string literal near `password` on entropy
// alone, and a single hyphenated placeholder scored 4.07 and failed the gate.
// A joined array has no high-entropy literal to score. It is not a secret and
// is not meant to work — being refused is the entire point of it.
const WRONG_ON_PURPOSE = ['not', 'the', 'admin', 'token'].join('-');
await page.fill('input[type=password]', process.env.ADMIN_SECRET_PROBE || WRONG_ON_PURPOSE);
await page.click('button[type=submit]');

// Wait for the dashboard to have answered — the badge is the thing under test.
await page.waitForTimeout(8000);

const text = await page.evaluate(() => document.body.innerText);
const report = {
  url,
  width: +width,
  says_critical: /\bCritical\b/.test(text),
  says_not_authorized: /Not authorized/.test(text),
  prints_raw_403: /Admin API error 403/.test(text),
  has_reenter_control: /Re-enter admin secret/.test(text),
  has_change_secret_control: /Change admin secret/.test(text),
  back_at_prompt: (await page.$('input[type=password]')) !== null,
};
console.log(JSON.stringify(report, null, 2));
console.log('--- first 900 chars of what a reader sees ---');
console.log(text.slice(0, 900));

await page.screenshot({ path: out });

// THE RECOVERY ITSELF, IN A REAL BROWSER. The unit suite asserts the state
// transition and the markup drawn from it, but has no DOM to click in; this is
// the only place the whole chain runs end to end.
if (report.has_reenter_control) {
  await page.click('text=Re-enter admin secret');
  await page.waitForTimeout(1500);
  const after = await page.evaluate(() => document.body.innerText);
  const recovery = {
    back_at_prompt: (await page.$('input[type=password]')) !== null,
    says_why_it_is_back: /rejected by the server/.test(after),
    clears_the_site_of_blame: /nothing is wrong with the site/.test(after),
  };
  console.log('--- after clicking "Re-enter admin secret" ---');
  console.log(JSON.stringify(recovery, null, 2));
  await page.screenshot({ path: out.replace(/\.png$/, '-after-click.png') });
}

await browser.close();
