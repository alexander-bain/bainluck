// shot-click-contract.mjs — the decision logic behind `shop-shot.mjs`, extracted
// so it can be tested without launching Chromium (#3968).
//
// WHY THIS FILE EXISTS
//
// `shop-shot.mjs` launches a browser at module top level, so importing it starts
// Chromium and nothing in it is reachable from a unit test. That is why #3932's
// six behaviours — all of them decisions, not rendering — shipped verified only
// BY HAND. The thing left unguarded is the rail that proves every other lane's
// rendered-surface work is done (standing notice 4), and it does not fail
// loudly when it regresses: it goes back to handing out plausible screenshots of
// the wrong page, which is unfalsifiable in the failing direction.
//
// So everything here is a PURE function of its arguments: no `process.env`, no
// `process.argv`, no browser, no top-level side effects. The one function that
// touches the filesystem (`clearStaleArtifact`) says so in its name and takes
// its path as an argument.
//
// Its guard is `frontend/e2e/contract/lookClickContract.contract.test.js`, which
// runs in ci.yml's `e2e-contract` job — no install, no network, no browser, and
// in `deploy: needs:`.

import * as nodeFs from "fs";

/**
 * Exit codes. THE VALUE IS THE STORY (gotcha #124): flattened to a single 1,
 * "your selector was nonsense", "the tap never landed so you are looking at the
 * wrong page" and "the camera broke" become one indistinguishable failure.
 */
export const EXIT_USAGE = 2;
export const EXIT_CLICK_FAILED = 3;
export const EXIT_CAMERA = 1;
export const EXIT_IMAGE_BLACKOUT = 5;

/**
 * Should the notice-39 agent tag ride THIS request? (#4903)
 *
 * It used to ride all of them. `shop-shot.mjs` set `x-bainluck-origin` as a
 * context-wide `extraHTTPHeaders`, and Playwright puts those on every request
 * the context makes — including the `<img>` loads Chromium issues in `no-cors`
 * mode. A custom header on a no-cors image request makes Chromium fail the
 * request outright, so from 2026-09-09 17:56 PT every LOOK in the fleet was a
 * photograph of a page with no crests, no faces and no market art.
 *
 * Measured on `/sports/baseball_mlb` at 390px, one A/B with everything else
 * held identical — same browser, args, viewport, DSF and waits:
 *
 * | arm | img elements | naturalWidth 0 | image responses | failures |
 * |---|---|---|---|---|
 * | with the header | 215 | 215 | none | 28 x net::ERR_FAILED |
 * | without it | 215 | 2 | 28 x 200 | none |
 *
 * The tag exists so OUR backend can tell a lane from a person
 * (`routes/events.py:_request_is_automation`). `a.espncdn.com` was never
 * supposed to see it. So it rides our own origins and nothing else.
 *
 * Loopback is included deliberately: the local rail shoots the same app, and a
 * tag that silently drops there would make the two rails disagree about what
 * they are.
 *
 * @param {string} requestUrl
 * @returns {boolean}
 */
export function agentHeaderApplies(requestUrl) {
  let host;
  try {
    host = new URL(requestUrl).hostname;
  } catch {
    return false; // not addressable, so not ours
  }
  if (host === "localhost" || host === "127.0.0.1" || host === "[::1]") return true;
  return host === "bainluck.com" || host.endsWith(".bainluck.com");
}

/**
 * Did the camera, rather than the site, take the pictures out of the page?
 *
 * #3932 was a tap that never landed exiting 0. #4664 was a chart the capture
 * path re-rendered away. This is the third of the same shape, and the shape is
 * what matters: **the rig hands back a plausible screenshot of something other
 * than the page, and exits 0.** Under standing notice 4 that PNG is the proof a
 * rendered-surface change is done, so each time, the done-test became
 * unfalsifiable in the failing direction — and this one is worse than a false
 * positive, because an image ship now photographs identically before and after.
 *
 * The discriminator is deliberately narrow. `failed > 0 && responded === 0` says
 * "every image request died at the network layer before the server answered" —
 * which is the camera. A 404 or a 500 IS a response, so a genuinely broken image
 * on the site still reaches the PNG and still reads as the defect it is. A page
 * with no images at all (`failed === 0`) is not a blackout; it is a page with no
 * images.
 *
 * @param {{responded?: number, failed?: number}} counts
 * @returns {{line: string|null, blackout: boolean}}
 */
