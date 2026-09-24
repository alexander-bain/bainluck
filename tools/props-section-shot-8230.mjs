// props-section-shot-8230.mjs <url> <out.png> — photograph the WHAT HIT / THE SCRIPT section
// (`#props-script`) at phone width and print what a reader reads in it.
//
// #8230: a finished game's WHAT HIT board printed every question twice, once green and once red.
// The element shot is the evidence; the printed counts (families, rows, verdict chips by colour) are
// how the same picture is compared before and after without eyeballing 50 rows.
//
// Sandbox launch flags are phone-shot.mjs's, for the same reasons (see that file).
//
//   node tools/props-section-shot-8230.mjs https://bainluck.com/events/15316869 /tmp/wh.png
import { createRequire } from 'module';
import { existsSync, readdirSync, statSync } from 'fs';

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
if (!url || !out) {
  console.error('usage: props-section-shot-8230.mjs <url> <out.png>');
  process.exit(2);
}

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let ok = false;
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(Number(process.env.SHOT_SETTLE_MS || 9000));
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(1500);
  } catch { /* no banner */ }
  const section = page.locator('#props-script');
  await section.waitFor({ timeout: 20000 });
  await section.scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  const read = await section.evaluate((el) => {
    const chips = [...el.querySelectorAll('span.rounded-full')].map((c) => ({
      text: c.textContent.trim(),
      cls: c.className.includes('accent-danger') ? 'red' : c.className.includes('accent-brand') ? 'green' : 'other',
    }));
    const eyebrow = el.querySelector('span')?.textContent?.trim();
    const blurb = el.querySelector('p')?.textContent?.trim();
    return {
      eyebrow,
      blurb,
      chips: chips.length,
      green: chips.filter((c) => c.cls === 'green').length,
      red: chips.filter((c) => c.cls === 'red').length,
      text: el.innerText.split('\n').filter(Boolean).slice(0, 40),
    };
  });
  const allCount = await page.locator('summary', { hasText: /^All \d+/ }).first().textContent().catch(() => null);
  console.log(JSON.stringify({ url, allCount: allCount?.trim() ?? null, ...read }, null, 1));
  await section.screenshot({ path: out });
  ok = true;
} catch (e) {
  console.error(`FAIL ${url} :: ${e.message}`);
} finally {
  await browser.close();
}
if (ok && (!existsSync(out) || statSync(out).size === 0)) ok = false;
if (ok) console.log(`${out} (${statSync(out).size} B)`);
process.exit(ok ? 0 : 1);
