"use strict";

const { before, describe, it } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

/**
 * #4032 — the half of the LOOK click rail that needs a real browser.
 *
 * ## What this covers that `contract/lookClickContract.contract.test.js` cannot
 *
 * #3968 extracted `shop-shot.mjs`'s decisions into `tools/shot-click-contract.mjs`
 * and guarded them with 23 browser-free tests. That was the right boundary and
 * it stopped in the right place: the `e2e-contract` job is safe to run on every
 * push precisely because it does no install, no network and no browser
 * download, and anything needing Chromium destroys the property that made a
 * home available at all.
 *
 * So four behaviours shipped verified only BY HAND, against production, twice
 * (#3932 and again #3968):
 *
 *   1. VISIBLE-FIRST SELECTION — the visible node, not the first in DOM order.
 *      Needs a layout engine; a pure function cannot have an opinion about it.
 *      Graded twice: once on whatever Playwright the machine resolves, and once
 *      on the LOCKED build CI resolves — #4032's own first red run was that
 *      divergence, and only the second reading can see it.
 *   2. EMOJI TEXT — the NFL pill reads `🏈NFL`, so `getByText('NFL', {exact})`
 *      misses. Needs real text-node matching.
 *   3. THE STEP LOOP through the browser path, actually advancing surfaces.
 *   4. OPTIONAL-CLICK MODE through that same real path.
 *
 * Plus, since it is the same vocabulary: the camera-failure exit is bound to
 * `EXIT_CAMERA` rather than a typed `1` (item 5).
 *
 * ## Why it matters more than a p3 usually does
 *
 * Standing notice 4 makes this rail the proof that every other lane's
 * rendered-surface work is done, and its failure mode is SILENT: it goes back
 * to handing out plausible screenshots of the wrong page. Every LOOK taken
 * while it is broken is unfalsifiable in the failing direction — which is to
 * say the evidence keeps arriving and stops meaning anything.
 *
 * ## Why exit codes and file side-effects, never pixels
 *
 * Nothing here reads a screenshot. Pixels drag in fonts, platform rendering and
 * a human judgement call, none of which is what regressed. What regressed was a
 * DECISION, and every decision this rail makes is observable as an exit code
 * (gotcha #124: the value is the story) or as whether a PNG exists.
 *
 * ## Why it is hermetic
 *
 * `file://` fixtures, no server, no network, no API. Aiming this at production
 * would buy the layout engine and lose everything else — the assertion would
 * depend on markup nobody promised to keep and on whatever the feed ranked that
 * morning. See `fixtures/fixture-a.html` for what each control stands in for.
 *
 * ## Where it runs, and where it must NOT
 *
 * `.github/workflows/look-rail-guard.yml`, which installs Chromium. NOT
 * `e2e-contract` — see above. Its wiring is itself guarded, browser-free, by
 * `contract/lookClickBrowserRail.contract.test.js`, because a browser guard
 * that quietly stops being invoked reads exactly like a browser guard that
 * passes.
 */

const E2E_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(E2E_ROOT, "..", "..");
const SHOP_SHOT = path.join(REPO_ROOT, "tools", "shop-shot.mjs");
const CONTRACT_MODULE = path.join(REPO_ROOT, "tools", "shot-click-contract.mjs");

const FIXTURE_A = path.join(__dirname, "fixtures", "fixture-a.html");
const FIXTURE_B = path.join(__dirname, "fixtures", "fixture-b.html");
const FIXTURE_A_URL = pathToFileURL(FIXTURE_A).href;

/**
 * The exit-code vocabulary, imported rather than retyped.
 *
 * Hard-coding 0/1/2/3 here would let a renumbering pass while every caller
 * broke — the same drift item 5 removed from `shop-shot.mjs` itself. The module
 * is ESM and this file is CJS, hence the dynamic import.
 */
let EXIT;
before(async () => {
  EXIT = await import(pathToFileURL(CONTRACT_MODULE).href);
});

