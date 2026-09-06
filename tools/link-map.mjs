// link-map.mjs <url> [textFilter] — print every /events/<id> href a production page renders.
// Same sandbox-safe launch as shop-shot.mjs (see its header for why the args are required).
// A screenshot proves what a card LOOKS like; this proves where the card SENDS you.
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

const [url, filter] = process.argv.slice(2);
if (!url) { console.error('usage: link-map.mjs <url> [textFilter]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(7000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(1500);
  } catch { /* no banner */ }
  // Scroll the whole page so lazy rails mount before we read the DOM.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 800) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(2500);
  const links = await page.$$eval('a[href]', (as) =>
    as
      .map((a) => ({ href: a.getAttribute('href'), text: a.innerText.replace(/\s+/g, ' ').trim().slice(0, 80) }))
      .filter((l) => /\/events?\//.test(l.href || ''))
  );
  const seen = new Set();
  for (const l of links) {
    const key = l.href + l.text;
    if (seen.has(key)) continue;
    seen.add(key);
    if (filter && !l.text.toLowerCase().includes(filter.toLowerCase())) continue;
    console.log(`${l.href}\t${l.text}`);
  }
  console.error(`total event links: ${links.length}`);
} finally {
  await browser.close();
}
