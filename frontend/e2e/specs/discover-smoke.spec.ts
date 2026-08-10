import { test, expect, measureMainRegion } from "../fixtures/audit";
import { classifyMainRegion } from "../helpers/contentState";

/**
 * L2-221 Item 1/2 — the anonymous Discover deploy smoke.
 *
 * This is the journey the queue asks the manual workflow to run at desktop and
 * mobile. It exists to answer exactly one question honestly: **did the
 * deployed frontend render something real?**
 *
 * The contract, and the reason the old trace could not be trusted:
 *
 *   - A real (non-skeleton) card, OR a NAMED empty state that was actually
 *     seen on screen. "The page was blank" satisfies neither.
 *   - "Failed to load feed" is an ERROR state, deliberately NOT accepted as a
 *     legitimate empty state — that distinction is the whole point.
 *   - The verdict is computed by the shared evaluator in `helpers/journey.js`,
 *     the same function the contract fixtures drive, so this spec cannot grade
 *     itself more leniently than the fixtures prove.
 */

/**
 * Stable, state-based hooks (L2-223). These replaced two brittle selectors:
 *
 *   - `main div.break-inside-avoid` for a card. That is a Tailwind LAYOUT
 *     class, and `DiscoverSkeletonGrid` carries it too — so a Discover stuck
 *     on skeletons matched, `realCardFound` went true, a first-card latency
 *     was recorded, and the run reported GREEN. A live false green of exactly
 *     the C96 [P1] shape, reached through the selector instead of a `.catch()`.
 *   - `getByText("You're all caught up")` for the empty state. Copy is edited
 *     by anyone at any time; a wording change would quietly convert a proven
 *     empty state into an unproven blank page.
 *
 * `data-testid` is rendered only on a mounted feed item and on the real empty
 * state, so neither substitution is possible.
 */
const CARD_WRAPPER = '[data-testid="discover-card"]';
/** Card detail links — a second, independent signal that content is real. */
const CARD_LINK =
  'main a[href^="/event"], main a[href^="/futures"], main a[href^="/hub"], main a[href^="/topic"], main a[href^="/market"]';
/** The named, legitimate empty state Discover ships (EndOfFeedCard). */
const NAMED_EMPTY = '[data-testid="discover-empty-state"]';
/**
 * Error states. Never legitimate empty states.
 *
 * L2-238 added the second one: the backend types a no-data feed response
 * `cache.status = "unavailable"`, and Discover now renders its retry state
 * instead of the end-of-feed card. Racing it here is what keeps that outcome a
 * FAST, named red instead of a 45s timeout that reports only "nothing appeared"
 * — the rail must be able to tell "the deploy served an unavailable feed" from
 * "the page was blank".
 */
const ERROR_STATE =
  '[data-testid="discover-feed-error"], [data-testid="discover-feed-unavailable"]';
/**
 * The loading placeholder. Never content — measured, and ranked below real
 * rendered text by `helpers/contentState.js`. A page that is only skeleton
 * still fails; a skeleton left standing beside a rendered feed does not.
 */
const SKELETON = '[data-testid="discover-skeleton"]';

/**
 * #1525 — Next cancels its in-flight RSC prefetch of a card's detail route when
 * this spec tears down. First-party, orthogonal to everything this journey
 * grades, and a deploy signal it is not: the prefetch is cancelled by the
 * browser closing, not by anything the deploy did.
 *
 * DECLARED, never filtered, per #1525. The evaluator excuses it only if it is
 * genuinely an abort and not a feed request, so Shape A stays graded.
 *
 * MEASURED BEFORE DECLARING (INT-034, 2026-08-10), and the measurement is the
 * reason this one is `intermittent` where event-page's is strict — all four at
 * the same frontend SHA `f6a40849`, pack `deploy-smoke`, against production:
 *
 *   | run        | discover.route [desktop] | [mobile] | discover.landing |
 *   |------------|--------------------------|----------|------------------|
 *   | 31428469455| 1 abort                  | 0        | 0 both viewports |
 *   | 31431570162| 1 abort                  | 0        | 0 both viewports |
 *   | 31431775245| 0 aborts (run PASSED)    | 0        | 0 both viewports |
 *
 * So: desktop `/discover` only, and 2 of 3 rather than 3 of 3. A strict
 * declaration would have turned the 1-in-3 clean run RED on
 * `network.declared_allowances_fired` — trading a 2-in-3 false red for a 1-in-3
 * false red, which is not a fix. Hence the measured-intermittent form.
 *
 * It was scoped to `discover.route` for the same reason: `/` and mobile measured
 * ZERO across all three runs, so declaring there would have been an allowance
 * with no phenomenon behind it.
 *
 * UX-P049 (2026-08-10) — THAT PREMISE IS NOW FALSIFIED, by the run dispatched to
 * verify this very fix:
 *
 *   | run        | sha      | where it fired                                  |
 *   |------------|----------|-------------------------------------------------|
 *   | 31439829728| 705a5dd1 | **discover.landing [mobile]** — 1 abort, RED     |
 *
 *   ✗ network.no_unexpected_failures: 1 failed request(s):
 *     .../event/golf/fedex-st-jude-championship?_rsc=... net::ERR_ABORTED
 *
 * `/` IS the Discover page, so a prefetch it never cancels was always the odd
 * claim; three runs that happened not to see a RACY event are weak evidence of
 * absence, which is the trap gotcha #53 names. The phenomenon is the same one,
 * on the same card class, cancelled the same way.
 *
 * DECLARING IT ON BOTH IS SAFE BY CONSTRUCTION, which is why one observation is
 * enough here and would not be for a strict allowance: an `intermittent`
 * declaration is EXEMPT from run-level expiry, so declaring it where it rarely
 * fires cannot manufacture a red. The cost of NOT declaring it is a daily
 * scheduled pack that reds on a non-defect — the crying-wolf state #1648 exists
 * to end, and one that blocks other lanes' evidence runs too.
 *
 * Shape A is untouched: `abortAllowanceMatches` refuses any feed request before
 * it consults the token, so an aborted `/api/feed` still fails on both journeys.
 *
 * RETIRE THIS when Next stops aborting the prefetch, or when a measurement
 * shows it fires on every run — at which point it should become a bare string
 * and be held to the strict staleness rule.
 */
