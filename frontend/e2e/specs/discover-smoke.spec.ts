import { test, expect, readContentRegionText } from "../fixtures/audit";

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
/** The loading placeholder. Never content, and explicitly asserted against. */
const SKELETON = '[data-testid="discover-skeleton"]';

const PATHS = [
  { journeyId: "discover.landing", path: "/" },
  { journeyId: "discover.route", path: "/discover" },
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

    // A still-mounted skeleton means the feed never resolved. It is neither
    // content nor a legitimate empty state, and asserting on it directly keeps
    // "we timed out waiting" distinguishable from "the deploy is genuinely
    // empty" in the manifest rather than only in a screenshot.
    const skeletonVisible = await page.locator(SKELETON).first().isVisible().catch(() => false);

    const mainText = await readContentRegionText(page);

    await journey.finish({
      journeyId: `${target.journeyId}`,
      expectedPath: target.path,
      realCardFound,
      firstCardMs,
      emptyState,
      mainRegionNonBlank: mainText.trim().length > 40 && !skeletonVisible,
    });

    // Redundant with the evaluator, but keeps the failure legible in the
    // Playwright report without having to open the manifest.
    expect(skeletonVisible, "the loading skeleton must not still be mounted").toBe(false);
    expect(realCardFound || namedEmptyVisible, "a real card or a named empty state must render").toBe(true);
  });
}
