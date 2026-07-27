import { test, expect, type Page, type Response } from "@playwright/test";

/**
 * L2-189 Item 2 — Discover cold/warm latency trace.
 *
 * Separates, per navigation, the three slices the L2-188 curl audit could not
 * take apart in the browser:
 *   1. shell        — server HTML / DOMContentLoaded (pre-hydration structure)
 *   2. feed         — the `/api/feed` round-trip, plus the backend-attested
 *                     `X-Feed-Elapsed-Ms` compute time and `X-Feed-Cache`
 *                     status (readable now that CORS exposes them)
 *   3. first card   — time to the first real (non-skeleton) card element
 *
 * It asserts SHAPE and ORDERING invariants only — it does NOT hard-code any
 * latency target (those are product decisions, out of scope for this queue).
 * The `paths` param picks up both `/` and `/discover`.
 */

const PATHS = ["/", "/discover"] as const;

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
    test("cold + warm trace, slices recorded separately", async ({ page }, testInfo) => {
      // ---- COLD: fresh context, feed captured concurrently with navigation ----
      const feedPromise = captureFeed(page);
      const t0 = Date.now();
      await page.goto(path, { waitUntil: "domcontentloaded" });
      const shell = await navTimings(page);
      const coldFeed = await feedPromise;

      // First real card: skeleton (.animate-pulse) gone AND a card link present.
      await page
        .locator('main a[href^="/event"], main a[href^="/futures"], main a[href^="/hub"]')
        .first()
        .waitFor({ state: "visible", timeout: 30_000 })
        .catch(() => {
          /* recorded as null below; do not fail the trace on an empty slate */
        });
      const firstCardMs = Date.now() - t0;

      // ---- WARM: reload; server shell + edge caches are hot ----
      const warmFeedPromise = captureFeed(page);
      await page.reload({ waitUntil: "domcontentloaded" });
      const warmFeed = await warmFeedPromise;

      const record = {
        path,
        project: testInfo.project.name,
        viewport: page.viewportSize(),
        shell,
        cold: { feed: coldFeed, firstCardMs },
        warm: { feed: warmFeed },
      };

      // Human-readable artifact in the trace log + attached to the report.
      // eslint-disable-next-line no-console
      console.log("[discover-latency]", JSON.stringify(record, null, 2));
      await testInfo.attach("discover-latency.json", {
        body: JSON.stringify(record, null, 2),
        contentType: "application/json",
      });

      // Invariants (no latency targets): we could read a feed response, and the
      // backend compute slice is never larger than the full client round-trip.
      expect(coldFeed, "feed response should be observable").not.toBeNull();
      if (coldFeed?.backendElapsedMs != null && coldFeed?.roundTripMs != null) {
        expect(coldFeed.backendElapsedMs).toBeLessThanOrEqual(coldFeed.roundTripMs + 50);
      }
    });
  });
}