/** Somewhere to write PNGs that is not the repo. */
const OUT_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "look-rail-guard-"));
let shotSeq = 0;
const nextOut = () => path.join(OUT_DIR, `shot-${++shotSeq}.png`);

/**
 * A HOME with no `~/.npm/_npx` in it, which forces `findPlaywright()` down its
 * fallback branch and onto the repo's own locked Playwright.
 *
 * This is not a tidiness measure. `findPlaywright()` prefers whatever the npx
 * cache holds, so the authoring laptop ran 1.55.1 while CI — which has no such
 * cache — ran the lockfile's 1.48.2, and the two disagreed about what
 * `.filter({ visible: true })` means. See the forced-resolution case below.
 *
 * Overriding HOME also moves Playwright's browser cache, so the real one is
 * handed back explicitly; otherwise every run under this env would fail on a
 * missing executable rather than on the thing being tested.
 */
const LOCKFILE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "look-rail-nonpx-"));
const LOCKFILE_ENV = {
  HOME: LOCKFILE_HOME,
  PLAYWRIGHT_BROWSERS_PATH:
    process.env.PLAYWRIGHT_BROWSERS_PATH ||
    (process.platform === "darwin"
      ? path.join(os.homedir(), "Library", "Caches", "ms-playwright")
      : path.join(os.homedir(), ".cache", "ms-playwright")),
};

/**
 * Run `shop-shot.mjs` exactly as `look.sh` does — as a subprocess, read by its
 * exit code.
 *
 * `cwd: E2E_ROOT` is load-bearing. `findPlaywright()` looks first in
 * `~/.npm/_npx/*` (how a laptop that has run `look.sh` already has it) and
 * otherwise falls back to `process.cwd()`, which on CI is where `npm ci` put
 * it. Both paths resolve the same locked 1.48.2.
 *
 * The viewport is pinned at phone width because fixture A hides its decoy nav
 * behind a `min-width: 900px` media query — at a desktop width the decoy is
 * visible and test 1 would be proving something else entirely.
 */
function shoot({ url = FIXTURE_A_URL, out = nextOut(), env = {} } = {}) {
  const result = spawnSync(process.execPath, [SHOP_SHOT, url, out], {
    cwd: E2E_ROOT,
    encoding: "utf8",
    // 3 minutes: the slowest case below is a 15s click timeout on top of the
    // script's own ~13s of settle waits, so this bounds a hang without ever
    // truncating a healthy run.
    timeout: 180_000,
    env: { ...process.env, SHOT_W: "390", SHOT_H: "844", ...env },
  });
  return { ...result, out };
}

