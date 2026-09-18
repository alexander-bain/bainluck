// ux1324-trailing-gap-probe-6802.mjs <url> — WHAT IS HOLDING THE BLANK OPEN?
//
// #6802: an MMA concept page leaves ~950 CSS px — 2.4 phone screens — between its
// one card and the footer, and the gap GROWS as content shrinks. "Something
// reserves height for what did not render" is a hypothesis; this turns it into a
// name, because the fix is different for each answer:
//
//   - a rendered element with a real height   -> that component's own min-height
//   - an EMPTY element with a height          -> a reserved slot (the hypothesis)
//   - no element at all in the band           -> a margin/padding on an ancestor,
//                                                or the main's own min-height
//
// Prints the main column's direct children with their heights, whether they are
// visually empty, and their computed min-height — then names whatever spans the
// widest empty band. Read the OUTPUT, not the exit code.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 measured, 2 usage, 1 camera/navigation.
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

// 🔴 THE VIEWPORT HEIGHT IS PART OF THE MEASUREMENT, WHICH IS WHY IT IS AN
// ARGUMENT. `look.sh` defaults to 2200px tall, and a `min-h-screen` wrapper makes
// the document exactly as tall as whatever you asked for — so a trailing blank
// measured off a default shot can be the CAMERA's, not the page's. Measure a
// phone (844) before you believe one.
const [url, heightArg] = process.argv.slice(2);
if (!url) { console.error('usage: … <url> [viewportHeight=844]'); process.exit(2); }
const viewportHeight = Number(heightArg) || 844;

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: viewportHeight } });
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
await page.waitForTimeout(4000);

const report = await page.evaluate(() => {
  const describe = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      cls: String(el.className || '').slice(0, 70),
      top: Math.round(r.top + window.scrollY),
      height: Math.round(r.height),
      text: (el.innerText || '').trim().length,
      minH: cs.minHeight,
      mt: cs.marginTop,
      mb: cs.marginBottom,
      pb: cs.paddingBottom,
    };
  };

  const main = document.querySelector('main') || document.body;
  const children = [...main.children].map(describe);

  // The widest vertical band inside `main` that no rendered TEXT occupies.
  const boxes = [...main.querySelectorAll('*')]
    .filter((el) => (el.innerText || '').trim().length > 0)
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.height > 0)
    .map((r) => [r.top + window.scrollY, r.bottom + window.scrollY])
    .sort((a, b) => a[0] - b[0]);
  let gapStart = 0, gapSize = 0, cursor = 0;
  for (const [t, b] of boxes) {
    if (t - cursor > gapSize) { gapSize = t - cursor; gapStart = cursor; }
    cursor = Math.max(cursor, b);
  }

  // Everything that SPANS that band, innermost first — the suspects.
  const spanning = [...main.querySelectorAll('*')]
    .filter((el) => {
      const r = el.getBoundingClientRect();
      const top = r.top + window.scrollY;
      return top <= gapStart + 2 && top + r.height >= gapStart + gapSize - 2 && r.height > 40;
    })
    .map(describe)
    .sort((a, b) => a.height - b.height)
    .slice(0, 8);

  const footer = document.querySelector('footer');
  const fr = footer ? footer.getBoundingClientRect() : null;
  const mr = main.getBoundingClientRect();

  return {
    viewport: window.innerHeight,
    docHeight: document.documentElement.scrollHeight,
    mainBottom: Math.round(mr.bottom + window.scrollY),
    footerTop: fr ? Math.round(fr.top + window.scrollY) : null,
    mainToFooter: fr ? Math.round(fr.top + window.scrollY - (mr.bottom + window.scrollY)) : null,
    mainTag: main.tagName.toLowerCase(),
    mainMinHeight: getComputedStyle(main).minHeight,
    children,
    gap: { start: Math.round(gapStart), size: Math.round(gapSize) },
    spanning,
  };
});

console.log(JSON.stringify(report, null, 1));
await browser.close();
