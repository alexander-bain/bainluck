// lane1b-272-market-verdict-text.mjs <url> <needle> [out.png]
//
// WHY: #5221's harm is a stored verdict, and the question a LOOK has to answer is not "is the
// number wrong in the table" (I proved that with arithmetic on the linescore) but "does a reader
// meet the wrong verdict IN WORDS on the page". A tall whole-page PNG cannot answer that — the
// 2H market sits somewhere in 7,311px of event page and a downscaled strip is not a LOOK
// (look.sh's own header says so). So: ask the DOM where the text is, PRINT what the block says,
// and shoot that viewport so the picture and the transcript are the same evidence.
//
// It prints the matched block's innerText because the transcript is the finding: "Boston wins 2nd
// half — WON" is the defect in the reader's own words, and a PNG alone leaves the next session
// re-reading pixels to quote it.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 found and shot · 2 usage · 4 the needle is not on the
// page at all (the market does not render for a reader — a DIFFERENT and reportable finding, not
// a camera failure) · 1 anything else.
import { createRequire } from 'module';
import { existsSync, readdirSync, rmSync } from 'fs';

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
const [url, needle, out] = process.argv.slice(2);
if (!url || !needle) {
  console.error('usage: lane1b-272-market-verdict-text.mjs <url> <needle> [out.png]');
  process.exit(2);
}
if (out && existsSync(out)) rmSync(out);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let code = 1;
try {
  const W = parseInt(process.env.SHOT_W || '390', 10);
  const H = parseInt(process.env.SHOT_H || '844', 10);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  // A client-rendered event page serves "Loading event..." for seconds. Asking the DOM before the
  // fetch resolves reports every needle ABSENT — an unloaded page is indistinguishable from a
  // missing market unless you wait for the placeholder to go. Control-probe any absence.
  try {
    await page.waitForFunction(() => !document.body.innerText.includes('Loading event'), { timeout: 45000 });
  } catch {
    console.error('WARNING: "Loading event..." never cleared — any ABSENT below is untrustworthy.');
  }
  await page.waitForTimeout(5000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 5000 });
    await page.waitForTimeout(2000);
  } catch { /* no banner */ }
  await page.mouse.move(W - 2, 2);

  // Grow the page once so anything that mounts on intersection has mounted before we ask.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(2500);

  // Markets live behind "10 more" / "Show more" collapses (D102 put untraded props behind a
  // toggle deliberately). A needle reported ABSENT from an unexpanded page is a statement about
  // the toggle, not about the data — open every expander before asking.
  for (let round = 0; round < 6; round++) {
    const clicked = await page.evaluate(() => {
      const re = /^\s*(\d+\s+more|show\s+more|see\s+all|more\b)/i;
      const els = Array.from(document.querySelectorAll('button,[role="button"],summary,a'));
      let n = 0;
      for (const el of els) {
        const t = (el.innerText || '').trim();
        if (re.test(t) && el.getClientRects().length > 0) { el.click(); n++; }
      }
      return n;
    });
    if (!clicked) break;
    await page.waitForTimeout(1200);
  }
  await page.waitForTimeout(1500);

  const hit = await page.evaluate((n) => {
    const want = n.toLowerCase();
    // Smallest element whose OWN text carries the needle, then climb to a block with context.
    // innerText falls back to textContent on a NON-RENDERED element, so <script> returns the whole
    // Next.js JSON payload and every needle "matches". A reader cannot read a script tag: require
    // the node to have layout, and skip the non-rendered tags outright.
    const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'HEAD', 'META', 'LINK', 'TITLE']);
    const all = Array.from(document.querySelectorAll('body *')).filter(
      (el) => !skip.has(el.tagName) && el.getClientRects().length > 0,
    );
    const matches = all.filter((el) => (el.innerText || '').toLowerCase().includes(want));
    if (!matches.length) return null;
    let el = matches[matches.length - 1]; // deepest
    for (let i = 0; i < 4 && el.parentElement; i++) {
      if ((el.innerText || '').split('\n').filter(Boolean).length >= 3) break;
      el = el.parentElement;
    }
    const r = el.getBoundingClientRect();
    return {
      y: Math.round(r.top + window.scrollY),
      h: Math.round(r.height),
      docHeight: document.body.scrollHeight,
      text: (el.innerText || '').slice(0, 1200),
    };
  }, needle);

  if (!hit) {
    console.error(`NEEDLE ABSENT: "${needle}" is nowhere in the rendered page.`);
    code = 4;
  } else {
    console.log(`docHeight=${hit.docHeight} needle_y=${hit.y} block_h=${hit.h}`);
    console.log('--- BLOCK TEXT ---');
    console.log(hit.text);
    console.log('--- END BLOCK ---');
    if (out) {
      const top = Math.max(0, hit.y - 120);
      await page.evaluate((y) => window.scrollTo(0, y), top);
      await page.waitForTimeout(1200);
      await page.screenshot({ path: out });
      console.log(`shot ${out} at scroll ${top}`);
    }
    code = 0;
  }
} catch (e) {
  console.error('PROBE FAILED:', e.message);
  code = 1;
} finally {
  await browser.close();
}
process.exit(code);
