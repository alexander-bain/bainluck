// L2-214 Item 1 — Discover web request shape: one bounded initial request and
// monotonic pagination from the returned page boundary.
//
// This is the single source of truth for the request plan so the Discover page
// and its tests share the SAME production logic (no cloned helper). The rules
// enforced here mirror backend/scripts/evals/feed_speed_fixtures.json:
//   • the initial request is bounded to FEED_PAGE_LIMIT (<= initial_page_limit_max)
//   • pagination offsets are strictly increasing and never re-request offset 0
//   • rendered items are de-duplicated by their stable id across pages

/** Bounded first-paint page size. Kept small so the first cards render fast and
 *  the remainder streams in on scroll, instead of pulling the whole feed up front. */
export const FEED_PAGE_LIMIT = 20;

export interface FeedRequestPlan {
  limit: number;
  offset: number;
}

/** The single initial (offset-zero) request. Exactly one owner should issue this. */
export function initialFeedRequest(): FeedRequestPlan {
  return { limit: FEED_PAGE_LIMIT, offset: 0 };
}

/**
 * The next page request, advancing monotonically from the number of items already
 * loaded. Never re-requests offset 0 as pagination — the boundary is exactly the
 * count already held, so offsets march 0 → 20 → 40 … with no overlap or regression.
 */
export function nextFeedRequest(loadedCount: number): FeedRequestPlan {
  // Offset is exactly the number of items already held — the returned page
  // boundary — so pages march 0 → 20 → 40 … with no overlap. Floored at 1 so a
  // paginated request can never masquerade as a second offset-zero fetch.
  const offset = Math.max(1, loadedCount);
  return { limit: FEED_PAGE_LIMIT, offset };
}

/**
 * De-duplicate items by stable id, preserving first-seen order. Defense in depth
 * so a paging/coalesce hiccup can never render the same card twice.
 */
export function dedupeById<T>(items: T[], getId: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const id = getId(item);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}
