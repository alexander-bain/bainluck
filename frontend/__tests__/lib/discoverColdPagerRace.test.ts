// LAT-P171: the Discover auto-pager must not fire before page one has landed.
//
// ## The defect
//
// The effect in `app/discover/page.tsx` read:
//     visibleCount >= processedItems.length - 5 && hasMore && !loadingMore
// On the first commit `visibleCount` is `FEED_PAGE_LIMIT` (20) and
// `processedItems` is empty, so this is `20 >= -5` — TRUE. Page two was
// requested on mount. `nextFeedRequest(0)` floors the offset at 1, so a cold
// load issued `/api/feed?limit=20&offset=1` CONCURRENTLY with the `offset=0`
// request that gates the first card: a second full feed build, at an offset the
// backend prewarm does not cover, whose payload then overlaps page one by 19 of
// its 20 items.
//
// Observed in production by the browser-audit `latency` pack on 2026-08-31
// (run 33425693615) as `network.no_unexpected_failures` failing with
// `net::ERR_ABORTED` on exactly that URL.
//
// ## Why the predicate is tested here and not through a render
//
// `jest.config.js` sets `testEnvironment: "node"` and component tests SSR via
// `renderToStaticMarkup`, which never runs effects — an inline predicate inside
// a `useEffect` has no assertable path at all. So the decision was extracted to
// `lib/discover/feedPaging.shouldLoadNextPage` and is tested directly, with a
// source-shape guard below proving the page actually calls it. A lib test alone
// would stay green if the component quietly went back to its own inline
// arithmetic.

import { readFileSync } from "fs";
import { join } from "path";
import {
  shouldLoadNextPage,
  nextFeedRequest,
  FEED_PAGE_LIMIT,
  PAGINATION_LOOKAHEAD,
} from "@/lib/discover/feedPaging";

const PAGE_SOURCE = readFileSync(
  join(__dirname, "..", "..", "app", "discover", "page.tsx"),
  "utf8"
);

describe("LAT-P171 — the cold-load pager race", () => {
  it("does NOT paginate on the first commit, before any card has rendered", () => {
    // The exact mount state: visibleCount seeded to the page size, nothing
    // loaded yet, hasMore optimistically true, no request in flight.
    expect(
      shouldLoadNextPage({
        visibleCount: FEED_PAGE_LIMIT,
        renderedCount: 0,
        hasMore: true,
        loadingMore: false,
      })
    ).toBe(false);
  });

  it("fails on the pre-fix predicate — the regression is caught, not assumed", () => {
    // This is what the old inline expression computed for the same state. If a
    // future edit restores it, the assertion above flips; this documents that
    // the two disagree rather than leaving it to a reader's arithmetic.
    const mountState = { visibleCount: FEED_PAGE_LIMIT, renderedCount: 0 };
    const preFix =
      mountState.visibleCount >= mountState.renderedCount - PAGINATION_LOOKAHEAD;
    expect(preFix).toBe(true);
    expect(
      shouldLoadNextPage({ ...mountState, hasMore: true, loadingMore: false })
    ).toBe(false);
  });

  it("the request that WOULD have been issued is a duplicate of page one", () => {
    // Why the race is not merely wasteful: offset 1 re-fetches 19 of page one's
    // 20 items, so the second build buys exactly one new card.
    const initial = { limit: FEED_PAGE_LIMIT, offset: 0 };
    const racing = nextFeedRequest(0);
    expect(racing.offset).toBe(1);
    const overlap = initial.offset + initial.limit - racing.offset;
    expect(overlap).toBe(19);
  });

  it("still paginates once cards are rendered and the reader nears the end", () => {
    expect(
      shouldLoadNextPage({
        visibleCount: 20,
        renderedCount: 20,
        hasMore: true,
        loadingMore: false,
      })
    ).toBe(true);
  });

  it("does not paginate while the reader has plenty of unseen cards left", () => {
    expect(
      shouldLoadNextPage({
        visibleCount: 20,
        renderedCount: 60,
        hasMore: true,
        loadingMore: false,
      })
    ).toBe(false);
  });

  it("respects the existing in-flight and exhausted terminals", () => {
    const near = { visibleCount: 20, renderedCount: 20 };
    expect(shouldLoadNextPage({ ...near, hasMore: false, loadingMore: false })).toBe(false);
    expect(shouldLoadNextPage({ ...near, hasMore: true, loadingMore: true })).toBe(false);
  });

  it("an exhausted-on-page-one feed is not stranded by the new precondition", () => {
    // The worry the precondition invites: if page one comes back empty, does the
    // gate stop the feed from ever advancing? It does not matter — an empty page
    // one closes `has_more` through the availability decision, so pagination is
    // already over on the other two terminals.
    expect(
      shouldLoadNextPage({
        visibleCount: FEED_PAGE_LIMIT,
        renderedCount: 0,
        hasMore: false,
        loadingMore: false,
      })
    ).toBe(false);
  });

  it("the Discover page uses the shared predicate, not its own arithmetic", () => {
    // Required by the lib/source two-layer pattern: without this, the component
    // can drop the thing the tests above prove and nothing goes red.
    expect(PAGE_SOURCE).toContain("shouldLoadNextPage");
    // And it must not have quietly kept an inline copy of the old comparison.
    expect(PAGE_SOURCE).not.toMatch(/visibleCount\s*>=\s*processedItems\.length\s*-\s*5/);
  });
});
