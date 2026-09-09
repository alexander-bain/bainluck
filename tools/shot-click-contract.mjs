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
