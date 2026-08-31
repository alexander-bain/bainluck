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
 * Whether the auto-pager should fetch the next page RIGHT NOW.
 *
 * LAT-P171. This lived inline in `app/discover/page.tsx` as
 * `visibleCount >= processedItems.length - 5 && hasMore && !loadingMore`, which
 * is true on the very first commit: `visibleCount` starts at `FEED_PAGE_LIMIT`
 * and `renderedCount` is 0, so the test reads `20 >= -5`. A cold load therefore
 * issued `/api/feed?limit=20&offset=1` — `nextFeedRequest` floors the offset at
 * 1 — concurrently with the `offset=0` request that gates the first card. That
 * is a second full feed build, at an offset the backend prewarm does not cover,
 * returning a page that overlaps page one by 19 of 20 items. The 2026-08-31
 * browser rail observed it as `net::ERR_ABORTED` on that exact URL.
 *
 * 🔴 `renderedCount > 0` IS THE PRECONDITION, NOT A THRESHOLD TWEAK. "The reader
 * is running out of rendered items" cannot be true before any item has rendered.
 * It does not risk stranding an exhausted feed: an empty page one closes
 * `has_more` through the availability decision, so pagination is already over.
 *
 * Extracted here rather than left in the component because this harness renders
 * with `renderToStaticMarkup`, which never runs effects — inline, the predicate
 * has no test path at all.
 */
export function shouldLoadNextPage(state: {
  /** Cards the reader can currently see. */
  visibleCount: number;
  /** Cards already loaded and rendered across every page so far. */
  renderedCount: number;
  /** The backend has not yet said the feed is exhausted. */
  hasMore: boolean;
  /** A pagination request is already in flight. */
  loadingMore: boolean;
}): boolean {
  const { visibleCount, renderedCount, hasMore, loadingMore } = state;
  if (renderedCount === 0) return false;
  if (!hasMore || loadingMore) return false;
  return visibleCount >= renderedCount - PAGINATION_LOOKAHEAD;
}

/** How many unseen cards may remain before the next page is fetched. */
export const PAGINATION_LOOKAHEAD = 5;

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