export function imageBlackoutReport({ responded = 0, failed = 0 } = {}) {
  const blackout = failed > 0 && responded === 0;
  if (blackout) {
    return {
      blackout: true,
      line:
        `IMAGE-BLACKOUT all ${failed} image request(s) failed at the network layer and none ` +
        `was answered, so this PNG has NO images in it. That is the camera, not the page ` +
        `(#4903): do not file a missing crest, a missing face or a missing image from it, and ` +
        `do not accept it as proof that an image-bearing fix works.`,
    };
  }
  if (failed > 0) {
    return {
      blackout: false,
      line: `images=${responded + failed} answered=${responded} failed=${failed} — the failures are the page's, not the camera's.`,
    };
  }
  return { blackout: false, line: null };
}

/**
 * Decide which click steps to run, and whether to warn about a conflict.
 *
 * `SHOT_CLICKS` wins over the positional `clickText` when both are given, and
 * says so — silently dropping one of two conflicting instructions is how a
 * caller ends up sure they tapped something they did not.
 *
 * @param {{envClicks?: string, clickText?: string}} input
 * @returns {{steps: string[], warning: string|null}}
 */
export function parseClickSteps({ envClicks, clickText } = {}) {
  const envSteps = (envClicks || "")
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);

  const warning =
    envSteps.length && clickText
      ? `SHOT_CLICKS overrides the positional click target "${clickText}"`
      : null;

  const steps = envSteps.length ? envSteps : clickText ? [clickText] : [];
  return { steps, warning };
}

/**
 * Read one step as either a CSS selector or exact visible text.
 *
 * The shorthand (`[`, `.`, `#` ⇒ selector) is kept for the forms already in
 * circulation, but it is NOT sufficient on its own, and that is the #3932 bug:
 * `a[href="/sport/football/nfl"]` starts with `a`, so the shorthand reads it as
 * a demand for a visible-text node whose text is literally
 * `a[href="/sport/football/nfl"]`. Zero matches — and before #3932 that was a
 * screenshot of the un-tapped page. Tag-qualified selectors are the normal way
 * to address exactly the controls text cannot reach, so the heuristic was wrong
 * for the main case it exists to serve.
 *
 * `css=` and `text=` are explicit and always beat the shorthand, including for
 * a text target that happens to start with `[`.
 *
 * @param {string} step
 * @returns {{isSelector: boolean, sel: string}}
 */
