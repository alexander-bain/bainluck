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
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');
const b = await chromium.launch({ headless: true, args });
const pg = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await pg.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
// scroll the whole page so anything lazy mounts
for (let y = 0; y < 12; y++) {
  await pg.evaluate((n) => window.scrollTo(0, n * 800), y);
  await pg.waitForTimeout(350);
}
await pg.waitForTimeout(1500);
const txt = await pg.evaluate(() => document.body.innerText);
console.log('=== full page innerText ===');
console.log(txt);
await b.close();
