// #6250 — where is the CHAMPIONSHIP ODDS grid on a league page, and what does it say?
// Prints the section's y-offset (CSS px, for SHOT_SCROLL / a crop) and its row labels,
// so a LOOK on a 23,000px page aims at the block instead of hunting for it.
// Usage: node lane1b-275-grid-section-offset.mjs <url> [headingText]
import { existsSync, readdirSync } from 'fs';
import { createRequire } from 'module';
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
const heading = (process.argv[3] || 'CHAMPIONSHIP ODDS').toUpperCase();
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
const b = await chromium.launch({ headless: true, args });
const pg = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await pg.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
for (let y = 0; y < 16; y++) {
  await pg.evaluate((n) => window.scrollTo(0, n * 800), y);
  await pg.waitForTimeout(300);
}
await pg.evaluate(() => window.scrollTo(0, 0));
await pg.waitForTimeout(800);
const out = await pg.evaluate((h) => {
  const all = [...document.querySelectorAll('*')];
  const hit = all.find((e) => (e.textContent || '').trim().toUpperCase().startsWith(h)
    && e.children.length === 0);
  if (!hit) return { found: false, docHeight: document.documentElement.scrollHeight };
  let box = hit.getBoundingClientRect();
  const top = Math.round(box.top + window.scrollY);
  // the table/list that follows the heading
  let sec = hit;
  for (let i = 0; i < 6 && sec.parentElement; i++) sec = sec.parentElement;
  return {
    found: true,
    docHeight: document.documentElement.scrollHeight,
    headingTop: top,
    sectionText: (sec.innerText || '').slice(0, 2500),
  };
}, heading);
console.log(JSON.stringify(out, null, 1));
await b.close();
