// shop-shot.mjs <url> <out.png> [clickText] — headless screenshot of a production page.
//
// Why this exists instead of `npx playwright screenshot`: Chromium's default multi-process
// launch dies in the agent sandbox (`bootstrap_check_in ... Permission denied (1100)`), and the
// browser does not inherit the session egress proxy. Both are fixed by the args below:
//   --single-process        clears the Mach port rendezvous the sandbox blocks
//   --proxy-server=$HTTPS_PROXY --proxy-bypass-list=<-loopback>   gives the browser egress
// --single-process supports exactly ONE context, so this launches a fresh browser per page.
//
// Also dismisses the cookie banner, which otherwise covers real content in every full-page shot.
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
// #3968: the decision logic lives in a browser-free module so it can be guarded
// by `frontend/e2e/contract/lookClickContract.contract.test.js`. Importing THIS
// file starts Chromium, so nothing in it is reachable from a test — which is why
// #3932's behaviours shipped verified only by hand.
import {
  EXIT_CAMERA,
  EXIT_CLICK_FAILED,
  EXIT_USAGE,
  clearStaleArtifact,
  clickFailHint,
  parseClickSteps,
  parseScroll,
  readStep,
} from './shot-click-contract.mjs';

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
const [url, out, clickText] = process.argv.slice(2);
if (!url || !out) {
  console.error('usage: shop-shot.mjs <url> <out.png> [clickText]');
  console.error('  SHOT_CLICKS="step;step"  tap a SEQUENCE before shooting. A step starting');
  console.error('                           with [ . or # is a CSS selector, else exact text.');
  console.error('  SHOT_CLICK_OPTIONAL=1    restore the old best-effort taps (see #3932).');
  process.exit(EXIT_USAGE);
}

// #3932: a tap that did not happen must not produce a pass-looking artifact.
//
// The old shape caught every click failure, printed CLICKFAIL to stderr, and
// carried on to `ok = true` / exit 0 — so a shot of the UN-TAPPED page came back
// with a filename saying otherwise, and `look.sh` (which only checks that a PNG
// exists) read it as a clean pass. Under the LOOK RULE that PNG is the proof a
// rendered-surface change is done, so for any surface behind a tap the proof was
// unfalsifiable in the failing direction. ux/1052 already lost a pass this way.
//
// The sibling rail had already worked this out: `tools/look-local.mjs` exits 4 on
// a click target it cannot find, because "a click that does not land must not
// produce a PNG — exiting here is the only way the caller finds out". The two
// halves of one rail disagreed; this is them agreeing.
//
// EXIT CODES ARE A STORY (gotcha #124): 2 usage, 3 a tap that did not land,
// 1 anything else. `SHOT_CLICK_OPTIONAL=1` restores best-effort for a caller who
// genuinely wants "tap it if it's there" — it is never the default, because the
// default is what silently lied.
const CLICK_OPTIONAL = process.env.SHOT_CLICK_OPTIONAL === '1';
const { steps: clickSteps, warning: clickWarning } = parseClickSteps({
  envClicks: process.env.SHOT_CLICKS,
  clickText,
});
if (clickWarning) console.error(clickWarning);

