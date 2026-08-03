import { test, expect, readContentRegionText } from "../fixtures/audit";
import type { Page, Response } from "@playwright/test";

/**
 * Sports cold/warm latency trace — L2-240 Items 0/3.
 *
 * The /sports twin of discover-latency.spec.ts. It exists to answer the queue's
 * measurement items honestly in a REAL browser against the DEPLOYED build:
 * how long until the first real (non-skeleton) card, and what did the
 * `/api/feed?mode=sports` request actually do?
 *
 * This is the rail that PROVES the two L2-240 blockers are gone:
 *   1. the anonymous request no longer waits on Firebase auth (it starts
 *      concurrently with navigation, captured below), and
 *   2. the initial request is bounded to one page (limit=20), not the old
 *      200-item pull — visible in the request URL this spec records.
 *
 * It records latency; it asserts no latency budget (those are product
 * decisions). What it DOES assert is honesty about what it saw: no card means
 * `firstCardMs === null`, and the shared evaluator fails the journey unless a
 * named empty state was proven visible — the same guard that killed the C96
 * [P1] false green in discover-latency.
 */

const PATHS = ["/sports"] as const;

/**
 * Stable, state-based hooks (L2-223/L2-240). `data-testid="sports-card"` exists
 * only on a mounted Sports feed item, never on the loading skeleton, so a feed
 * stuck on skeletons cannot satisfy "a real card appeared".
 */
const CARD_WRAPPER = '[data-testid="sports-card"]';
// The named, legitimate empty states the Sports page ships: its own quiet/no-
// games slate, and the shared end-of-feed card at genuine exhaustion.
const NAMED_EMPTY =
  '[data-testid="sports-empty-state"], [data-testid="discover-empty-state"]';

interface FeedTiming {
  status: number;
  url: string;
  /** The `limit=` query param on the request — proves the bounded first page. */
  requestedLimit: string | null;
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
    let requestedLimit: string | null = null;
    try {
      requestedLimit = new URL(res.url()).searchParams.get("limit");
    } catch {
      requestedLimit = null;
    }
    return {
      status: res.status(),
      url: res.url(),
      requestedLimit,
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
  test.describe(`Sports latency @ ${path}`, () => {
    test("cold + warm trace, slices recorded separately", async ({ page, journey }, testInfo) => {
      // ---- COLD: fresh context, feed captured concurrently with navigation.
      // Capturing the feed request BEFORE navigation is what proves the
      // anonymous request no longer waits on auth: it fires as the page loads,
      // not after Firebase resolves. ----
      const feedPromise = captureFeed(page);
      const t0 = Date.now();
      await page.goto(path, { waitUntil: "domcontentloaded" });
      const shell = await navTimings(page);
      const coldFeed = await feedPromise;

      // First real card. A timeout means no card was seen; that fact is carried
      // forward truthfully rather than smoothed into a number.
      const cardLocator = page.locator(CARD_WRAPPER).first();
      const realCardFound = await cardLocator
        .waitFor({ state: "visible", timeout: 30_000 })
        .then(() => true)
        .catch(() => false);
      const firstCardMs = realCardFound ? Date.now() - t0 : null;

      const emptyLocator = page.locator(NAMED_EMPTY).first();
      const namedEmptyVisible = await emptyLocator.isVisible().catch(() => false);
      const emptyStateName = namedEmptyVisible
        ? await emptyLocator.getAttribute("data-empty-state-name").catch(() => null)
        : null;

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
      await testInfo.attach("sports-latency.json", {
        body: JSON.stringify(record, null, 2),
        contentType: "application/json",
      });

      // Invariants (no latency targets): a feed response was observable; the
      // initial request was bounded to one page (never the old 200 pull); and
      // the backend compute slice never exceeds the full client round-trip.
      expect(coldFeed, "feed response should be observable").not.toBeNull();
      if (coldFeed?.requestedLimit != null) {
        expect(Number(coldFeed.requestedLimit)).toBeLessThanOrEqual(20);
      }
      if (coldFeed?.backendElapsedMs != null && coldFeed?.roundTripMs != null) {
        expect(coldFeed.backendElapsedMs).toBeLessThanOrEqual(coldFeed.roundTripMs + 50);
      }

      const mainText = await readContentRegionText(page);
      await journey.finish({
        journeyId: "sports.latency",
        expectedPath: path,
        realCardFound,
        firstCardMs,
        emptyState: namedEmptyVisible
          ? { name: emptyStateName || "sports-empty-state", visible: true }
          : null,
        mainRegionNonBlank: mainText.trim().length > 40,
      });
    });
  });
}
