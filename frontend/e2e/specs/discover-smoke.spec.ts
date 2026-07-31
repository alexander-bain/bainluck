import { test, expect } from "../fixtures/audit";

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

/** Per-card wrapper rendered only when the feed has visible items. */
const CARD_WRAPPER = "main div.break-inside-avoid";
/** Card detail links — a second, independent signal that content is real. */
const CARD_LINK =
  'main a[href^="/event"], main a[href^="/futures"], main a[href^="/hub"], main a[href^="/topic"], main a[href^="/market"]';
/** The one named, legitimate empty state Discover ships (EndOfFeedCard). */
const NAMED_EMPTY = "You're all caught up";
/** An error state. Never a legitimate empty state. */
const ERROR_STATE = "Failed to load feed";

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
    const emptyLocator = page.getByText(NAMED_EMPTY, { exact: false }).first();
    const errorLocator = page.getByText(ERROR_STATE, { exact: false }).first();

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
    const emptyState = namedEmptyVisible ? { name: NAMED_EMPTY, visible: true } : null;

    const mainText = (await page.locator("main").first().innerText().catch(() => "")) || "";

    await journey.finish({
      journeyId: `${target.journeyId}`,
      expectedPath: target.path,
      realCardFound,
      firstCardMs,
      emptyState,
      mainRegionNonBlank: mainText.trim().length > 40,
    });

    // Redundant with the evaluator, but keeps the failure legible in the
    // Playwright report without having to open the manifest.
    expect(realCardFound || namedEmptyVisible, "a real card or a named empty state must render").toBe(true);
  });
}