describe("#4032 — the LOOK click rail, through a real browser", () => {
  /**
   * ANTI-VACUITY. Nothing in this file is skipped, so the one way it can pass
   * without proving anything is by not running — and a suite that cannot find
   * a browser should say so in those words rather than fail six times with a
   * module-resolution stack trace.
   */
  it("preflight: the script, the contract module and both fixtures exist", () => {
    for (const p of [SHOP_SHOT, CONTRACT_MODULE, FIXTURE_A, FIXTURE_B]) {
      assert.ok(fs.existsSync(p), `missing: ${path.relative(REPO_ROOT, p)}`);
    }
    assert.equal(typeof EXIT.EXIT_CAMERA, "number", "the exit vocabulary did not import");

    // A usage error exits BEFORE Chromium is launched, so this separates "the
    // script is broken" from "there is no browser on this machine" — the two
    // failures that otherwise look identical from a red suite.
    const usage = spawnSync(process.execPath, [SHOP_SHOT], { cwd: E2E_ROOT, encoding: "utf8" });
    assert.equal(usage.status, EXIT.EXIT_USAGE, "no-argument run must exit EXIT_USAGE");
    assert.match(usage.stderr, /usage: shop-shot\.mjs/);
  });

  /**
   * ITEM 1 + ITEM 3, in one run, because the cheapest proof that the click
   * landed on the RIGHT node is a second step that only the right node can
   * reach.
   *
   * Fixture A holds a hidden `Sports` (a `min-width: 900px` nav, first in DOM
   * order) above a visible `Sports` that navigates to fixture B. `LandedOnB`
   * exists only on B. So exit 0 rules out all three failures at once: clicking
   * the decoy (it goes nowhere and is not actionable), never navigating, and
   * abandoning the sequence after step 1.
   *
   * MEASURED, by deleting `.filter({ visible: true })` from `shop-shot.mjs` and
   * re-running this exact case: exit 3, `CLICKFAIL Sports :: locator.click:
   * Timeout 15000ms exceeded`, and no PNG. The guard is load-bearing rather
   * than decorative.
   */
  it("picks the first VISIBLE node, not the first in the DOM, and carries the sequence onto the next surface", () => {
    const r = shoot({ env: { SHOT_CLICKS: "Sports;LandedOnB" } });

    assert.equal(
      r.status,
      0,
      `expected a clean two-step run.\nstderr:\n${r.stderr}`
    );
    assert.match(r.stderr, /CLICKED Sports/, "step 1 must report as landed");
    assert.match(r.stderr, /CLICKED LandedOnB/, "step 2 must run on the surface step 1 opened");
    assert.ok(fs.existsSync(r.out), "a landed sequence must leave a screenshot");
  });

  /**
   * ITEM 1 AGAIN, ON THE PLAYWRIGHT CI ACTUALLY RESOLVES — the case that would
   * have caught #4032's own first red run before it was pushed.
   *
   * The case above proves visible-first on whatever `findPlaywright()` happens
   * to load, and on a laptop that is the npx cache (1.55.1 here). CI has no npx
   * cache, so it falls through to the repo's lockfile (1.48.2), and the two
   * builds do not agree:
   *
   *   1.48.2  getByText('Sports').filter({visible:true}) -> count 2, first = the HIDDEN decoy
   *   1.55.1  the same expression                        -> count 1, first = the visible link
   *
   * `filter()`'s `visible` option arrived in 1.51, and an older Playwright does
   * not reject the unknown key — it accepts the object and drops it. So the fix
   * degraded, in silence, to the bare `.first()` it was written to replace: the
   * laptop went green six for six and CI failed on this exact click with
   * `CLICKFAIL Sports :: locator.click: Timeout 15000ms exceeded`.
   *
   * A version-independent form (`locator('visible=true')`, in the engine since
   * 1.14) is the repair. This is the guard that keeps it honest, because the
   * failure it protects against is invisible from the machine writing the code.
   */
  it("visible-first survives the OLDEST Playwright this can resolve, not just the newest installed", () => {
    // ANTI-VACUITY. If either of these stops holding, the run below silently
    // grades the same build as the case above and this test proves nothing.
    assert.ok(
      !fs.existsSync(path.join(LOCKFILE_HOME, ".npm", "_npx")),
      "the forced HOME has an npx cache in it, so findPlaywright() will not reach the lockfile build"
    );
    const lock = JSON.parse(fs.readFileSync(path.join(E2E_ROOT, "package-lock.json"), "utf8"));
    const pinned = lock.packages["node_modules/playwright"].version;
    const installed = JSON.parse(
      fs.readFileSync(path.join(E2E_ROOT, "node_modules", "playwright", "package.json"), "utf8")
    ).version;
    assert.equal(
      installed,
      pinned,
      `frontend/e2e/node_modules holds Playwright ${installed} but the lockfile pins ${pinned} — run \`npm ci\` in frontend/e2e; this case is only meaningful against the pinned build`
    );

    const r = shoot({ env: { SHOT_CLICKS: "Sports;LandedOnB", ...LOCKFILE_ENV } });

    assert.equal(
      r.status,
      0,
      `the rail must pick the visible node under the LOCKED Playwright (${pinned}), not only under whatever npx cached.\nstderr:\n${r.stderr}`
    );
    assert.match(r.stderr, /CLICKED LandedOnB/, "the click must still land on the node that navigates");
  });

  /**
   * ITEM 2, failing half — and the stale-artifact rule through the real path.
   *
   * `🏈NFL` is one text node; `exact: true` means `NFL` does not match it. The
   * requirement is not that this succeed — it is that it fail LOUDLY (exit 3,
   * not a screenshot of the un-tapped page) and name the reading that failed,
   * because "no exact-text node reads NFL" and "the button is covered" are
   * different problems a bare timeout cannot tell apart.
   *
   * The pre-seeded PNG is the other half of #3932: a failed run must not leave
   * the PREVIOUS run's screenshot sitting under this run's filename. That is
   * unit-tested browser-free, but this is the path that actually ships.
   */
  it("bare text does not match an emoji-prefixed control, and says so instead of shooting", () => {
    const out = nextOut();
    fs.writeFileSync(out, "stale bytes from an earlier run");

    const r = shoot({ out, env: { SHOT_CLICKS: "NFL" } });

    assert.equal(r.status, EXIT.EXIT_CLICK_FAILED, `expected EXIT_CLICK_FAILED.\nstderr:\n${r.stderr}`);
    assert.match(r.stderr, /CLICKFAIL NFL/);
    assert.match(
      r.stderr,
      /read as exact TEXT; if you meant a CSS selector, prefix it `css=`/,
      "the hint must name the READING that failed, not just the timeout"
    );
    assert.ok(!fs.existsSync(out), "a failed run must delete the stale artifact, not leave it as a pass");
  });

  /** ITEM 2, succeeding half — `css=` is the documented way to reach it. */
  it("`css=` reaches the control that exact text cannot", () => {
    const r = shoot({ env: { SHOT_CLICKS: "css=.pill" } });

    assert.equal(r.status, 0, `expected the selector to land.\nstderr:\n${r.stderr}`);
    assert.match(r.stderr, /CLICKED css=\.pill/);
    assert.ok(fs.existsSync(r.out));
  });

  /**
   * ITEM 4. `SHOT_CLICK_OPTIONAL=1` restores the pre-#3932 best-effort tap for a
   * caller who genuinely means "tap it if it's there".
   *
   * All three halves matter together: it still WARNS (silence would be the old
   * lie), it still SHOOTS, and it exits 0. Asserting only the exit code would
   * pass for a build that had stopped warning, which is the state #3932 was.
   */
  it("optional mode warns, shoots anyway, and exits clean", () => {
    const r = shoot({
      env: { SHOT_CLICKS: "NoSuchControlAnywhere", SHOT_CLICK_OPTIONAL: "1" },
    });

    assert.equal(r.status, 0, `optional mode must not fail the run.\nstderr:\n${r.stderr}`);
    assert.match(r.stderr, /CLICKFAIL NoSuchControlAnywhere/, "a swallowed miss must still be announced");
    assert.ok(fs.existsSync(r.out), "optional mode's whole point is that it still produces the shot");
  });

  /**
   * ITEM 5. A page that cannot be loaded is a CAMERA failure, and it must stay
   * distinguishable from the other two codes — that separation is the entire
   * reason the vocabulary exists (gotcha #124).
   *
   * Asserting `!== EXIT_CLICK_FAILED` and `!== EXIT_USAGE` explicitly, not just
   * `=== EXIT_CAMERA`: `EXIT_CAMERA` is 1 today, and a renumbering that
   * collided it with another code would otherwise slip through on the equality
   * alone.
   */
  it("a page that will not load exits EXIT_CAMERA, distinct from a failed tap", () => {
    const missing = pathToFileURL(path.join(OUT_DIR, "no-such-page.html")).href;
    const r = shoot({ url: missing });

    assert.equal(r.status, EXIT.EXIT_CAMERA, `expected EXIT_CAMERA.\nstderr:\n${r.stderr}`);
    assert.notEqual(r.status, EXIT.EXIT_CLICK_FAILED, "camera failure must not read as a failed tap");
    assert.notEqual(r.status, EXIT.EXIT_USAGE, "camera failure must not read as a usage error");
    assert.match(r.stderr, /FAIL file:.*no-such-page\.html/);
    assert.ok(!fs.existsSync(r.out), "a run that never loaded the page must leave no artifact");
  });
});
