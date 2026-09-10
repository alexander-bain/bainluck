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
  chooseCapture,
  clearStaleArtifact,
  clickFailHint,
  parseClickSteps,
  parseScroll,
  pointerParkPoint,
  readStep,
  scrollReachReport,
  scrollTargetIsBeyondDocument,
  shouldParkPointer,
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
  // Notice 39 / #1916 rung 1: say who we are. Every shot this tool takes is a real
  // request to production, and `look.sh` delegates here, so this one call site is the
  // whole fleet — nine lanes plus the bus's probes.
  //
  // 🔴 This is not cosmetic labelling: `x-bainluck-origin` is READ by the backend
  // (`routes/events.py:_request_is_automation`) and any non-empty value other than the
  // literal "user" SUPPRESSES the search-query log write and the trending vote. So
  // before this, every `look.sh <…/search?q=X>` shot voted X into the search head that
  // the warmer then warms — our own screenshot tool was shaping the thing it photographs.
  //
  // Shoot deliberately AS a person with `BL_AGENT=user` (the backend honours that
  // spelling positively); that is the only value that keeps the row.
  const AGENT = process.env.BL_AGENT || 'look.sh';

  // 🔴 Deliberately NOT also suffixing the User-Agent with `BainLuckBot/1.0`, which
  // notice 39 asks for. Appending to a UA means first READING it, and the only way to
  // read it is a second context — which this browser cannot give: it is launched
  // `--single-process`, and the probe context closes the browser under the real page
  // (`browser.newPage: Target page, context or browser has been closed`, reproduced
  // locally before this shipped). Replacing the UA outright is worse: this tool exists
  // to photograph what a PERSON sees, and a bot UA can change what the site serves.
  //
  // No loss. The header is what the backend actually reads and what notice 39 point 4
  // wants the rate-limit allowlist keyed on ("allowlist by header, not IP"). The UA is
  // the one carrier with no reader and a real failure mode.
  //
  // 🔴 A `bl_agent` COOKIE used to be set here too, for rung 3's client-analytics drop.
  // It is gone and must not come back: rung 3 is WITHDRAWN because all four client rails
  // were already agent-free, so nothing ever read it (#4606, #4608).
  //   - GA4, Vercel Analytics and Web Vitals are consent-gated. A fresh Playwright
  //     context has no stored consent, so `decideTelemetry(null)` returns NOTHING.
  //   - Speed Insights — the one UNGATED rail (D30) — drops us at the VENDOR level. Its
  //     loaded script opens with the equivalent of
  //     `if (navigator.webdriver || navigator.userAgent.includes("Headless")) return;`
  //     before it reads any config, and this browser trips both tells.
  // Measured on production 2026-09-09, two arms of one run: identical script and dataset
  // both times, 0 vitals beacons as stock Playwright, 2 POSTs to `<basePath>/vitals` with
  // those two tells removed. Re-adding a cookie would be inert code carrying a live bug
  // (#4608: it was set on the APEX origin while the shot redirects to www, so it never
  // reached the page even once).
  const page = await browser.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: 2,
    extraHTTPHeaders: { 'x-bainluck-origin': AGENT },
  });
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
    // VISIBLE BEFORE `.first()`, and it is load-bearing.
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
    //
    // WHY THE SELECTOR ENGINE AND NOT `.filter({ visible: true })` (#4032).
    //
    // The filter option is sugar added in Playwright 1.51, and an OLDER
    // Playwright does not reject it — it accepts the object and drops the key.
    // So the visible-first fix quietly evaporated on any machine resolving an
    // older build, leaving a bare `.first()` and the exact bug it repaired.
    // Measured on this fixture, same page, same viewport:
    //
    //   1.48.2  filter({visible:true}) -> count=2, first = the HIDDEN decoy
    //   1.55.1  filter({visible:true}) -> count=1, first = the visible link
    //   both    locator('visible=true') -> count=1, first = the visible link
    //
    // That is not hypothetical: `findPlaywright()` above prefers whatever
    // `~/.npm/_npx` holds (1.55.1 on the authoring laptop) and falls back to the
    // repo's own lockfile, which pins 1.48.2 — so the laptop passed and CI, and
    // any machine without that npx cache, silently clicked the wrong node. The
    // `visible=true` selector engine has existed since 1.14 and means the same
    // thing in every version this can resolve, so the behaviour no longer
    // depends on which one it got.
    const all = isSelector ? page.locator(sel) : page.getByText(sel, { exact: true });
    const target = all.locator('visible=true').first();
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
  // Park the pointer off-viewport so the shot carries no `:hover` (see
  // `pointerParkPoint`). Before the scroll AND before the shutter: hover is
  // recomputed at the pointer's position on every scroll, so a pointer left on
  // the tab it clicked ends up hovering whatever content scrolls under it.
  if (shouldParkPointer(process.env.SHOT_KEEP_POINTER)) {
    const park = pointerParkPoint({ width: W, height: H });
    await page.mouse.move(park.x, park.y);
    await page.waitForTimeout(300);
  }

  const docHeight = await page.evaluate(() => document.body.scrollHeight);
  const scroll = process.env.SHOT_SCROLL;
  const shot = parseScroll(scroll);
  if (shot.mode === 'error') {
    console.error(shot.message);
    process.exit(EXIT_USAGE);
  }
  // Which capture actually ran, for the stderr line below. A lane reading
  // "mode=fullPage" on a PNG whose chart came out empty has to be able to tell
  // whether it got the grown capture or the #4664-unsafe fallback.
  let capture = shot.mode === 'fullPage' ? 'fullPage' : `viewport@${scroll}`;
  if (shot.mode === 'fullPage') {
    // #4664: `fullPage: true` is NOT a photograph of the page we just measured.
    // Chromium serves it through captureBeyondViewport, which re-renders the
    // document off-screen, remounts every chart, and restarts Recharts' entry
    // animation — so the shutter catches the line at a ~6px dash and the plot
    // comes out EMPTY while a 64-vertex path sits in the DOM. It also stamps
    // the fixed bottom nav across mid-page content. Growing the viewport to the
    // document height and taking an ordinary viewport shot gets both right.
    // The full measurement, in both directions, is on `chooseCapture`.
    const plan = chooseCapture({ docHeight, viewportHeight: H });
    if (plan.warning) console.error(plan.warning);
    if (plan.mode === 'grow') {
      // Growing puts the whole document on screen, so anything that loads on
      // intersection loads now and the page can get TALLER. Re-measure and grow
      // again rather than photograph a page that outgrew its own frame — but
      // bounded, because a page that grows every time it is measured (an
      // infinite feed) would otherwise never reach the shutter.
      let target = plan.height;
      for (let i = 0; i < 2; i++) {
        await page.setViewportSize({ width: W, height: target });
        await page.waitForTimeout(2500);
        const grown = await page.evaluate(() => document.body.scrollHeight);
        const next = chooseCapture({ docHeight: grown, viewportHeight: H });
        if (next.mode !== 'grow' || next.height <= target) break;
        target = next.height;
      }
      // The resize can leave the document scrolled; a whole-page shot starts at 0.
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(500);
      await page.screenshot({ path: out });
      capture = `wholePage@grown${target}`;
    } else {
      await page.screenshot({ path: out, fullPage: true });
      capture = 'fullPage(CHART-UNSAFE)';
    }
  } else {
    // #4749 — REACH a target past the current bottom instead of clamping to the
    // bottom and photographing it under the caller's filename.
    //
    // An infinite-scroll surface only holds the pages the reader has scrolled
    // through: Discover seeds `visibleCount` at 20 and appends the next 20 when
    // its sentinel intersects. So `scrollTo(0, 18000)` on a 7,979px document is
    // not "near the bottom of Discover" — it is the site footer, and until now
    // that came back as a clean shot.
    //
    // Nothing changes for a target INSIDE the document: `scrollTargetIsBeyond‑
    // Document` is false on the first check, the loop never runs, and it is the
    // same one `scrollTo` and one wait it always was.
    let grewTo = docHeight;
    // Bounded at eight pages — far past any LOOK — and a page that has stopped
    // growing breaks on its first no-growth pass regardless.
    for (let step = 0; step < 8; step += 1) {
      if (!scrollTargetIsBeyondDocument({ target: shot.y, docHeight: grewTo, viewportHeight: H })) break;
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      // Long enough for the sentinel's fetch AND its render. A shorter wait
      // reads a page still loading as one that has stopped growing.
      await page.waitForTimeout(3500);
      const next = await page.evaluate(() => document.body.scrollHeight);
      if (next <= grewTo) break; // it will not grow again; stop asking.
      grewTo = next;
    }
    await page.evaluate((to) => window.scrollTo(0, to), shot.y);
    // Let lazy rails and any scroll-triggered animation settle before the shot.
    await page.waitForTimeout(2500);
    const finalY = await page.evaluate(() => Math.round(window.scrollY));
    await page.screenshot({ path: out });
    // Replaces the plain `viewport@N`: same information when the target was
    // reached, plus the growth and a loud refusal when it was not.
    capture = null;
    console.error(scrollReachReport({ target: shot.y, finalY, docHeight, grewTo }).line);
  }
  if (capture !== null) console.error(`docHeight=${docHeight} mode=${capture}`);
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
