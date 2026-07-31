import { test, expect } from "../fixtures/audit";
import type { Page, Response } from "@playwright/test";

/**
 * Discover cold/warm latency trace — originally L2-189 Item 2, brought under
 * the L2-221 shared evidence collector.
 *
 * Separates, per navigation, the three slices the L2-188 curl audit could not
 * take apart in the browser:
 *   1. shell        — server HTML / DOMContentLoaded (pre-hydration structure)
 *   2. feed         — the `/api/feed` round-trip, plus the backend-attested
 *                     `X-Feed-Elapsed-Ms` compute time and `X-Feed-Cache`
 *                     status (readable because CORS exposes them)
 *   3. first card   — time to the first real (non-skeleton) card
 *
 * It records latency; it asserts no latency budget (those are product
 * decisions). What it now DOES assert is honesty about what it saw.
 *
 * ## The false green this file used to carry (C96 [P1])
 *
 * The old version wrapped the first-card wait in `.catch(() => {})` with a
 * comment claiming the result would be recorded as null — then recorded
 * `Date.now() - t0` unconditionally. A blank, empty or broken Discover render
 * therefore produced a plausible `firstCardMs` and PASSED, because only the
 * feed response was asserted. That is the same false-green shape the dead
 * provider's rail had, and it is why this spec was never closure evidence.
 *
 * Now: no card means `firstCardMs === null`, and the shared evaluator fails
 * the journey unless a named empty state was proven visible.
 */

const PATHS = ["/", "/discover"] as const;

/** Per-card wrapper rendered only when the feed has visible items. */
const CARD_WRAPPER = "main div.break-inside-avoid";
const NAMED_EMPTY = "You're all caught up";

interface FeedTiming {
  status: number;
  cacheStatus: string | null;
  backendElapsedMs: number | null;
  /** ms from request start to response end, per Playwright request timing. */
  roundTripMs: number | null;
}

async function captureFeed(page: Page): Promise<FeedTiming | null> {
  try {
    const res: Response = await page.waitForResponse(
      (r) => r.url().includes("/api/feed") && r.request().method() === "GET",
      { timeout: 30_000 }
    );
    const headers = res.headers();
    const timing = res.request().timing();
    const roundTripMs =
      timing && timing.responseEnd >= 0 && timing.requestStart >= 0
        ? Math.round(timing.responseEnd - timing.requestStart)
        : null;
    const elapsedRaw = headers["x-feed-elapsed-ms"];
    return {
      status: res.status(),
      cacheStatus: headers["x-feed-cache"] ?? null,
      backendElapsedMs: elapsedRaw != null ? Number(elapsedRaw) : null,
      roundTripMs,
    };
  } catch {
    return null;
  }
}

function navTimings(page: Page) {
  return page.evaluate(() => {
    const nav = performance.getEntriesByType(
      "navigation"
    )[0] as PerformanceNavigationTiming | undefined;
    if (!nav) return null;
    return {
      ttfbMs: Math.round(nav.responseStart),
      domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd),
      loadMs: Math.round(nav.loadEventEnd),
    };
  });
}

for (const path of PATHS) {
  test.describe(`Discover latency @ ${path}`, () => {
    test("cold + warm trace, slices recorded separately", async ({ page, journey }, testInfo) => {
      // ---- COLD: fresh context, feed captured concurrently with navigation ----
      const feedPromise = captureFeed(page);
      const t0 = Date.now();
      await page.goto(path, { waitUntil: "domcontentloaded" });
      const shell = await navTimings(page);
      const coldFeed = await feedPromise;

      // First real card. THE FIX: a timeout means no card was seen, and that
      // fact is carried forward truthfully rather than smoothed into a number.
      const cardLocator = page.locator(CARD_WRAPPER).first();
      const realCardFound = await cardLocator
        .waitFor({ state: "visible", timeout: 30_000 })
        .then(() => true)
        .catch(() => false);
      const firstCardMs = realCardFound ? Date.now() - t0 : null;

      const namedEmptyVisible = await page
        .getByText(NAMED_EMPTY, { exact: false })
        .first()
        .isVisible()
        .catch(() => false);

      // ---- WARM: reload; server shell + edge caches are hot ----
      const warmFeedPromise = captureFeed(page);
      await page.reload({ waitUntil: "domcontentloaded" });
      const warmFeed = await warmFeedPromise;

      const record = {
        path,
        project: testInfo.project.name,
        viewport: page.viewportSize(),
        shell,
        cold: { feed: coldFeed, firstCardMs, realCardFound },
        warm: { feed: warmFeed },
      };
      await testInfo.attach("discover-latency.json", {
        body: JSON.stringify(record, null, 2),
        contentType: "application/json",
      });

      // Invariants (no latency targets): a feed response was observable, and
      // the backend compute slice never exceeds the full client round-trip.
      expect(coldFeed, "feed response should be observable").not.toBeNull();
      if (coldFeed?.backendElapsedMs != null && coldFeed?.roundTripMs != null) {
        expect(coldFeed.backendElapsedMs).toBeLessThanOrEqual(coldFeed.roundTripMs + 50);
      }

      const mainText = (await page.locator("main").first().innerText().catch(() => "")) || "";
      await journey.finish({
        journeyId: `discover.latency${path === "/" ? ".landing" : ".route"}`,
        expectedPath: path,
        realCardFound,
        firstCardMs,
        emptyState: namedEmptyVisible ? { name: NAMED_EMPTY, visible: true } : null,
        mainRegionNonBlank: mainText.trim().length > 40,
      });
    });
  });
}