export function readStep(step) {
  if (step.startsWith("css=")) return { isSelector: true, sel: step.slice(4) };
  if (step.startsWith("text=")) return { isSelector: false, sel: step.slice(5) };
  return { isSelector: /^[[.#]/.test(step), sel: step };
}

/**
 * The trailing hint on a CLICKFAIL.
 *
 * Name the READING that failed, not just the failure: "no exact-text node reads
 * `a[href=…]`" is a different problem from "the button is covered", and a bare
 * timeout cannot tell them apart. Only meaningful for a text step — a selector
 * that matched nothing needs no disambiguation.
 *
 * @param {boolean} isSelector
 * @returns {string}
 */
export function clickFailHint(isSelector) {
  return isSelector
    ? ""
    : " — read as exact TEXT; if you meant a CSS selector, prefix it `css=`";
}

/**
 * Read `SHOT_SCROLL` into a shot mode.
 *
 * Unset or empty is `fullPage`, unchanged and still the default. `top` is 0. A
 * number is a scroll offset in CSS pixels and the shot is one viewport there.
 * Anything else is a usage error rather than a silent fallback, because
 * defaulting a typo to fullPage is how you get the unreadable 30px strip the
 * option exists to avoid.
 *
 * @param {string|undefined} raw
 * @returns {{mode: 'fullPage'}|{mode: 'viewport', y: number}|{mode: 'error', message: string}}
 */
export function parseScroll(raw) {
  if (raw === undefined || raw === "") return { mode: "fullPage" };
  if (raw === "top") return { mode: "viewport", y: 0 };
  const y = parseInt(raw, 10);
  if (Number.isNaN(y)) {
    return {
      mode: "error",
      message: `SHOT_SCROLL must be a number of pixels or "top", got "${raw}"`,
    };
  }
  return { mode: "viewport", y };
}

/**
 * Is this scroll target BEYOND what the document can currently be scrolled to?
 *
 * #4749. `window.scrollTo(0, y)` clamps silently. On an infinite-scroll surface
 * the document only holds the pages the reader has scrolled through, so a
 * target past the current bottom lands on the bottom — and the shot comes back
 * under a filename saying otherwise. Measured on Discover at 390x844 on
 * 2026-09-10: `SHOT_SCROLL=18000` on a 7,979px document returned a readable
 * photograph of the site FOOTER, exit 0. That is #3932's failure class one
 * level out: plausible, filed under a name that lies, unfalsifiable in the
 * failing direction.
 *
 * Discover seeds `visibleCount` at `PAGE_SIZE = 20` and appends the next 20
 * only when its sentinel intersects, so before this every Discover card past
 * index ~20 was unphotographable — which is why the #4644 after-LOOK could not
 * be paid from page one (its only badge-carrying ladders sat at reader index 23
 * and 39). The caller's remedy is to step to the bottom and let the page load
 * before trying again; `shop-shot.mjs` does that, and this predicate is the one
 * decision in it, so it is the part that gets a test.
 *
 * Reachable means within `docHeight - viewportHeight`, because that is where
 * scrolling stops. A target past it is not "near the bottom" — it is a screen
 * that does not exist yet.
 *
 * @param {{target: number, docHeight: number, viewportHeight: number}} input
 * @returns {boolean}
 */
export function scrollTargetIsBeyondDocument({ target, docHeight, viewportHeight }) {
  return target > Math.max(0, docHeight - viewportHeight);
}

/**
 * What stderr says about a viewport shot, so a clamp is never silent.
 *
 * A LOOK is only evidence if the reader of the PNG can tell WHICH screen it is.
 * When the page grew under us (infinite scroll) or refused to grow far enough,
 * both facts belong beside the shot — and "could not reach" has to read as a
 * finding, not a footnote, because the PNG itself looks perfectly clean.
 *
 * @param {{target: number, finalY: number, docHeight: number, grewTo: number}} input
 * @returns {{line: string, reached: boolean}}
 */
export function scrollReachReport({ target, finalY, docHeight, grewTo }) {
  const reached = finalY >= target;
  const grew = grewTo > docHeight ? ` grewTo=${grewTo}` : "";
  const line = reached
    ? `docHeight=${docHeight}${grew} mode=viewport@${target}`
    : `docHeight=${docHeight}${grew} mode=viewport@${target} ` +
      `SHOT_SCROLL_CLAMPED: asked for ${target}, the document stops at ${finalY}. ` +
      `This PNG is NOT the screen you asked for — do not file it as one.`;
  return { line, reached };
}

/**
 * The tallest document we will photograph by GROWING the viewport (CSS px).
 *
 * This is a READABILITY line, not a technical limit, and the difference is
 * measured: `/politics` at 390px is 16,333px tall and the grown capture of it
 * succeeded in 3.0s, writing a valid 780x32,666 PNG. So the ceiling is not
 * "where Chromium gives up" — it is where a whole-page shot stops being a LOOK
 * at all, because ~50 phone screens downscaled into a bounded view is the
 * unreadable 30px strip `SHOT_SCROLL` exists to avoid. 20,000px clears every
 * charted surface measured so far with room to spare; the pages above it are
 * the hub monsters (`/hub/tennis` is 44,729px), which nobody should be
 * photographing whole regardless.
 */
export const GROWN_CAPTURE_MAX_DOC_HEIGHT = 20000;

/**
 * Decide HOW to photograph a whole document: grow the viewport to fit it, or
 * fall back to Chromium's capture-beyond-viewport.
 *
 * ## Why this decision exists at all (#4664)
 *
 * `page.screenshot({ fullPage: true })` does not photograph the page you
 * measured. On Chromium it goes through CDP `captureBeyondViewport`, which
 * re-renders the document into an off-screen surface — and that re-render
 * REMOUNTS every chart, restarting Recharts' 1500ms entry animation from a
 * zero-length line. The shutter lands at t≈0, so the plot rasterises EMPTY.
 *
 * Measured on `/events/15309061` at 390px, three captures in ONE page context,
 * counting the Kalshi curve's stroke pixels (`rgb(34,197,94)`):
 *
 * | capture                                        | stroke px |
 * |------------------------------------------------|-----------|
 * | viewport, chart scrolled into view              | 2870      |
 * | `screenshot({ fullPage: true })`                | **0**     |
 * | viewport grown to the document height           | 2870      |
 *
 * The line is in the DOM, complete and correct, at the moment of all three.
 * The tell is `stroke-dasharray`, not `d`: Recharts animates a line in by
 * growing the dash, so `d` is byte-identical the whole way. Read immediately
 * after the fullPage capture the computed dasharray was `6.53776px, 570.452px`
 * — 6.5px of a 577px line drawn — against the settled design dash
 * (`8px, 4px, …`). Forcing `stroke-dasharray: none` and re-taking the SAME
 * fullPage capture put 4444 stroke px in the raster. That is the mechanism,
 * measured in both directions.
 *
 * This is why ux/1170's refutation on #4664 reads as it does: it re-read `d`
 * across a resize, found it byte-identical, and concluded the animation was not
 * the cause. `d` is the one attribute that never moves.
 *
 * ## The chart is not the only thing it gets wrong
 *
 * On the same page the fullPage capture also stamped the FIXED bottom nav
 * across real content at page y≈787 (the first viewport's bottom edge) and then
 * omitted it from the actual page bottom. The grown capture places it once, at
 * the bottom, where a reader has it. Every pixel the two captures disagree on
 * is a pixel the grown one gets right.
 *
 * ## What growing costs
 *
 * The viewport becomes as tall as the document, so `100vh`/`min-h-screen`
 * boxes grow with it and anything lazy-loading on intersection loads at once.
 * On a long page `min-h-screen` is a floor the content already clears, so it is
 * inert; the case it could move is a page only slightly taller than one screen
 * that centres its content. A short document (`docHeight <= viewportHeight`)
 * is therefore left at the viewport height — identical to today.
 *
 * @param {{docHeight?: number, viewportHeight?: number, max?: number}} input
 * @returns {{mode: 'grow', height: number}|{mode: 'beyondViewport', warning: string}}
 */
export function chooseCapture({
  docHeight,
  viewportHeight,
  max = GROWN_CAPTURE_MAX_DOC_HEIGHT,
} = {}) {
  const vh = Number.isFinite(viewportHeight) && viewportHeight > 0 ? viewportHeight : 0;
  // An unmeasurable document is the one case where we cannot say how tall to
  // grow, so it keeps the old path — loudly. Guessing a height here would
  // silently truncate the page, which is worse than the bug being fixed.
  if (!Number.isFinite(docHeight) || docHeight <= 0) {
    return {
      mode: "beyondViewport",
      warning:
        "CHART-UNSAFE document height unreadable, falling back to fullPage: any chart " +
        "in this PNG may rasterise EMPTY while its line is present in the DOM (#4664). " +
        "Confirm with SHOT_SCROLL=<offset>.",
    };
  }
  if (docHeight > max) {
    return {
      mode: "beyondViewport",
      warning:
        `CHART-UNSAFE document is ${Math.round(docHeight)}px, over the ${max}px grown-capture ` +
        "limit, so this is a fullPage shot: any chart in it may rasterise EMPTY while its " +
        "line is present in the DOM (#4664). A PNG this tall is unreadable anyway — " +
        "use SHOT_SCROLL=<offset> for a screen you can actually judge.",
    };
  }
  return { mode: "grow", height: Math.max(Math.ceil(docHeight), vh) };
}

/**
 * Where to leave the pointer before the shutter opens.
 *
 * Playwright's pointer starts at (0,0) and STAYS wherever a click left it, so
 * every shot is taken with a mouse hovering something. `SHOT_SCROLL` then
 * scrolls the page under that stationary pointer, and whatever row happens to
 * land at those coordinates renders in its `:hover` state. Measured on
 * `/tournaments/us-open` at 390px: the `Men's` tab sits at y≈166, so a
 * `SHOT_CLICKS="Men's" SHOT_SCROLL=900` shot photographs the finished match at
 * page y≈1066 — a Tiafoe/Michelsen row painted grey in three disjoint blocks
 * with a white seam through it — while its identical siblings stay white. A
 * lane reading that PNG sees a layout defect that does not exist, and the
 * inverse is worse: a hover tint can cover a real one.
 *
 * The clincher is that these are PHONE-WIDTH shots of a touch surface. No
 * reader we are photographing for has a pointer at all, so a hover state in a
 * 390px LOOK is never evidence about anything.
 *
 * So the point must be OUTSIDE the viewport, which is why this takes the
 * viewport and returns a negative offset rather than a corner: (0,0) hovers the
 * logo and (2,2) still hovers the sticky header (measured — `:hover` resolved 5
 * deep there), whereas off-viewport resolves `document.querySelectorAll(':hover')`
 * to EMPTY, not even `body`.
 *
 * @param {{width?: number, height?: number}} [viewport]
 * @returns {{x: number, y: number}} a point guaranteed outside the viewport
 */
export function pointerParkPoint({ width, height } = {}) {
  // Proportional to the viewport, so it stays outside one of any size, and
  // never a bare literal that reads as "just off the top-left of a phone".
  const w = Number.isFinite(width) && width > 0 ? width : 0;
  const h = Number.isFinite(height) && height > 0 ? height : 0;
  return { x: -Math.max(8, Math.ceil(w * 0.02)), y: -Math.max(8, Math.ceil(h * 0.02)) };
}

/**
 * Whether to park the pointer at all.
 *
 * Parking is the default because a fabricated hover is the failure that costs a
 * reader a wrong judgement. But a lane deliberately photographing a hover-only
 * affordance — a tooltip, a hover-revealed control — needs the pointer left
 * where its click put it, and removing that capability to fix the artifact
 * would just trade one blind spot for another.
 *
 * @param {string|undefined} raw the `SHOT_KEEP_POINTER` value
 * @returns {boolean}
 */
export function shouldParkPointer(raw) {
  return !(raw === "1" || raw === "true");
}

/**
 * Delete any screenshot already sitting at the output path.
 *
 * A failed run must not leave the PREVIOUS run's screenshot under this run's
 * filename — that is the same class of lie one level out, and it is how a
 * reader ends up judging a photograph of something else entirely. Best effort:
 * if it cannot be removed, the run should still proceed and fail on its own
 * terms rather than on housekeeping.
 *
 * Takes its `fs` as an injectable second argument only so the guard can prove
 * the unlink is attempted; production passes nothing and gets real `fs`.
 *
 * @param {string} out
 * @param {{existsSync: Function, unlinkSync: Function}} [fs]
 * @returns {boolean} whether a stale file was removed
 */
export function clearStaleArtifact(out, fs) {
  const io = fs || nodeFs;
  try {
    if (io.existsSync(out)) {
      io.unlinkSync(out);
      return true;
    }
  } catch {
    /* best effort — housekeeping must not decide the run */
  }
  return false;
}
