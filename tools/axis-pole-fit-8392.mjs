// axis-pole-fit-8392.mjs <url> <out-prefix> — measure the two team names in every chart's
// sideways axis gutter at phone width, and photograph each chart.
//
// #8392: two long club names ran into each other on Win Probability and past the bottom of
// Score Differential. Prints, per gutter: its height, each pole's span, the gap between them
// (negative = overlap), how far the lower one runs past the gutter, whether a cap is applied
// and the text a reader sees. `ok` is gap >= 0 and overflow <= 0.
//
//   node tools/axis-pole-fit-8392.mjs https://bainluck.com/events/15306110 /tmp/axis
//   node tools/axis-pole-fit-8392.mjs http://127.0.0.1:3485/events/15306110 /tmp/axis   # a local build
//
// A loopback URL is a branch build (`next start`): loopback goes direct and the page's calls to
// api.bainluck.com are answered by curl, as tools/look-local.mjs does and for the same reason.
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
const [url, prefix] = process.argv.slice(2);
if (!url || !prefix) {
  console.error('usage: axis-pole-fit-8392.mjs <url> <out-prefix>');
  process.exit(2);
}
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const local = /^https?:\/\/(127\.0\.0\.1|localhost)[:/]/.test(url);
if (proxy) args.push(`--proxy-server=${proxy}`, local ? '--proxy-bypass-list=127.0.0.1;localhost' : '--proxy-bypass-list=<-loopback>');
const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
if (local) {
  await page.route('**://api.bainluck.com/**', async (route) => {
    const raw = execFileSync('curl', ['-sS', '--max-time', '45', '-w', '\n%{http_code}', route.request().url()], { maxBuffer: 64 * 1024 * 1024, encoding: 'utf8' });
    const cut = raw.lastIndexOf('\n');
    return route.fulfill({ status: parseInt(raw.slice(cut + 1), 10), contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: raw.slice(0, cut) });
  });
}
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => document.querySelectorAll('[data-testid=chart-axis-pole]').length >= 2, null, { timeout: 45000 });
await page.waitForTimeout(2500);
const decline = page.getByRole('button', { name: 'Decline' });
if (await decline.count()) await decline.first().click().catch(() => {});
const rows = await page.evaluate(() => {
  const gutters = [...document.querySelectorAll('div[style*="width: 28px"]')].filter((g) => g.children.length === 2);
  return gutters.map((g) => {
    const c = g.getBoundingClientRect();
    const [a, b] = [...g.children].map((p) => {
      const r = p.getBoundingClientRect();
      const label = p.querySelector('[data-axis-label]') || [...p.querySelectorAll('span')].find((s) => s.className.includes('uppercase'));
      // The glyphs, not the box: a squeezed pole's box can sit inside the gutter
      // while its text wraps or spills past it.
      let ink = { top: r.top, bottom: r.bottom };
      // A capped pole clips its name (#8392), so there the box IS the visible extent.
      if (label && label.firstChild && p.getAttribute('data-capped') !== 'true') {
        const range = document.createRange();
        range.selectNodeContents(label);
        const rr = range.getBoundingClientRect();
        ink = { top: rr.top, bottom: rr.bottom, width: rr.width };
      }
      return {
        inkTop: Math.round(ink.top - c.top),
        inkBottom: Math.round(ink.bottom - c.top),
        inkWidth: Math.round(ink.width || 0),
        top: Math.round(r.top - c.top),
        bottom: Math.round(r.bottom - c.top),
        capped: p.getAttribute('data-capped') === 'true',
        text: label ? label.textContent.trim() : '',
        clipped: label ? label.scrollHeight > label.clientHeight + 1 : false,
      };
    });
    // Home is drawn above away; with rotate(180deg) the ink of a pole spans its box.
    const top = a.inkTop < b.inkTop ? a : b;
    const low = top === a ? b : a;
    const gap = Math.min(low.top, low.inkTop) - Math.max(top.bottom, top.inkBottom);
    const overflow = Math.max(low.bottom, low.inkBottom) - Math.round(c.height);
    // More than one sideways column of text (~16px each) = the name wrapped.
    const wrapped = [a, b].some((p) => p.inkWidth > 20);
    return { gutterH: Math.round(c.height), home: a, away: b, gap, overflow, wrapped, ok: gap >= 0 && overflow <= 0 && !wrapped };
  });
});
console.log(JSON.stringify({ url, rows }, null, 1));
const gutters = await page.$$('div[style*="width: 28px"]');
let i = 0;
for (const g of gutters) {
  const chart = await g.evaluateHandle((e) => e.parentElement);
  await chart.asElement().scrollIntoViewIfNeeded();
  await chart.asElement().screenshot({ path: `${prefix}-${i++}.png` });
}
await browser.close();
