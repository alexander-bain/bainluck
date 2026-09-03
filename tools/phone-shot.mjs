// phone-shot.mjs <url> <out.png> — a D48 LOOK at PHONE width, of a real production page.
//
// WHY A SECOND CAMERA. `~/bainluck/tools/shop-shot.mjs` is the LOOK rail every lane uses and it
// photographs at 1280x2200. That is the right default for a mystery shop of a desktop layout and the
// wrong one for a latency ship: every number this lane registers — `felt-load.mjs`, `felt-waterfall.mjs`
// — is measured at 390x844 with deviceScaleFactor 3 on a Slow-4G profile, because that is the reader
// the bar is about. A before/after pair shot at 1280 is a picture of a layout nobody in the measurement
// ever saw. This matches the felt rig's viewport exactly, on purpose: the picture and the number have
// to be about the same reader or neither corroborates the other.
//
// 🔴 `~/bainluck/tools/shop-shot.mjs` AND `~/bainluck/tools/look.sh` ARE UNTRACKED (checked
// 2026-09-03). They exist on one laptop and are in no commit, which CLAUDE.md's launcher rule calls
// lost work rather than a local preference. This file does not fix that — it is a different camera for
// a different job — but whoever owns the LOOK rail should track those two.
//
// The sandbox workarounds are inherited verbatim from shop-shot.mjs and are not optional:
//   --single-process        clears the Mach port rendezvous the agent sandbox blocks
//   --proxy-server=$HTTPS_PROXY --proxy-bypass-list=<-loopback>   gives the browser egress
// --single-process supports exactly ONE context, so this launches a fresh browser per page.
//
//   node tools/phone-shot.mjs https://www.bainluck.com/events/12345 /tmp/before.png
//
// Exits non-zero if no PNG lands. A camera that exits 0 having photographed nothing is how a dead rail
// reads as a clean pass (ux/976 rewrote look.sh for exactly that).
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
  console.error('usage: phone-shot.mjs <url> <out.png>');
  process.exit(2);
}

// Same numbers as tools/felt-waterfall.mjs. Change them in both or in neither.
const WIDTH = Number(process.env.SHOT_WIDTH || 390);
const HEIGHT = Number(process.env.SHOT_HEIGHT || 844);
const SETTLE_MS = Number(process.env.SHOT_SETTLE_MS || 9000);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let ok = false;
try {
  const page = await browser.newPage({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  // Long settle on purpose. The whole subject of this lane is a surface that paints a skeleton first
  // and fills it a second or two later; a shot taken at `load` would photograph the spinner and call
  // it the page.
  await page.waitForTimeout(SETTLE_MS);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(2000);
  } catch { /* no banner on this page */ }
  await page.screenshot({ path: out, fullPage: true });
  ok = true;
} catch (e) {
  console.error(`FAIL ${url} :: ${e.message}`);
} finally {
  await browser.close();
}

// -s, not just existence: playwright can leave a zero-byte file behind on a partial write.
if (ok && (!existsSync(out) || statSync(out).size === 0)) {
  console.error(`phone-shot: no bytes written for ${url}`);
  ok = false;
}
if (ok) console.log(`${out} (${WIDTH}x${HEIGHT} @3x, ${statSync(out).size} B)`);
process.exit(ok ? 0 : 1);