const RSC_PREFETCH_ABORT = {
  match: "_rsc=",
  issue: 1525,
  intermittent: true,
} as const;

const PATHS = [
  { journeyId: "discover.landing", path: "/", allowRscAbort: true },
  { journeyId: "discover.route", path: "/discover", allowRscAbort: true },
] as const;

for (const target of PATHS) {
  test(`anonymous discover smoke @ ${target.path}`, async ({ page, journey }) => {
    const startedAt = Date.now();

    await page.goto(target.path, { waitUntil: "domcontentloaded" });

    // Wait for EITHER outcome — a real card or a terminal state. Racing them
    // means a legitimately-empty deploy resolves fast instead of burning the
    // full timeout, while a blank page still exhausts it and fails.
    const cardLocator = page.locator(CARD_WRAPPER).first();
    const emptyLocator = page.locator(NAMED_EMPTY).first();
    const errorLocator = page.locator(ERROR_STATE).first();

    await Promise.race([
      cardLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
      emptyLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
      errorLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    ]);

    const realCardFound =
      (await cardLocator.isVisible().catch(() => false)) ||
      (await page.locator(CARD_LINK).first().isVisible().catch(() => false));

    // A duration is captured ONLY when a card was actually seen. The evaluator
    // independently fails any journey that carries a duration without a card,
    // so this cannot silently drift back into the old false green.
    const firstCardMs = realCardFound ? Date.now() - startedAt : null;

    const namedEmptyVisible = await emptyLocator.isVisible().catch(() => false);
    // The state NAME comes from the component's own data attribute, not from
    // its rendered copy — the evaluator only believes an empty state it can
    // name, and a name scraped from editable prose is not a name.
    const emptyStateName = namedEmptyVisible
      ? await emptyLocator.getAttribute("data-empty-state-name").catch(() => null)
      : null;
    const emptyState = namedEmptyVisible
      ? { name: emptyStateName || "discover-empty-state", visible: true }
      : null;

    // What the main region actually rendered, as MEASUREMENTS — the verdict is
    // the shared classifier's (L2-239).
    //
    // The clause this replaces was `mainText.trim().length > 40 &&
    // !skeletonVisible`, and the second half made this check unfalsifiable on
    // `/discover`. That route has a segment-level `loading.tsx`, so its document
    // carries a SECOND `discover-skeleton` marker that `/` — the same component,
    // via a bare re-export — has no equivalent for. `.first().isVisible()`
    // answered for whichever marker came first, so the assertion was red on
    // every run regardless of the feed (30830689689, 30830999441: `/discover`
    // RED at both viewports, `/` green, terminal screenshot a populated
    // 30,165px feed). A permanently-red assertion is an unread one.
    //
    // Skeletons are still graded, just ranked: real text outside every skeleton
    // outranks a leftover shell, and a page that is ONLY skeleton stays red.
    const mainRegion = await measureMainRegion(page, SKELETON);

    await journey.finish({
      journeyId: `${target.journeyId}`,
      expectedPath: target.path,
      realCardFound,
      firstCardMs,
      emptyState,
      mainRegion,
      allowedNavigationAborts: target.allowRscAbort ? [RSC_PREFETCH_ABORT] : [],
    });

    // Redundant with the evaluator, but keeps the failure legible in the
    // Playwright report without having to open the manifest. Same classifier,
    // so this cannot grade more leniently than the manifest does.
    const region = classifyMainRegion(mainRegion);
    expect(
      region.nonBlank,
      `the main region must render content, not just a loading shell — ${region.state}: ${region.detail}`
    ).toBe(true);
    expect(realCardFound || namedEmptyVisible, "a real card or a named empty state must render").toBe(true);
  });
}