// A failed run must not leave the PREVIOUS run's screenshot sitting at the path
// this run's filename claims — that is the same class one level out, and it is
// how a reader ends up judging a photograph of something else entirely.
clearStaleArtifact(out);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let ok = false;
try {
  const W = parseInt(process.env.SHOT_W || '1280', 10);
  const H = parseInt(process.env.SHOT_H || '2200', 10);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(7000);
  try {
    await page.getByRole('button', { name: /Decline|Accept/ }).first().click({ timeout: 6000 });
    await page.waitForTimeout(2500);
  } catch { /* no banner on this page */ }
  // Each step in order; a step is a CSS selector when it starts with [ . or #,
  // otherwise the exact visible text. Selectors are what make a surface behind a
  // pill, an icon button or a `data-testid` reachable at all — `getByText` with
  // `exact: true` can only ever address a visible-text node.
  for (const step of clickSteps) {
    // HOW A STEP IS READ, and why guessing is not good enough.
    //
    // The first cut used only the shorthand below — a step is a CSS selector if
    // it starts with [ . or #, else it is text. That silently mis-read
    // `a[href="/sport/football/nfl"]`, which starts with `a`, as a demand for a
    // visible-text node reading literally `a[href="/sport/football/nfl"]`. Zero
    // matches, and before this ship that was a screenshot of the un-tapped page.
    // Tag-qualified selectors (`a[href=…]`, `button.pill`, `nav a`) are the
    // normal way to address exactly the controls text cannot reach, so the
    // heuristic was wrong for the main case it exists to serve.
    //
    // So: `css=` and `text=` say it outright and are never ambiguous. The
    // shorthand stays for the [ . # forms already in the issue. A bare step is
    // text, as the positional `clickText` always was.
    const { isSelector, sel } = readStep(step);
    // `.filter({ visible: true })` BEFORE `.first()`, and it is load-bearing.
    //
    // The old line was a bare `.first()`, which takes the first node in DOM
    // order whether or not it is on screen. Measured on bainluck.com at 390px:
    // `getByText('Sports', { exact: true })` resolves THREE nodes, and node 0 is
    // the desktop nav — `visible=false`, `boundingBox=null`. Playwright waits for
    // actionability, so the click times out on an invisible element while the
    // bottom-nav tab a reader can plainly see sits at node 2, untouched.
    // `a[href="/sports"]` has the identical shape.
    //
    // That is this issue's own bug wearing responsive CSS: the rail reports on a
    // node nobody can see. Silently it produced a screenshot of the un-tapped
    // page; loudly (above) it would fail on targets that are right there. Fixing
    // only the loudness would have turned a false pass into a false failure.
    const all = isSelector ? page.locator(sel) : page.getByText(sel, { exact: true });
    const target = all.filter({ visible: true }).first();
    let landed = false;
    try {
      await target.click({ timeout: 15000 });
      landed = true;
    } catch (e) {
      const why = e.message.split('\n')[0];
      // Name the reading that failed, not just the failure. "no exact-text node
      // reads `a[href=…]`" is a different problem from "the button is covered",
      // and the caller cannot tell them apart from a bare timeout.
      console.error(`CLICKFAIL ${step} :: ${why}${clickFailHint(isSelector)}`);
      if (!CLICK_OPTIONAL) {
        // Before the screenshot on purpose: exiting here is what guarantees no
        // artifact exists to be mistaken for a pass.
        await browser.close();
        process.exit(EXIT_CLICK_FAILED);
      }
    }
    // Only on the success path. A `CLICKED` line printed after a CLICKFAIL is
    // the same lie in miniature — the log would say the tap happened.
    if (landed) {
      await page.waitForTimeout(6000);
      console.error(`CLICKED ${step}`);
    }
  }

  // ux/1092: SHOT_SCROLL turns the full-page shot into a VIEWPORT shot.
  //
  // fullPage is right for most pages and useless on a long one. `/hub/tennis`
  // at 390px is 44,729px tall; the PNG comes back 1332x89458, and every reader
  // that has to fit an image into a bounded view downscales it to a ~30px-wide
  // strip. The LOOK rule says screenshot the page and JUDGE it — a capture
  // nobody can read passes the first half and silently fails the second.
  //
  // So: unset (the default) is fullPage exactly as before. A number is a
  // scroll offset in CSS pixels, and the shot is the viewport at that offset —
  // one readable screen. `top` is 0. The document height goes to stderr either
  // way, because knowing a page is 53 screens tall is itself a finding.
  const docHeight = await page.evaluate(() => document.body.scrollHeight);
  const scroll = process.env.SHOT_SCROLL;
  const shot = parseScroll(scroll);
  if (shot.mode === 'error') {
    console.error(shot.message);
    process.exit(EXIT_USAGE);
  }
  if (shot.mode === 'fullPage') {
    await page.screenshot({ path: out, fullPage: true });
  } else {
    await page.evaluate((to) => window.scrollTo(0, to), shot.y);
    // Let lazy rails and any scroll-triggered animation settle before the shot.
    await page.waitForTimeout(2500);
    await page.screenshot({ path: out });
  }
  console.error(`docHeight=${docHeight} mode=${shot.mode === 'fullPage' ? 'fullPage' : `viewport@${scroll}`}`);
  ok = true;
  console.log(out);
} catch (e) {
  console.error(`FAIL ${url} :: ${e.message}`);
} finally {
  await browser.close();
}
// The last place the exit-code vocabulary was still a literal (#4032 item 5).
// `EXIT_CAMERA` is 1, so this changes no behaviour today — it changes what a
// future edit has to do to stay coherent. Two of the three codes came from the
// shared module and the third was typed here, which is exactly how a
// vocabulary drifts: renumber `EXIT_CAMERA` and this line would have gone on
// meaning the old thing while every reader of the constant meant the new one.
process.exit(ok ? 0 : EXIT_CAMERA);
