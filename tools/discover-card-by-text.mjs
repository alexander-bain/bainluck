// discover-card-by-text.mjs <url> <out.png> <text> — shoot the Discover card containing <text>.
//
// WHY A SCROLL-TO-ELEMENT PROBE EXISTS (discover/030, D1 #4066).
//
// `look.sh SHOT_SCROLL=<px>` needs a pixel offset, and Discover has no stable one: the feed
// reshuffles between requests, so the index you read out of `/api/feed` a second earlier is not
// the index the browser renders. discover/029 lost a LOOK to exactly this (shot docHeight=15550
// then 8744 a minute apart and scrolled past the card it wanted), and its advice — find the index
// in the payload first, then shoot that offset — still races, because the payload read and the
// browser's own fetch are two different draws from a shuffled deck.
//
// So this addresses the card the way a reader would: by what it SAYS. It scrolls the page until a
// card whose text contains <text> (case-insensitive substring) is on screen, or reports honestly
// that the deal it was dealt does not contain one. It also prints the matched card's full text, so the caption under test is evidence
// in the log as well as in the PNG.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 no card matched after scrolling the
// whole page, 1 anything else. 4 is DISTINCT from 1 on purpose — "this load did not contain the
// specimen" is a re-run, while "the camera failed" is not, and a caller that cannot tell them
// apart will read a dead camera as a clean AFTER (the #4056 / ux-1052 failure mode).
//
// A no-match writes NO PNG and deletes any stale one at that path, for the same reason shop-shot
// does: an artifact whose filename claims a specimen it does not contain is worse than no artifact.
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
const [url, out, needle] = process.argv.slice(2);
if (!url || !out || !needle) {
  console.error('usage: discover-card-by-text.mjs <url> <out.png> <text>');
  console.error('  <text> is matched as a case-insensitive SUBSTRING of the card\'s innerText.');
  console.error('  SHOT_W / SHOT_H   viewport (default 390x844 — this is a phone-first surface)');
  console.error('  SHOT_PAGES        how many auto-pager pulls to allow (default 3)');
  process.exit(2);
}
if (existsSync(out)) rmSync(out);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let code = 1;
try {
  const W = parseInt(process.env.SHOT_W || '390', 10);
  const H = parseInt(process.env.SHOT_H || '844', 10);
  const maxPages = parseInt(process.env.SHOT_PAGES || '3', 10);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(7000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(2500);
  } catch { /* no banner on this page */ }
  // No pointer on a touch surface (#4408) — a hover state in a LOOK is never evidence.
  await page.mouse.move(W - 2, 2);

  // Walk down the page, letting the auto-pager pull more cards, until a match is on the page.
  //
  // SUBSTRING, NOT A REGEX, and that is a fix rather than a simplification: building a RegExp out
  // of argv is a regular-expression injection (CodeQL flagged exactly that on this file's first
  // sha, high severity, and standing notice 32 refused it). Every caller so far passes a literal
  // phrase a reader can see on the card — "opening price" — so the expressive power was never used
  // and only the injection surface was real.
  let found = null;
  for (let pass = 0; pass <= maxPages; pass++) {
    found = await page.evaluate((src) => {
      const wanted = src.toLowerCase();
      // The card root the feed actually renders. Fall back to any element that both matches and
      // has no matching descendant, so this keeps working if the class hook is renamed.
      const nodes = Array.from(document.querySelectorAll('article, [data-card], [class*="card" i]'));
      const hit = nodes.find((n) => (n.innerText || '').toLowerCase().includes(wanted));
      if (!hit) return null;
      const r = hit.getBoundingClientRect();
      return { top: r.top + window.scrollY, height: r.height, text: (hit.innerText || '').slice(0, 600) };
    }, needle);
    if (found) break;
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(4000);
  }

  if (!found) {
    const docHeight = await page.evaluate(() => document.body.scrollHeight);
    console.error(`NOMATCH "${needle}" docHeight=${docHeight} — this load did not deal the specimen; re-run`);
    code = 4;
  } else {
    // Centre the card rather than putting it at y=0: a card flush to the top edge is
    // indistinguishable in the PNG from one clipped by the sticky header.
    const to = Math.max(0, Math.round(found.top - (H - found.height) / 2));
    await page.evaluate((y) => window.scrollTo(0, y), to);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: out });
    console.error(`MATCH at y=${Math.round(found.top)} h=${Math.round(found.height)} shot@${to}`);
    console.error(`--- card text ---\n${found.text}\n-----------------`);
    console.log(out);
    code = 0;
  }
} catch (e) {
  console.error(`FAIL ${url} :: ${e.message}`);
  if (existsSync(out)) rmSync(out);
} finally {
  await browser.close();
}
process.exit(code);
