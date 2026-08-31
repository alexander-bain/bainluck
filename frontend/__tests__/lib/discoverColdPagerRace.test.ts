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

// LAT-P172 addendum — the SAME defect one commit later.
//
// `renderedCount > 0` closed the mount case and left the FIRST-PAINT case open.
// `visibleCount` is seeded to `PAGE_SIZE`, which is the same 20 the first page
// returns, so the instant page one landed the comparison read `20 >= 20 - 5` —
// true — and Discover fetched page two before the reader had scrolled.
//
// Fable's browser measurement of 2026-08-31 caught all three on the wire:
//   #1  849 ms → 1,649 ms   the offset=0 request that gates the first card
//   #2  849 ms → 3,361 ms   LAT-P171's mount-time offset=1 race
//   #3  1,727 ms → 4,425 ms  THIS one — 78 ms after #1 returned, i.e. one commit
// Content was not complete until 4,425 ms. Two of the three were uninvited.
//
// The precondition is `visibleCount > initialVisibleCount`: the window has been
// ADVANCED, which only the sentinel observer does. Which is why the sentinel
// must not be observed against the loading skeleton — see the render guard at
// the bottom of this file. The two halves are one fix; either alone leaks.

// The mount seed. `app/discover/page.tsx` declares `const PAGE_SIZE = 20` and
// seeds `useState(PAGE_SIZE)`; the source guard at the bottom pins that this
// constant is what the page actually passes.
const INITIAL_VISIBLE = FEED_PAGE_LIMIT;

/** The reader has not touched the window: every cold load starts here. */
const untouched = { initialVisibleCount: INITIAL_VISIBLE, hasMore: true, loadingMore: false };
/** The sentinel has come into view once and revealed the next window. */
const advanced = { visibleCount: 40, initialVisibleCount: INITIAL_VISIBLE, hasMore: true, loadingMore: false };
/** A full page of 20 came back from the API, whatever survived filtering. */
const landed = { loadedCount: 20 };
/** Nothing has come back yet: the cold mount, and the ONLY "page one has not
 *  landed" state (CERT-603). */
const nothingLanded = { loadedCount: 0 };

describe("LAT-P171 — the cold-load pager race", () => {
  it("does NOT paginate on the first commit, before any card has rendered", () => {
    // The exact mount state: visibleCount seeded to the page size, nothing
    // loaded yet, hasMore optimistically true, no request in flight.
    expect(
      shouldLoadNextPage({ ...untouched, ...nothingLanded, visibleCount: INITIAL_VISIBLE, renderedCount: 0 })
    ).toBe(false);
  });

  it("fails on the pre-fix predicate — the regression is caught, not assumed", () => {
    // This is what the old inline expression computed for the same state. If a
    // future edit restores it, the assertion above flips; this documents that
    // the two disagree rather than leaving it to a reader's arithmetic.
    const mountState = { visibleCount: INITIAL_VISIBLE, renderedCount: 0 };
    const preFix =
      mountState.visibleCount >= mountState.renderedCount - PAGINATION_LOOKAHEAD;
    expect(preFix).toBe(true);
    expect(shouldLoadNextPage({ ...untouched, ...nothingLanded, ...mountState })).toBe(false);
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

  it("does not paginate while the reader has plenty of unseen cards left", () => {
    expect(shouldLoadNextPage({ ...advanced, loadedCount: 60, renderedCount: 60 })).toBe(false);
  });

  it("respects the existing in-flight and exhausted terminals", () => {
    const near = { visibleCount: 40, loadedCount: 40, renderedCount: 40, initialVisibleCount: INITIAL_VISIBLE };
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
        visibleCount: INITIAL_VISIBLE,
        loadedCount: 0,
        renderedCount: 0,
        initialVisibleCount: INITIAL_VISIBLE,
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

describe("LAT-P172 — the second uninvited feed build, at first paint", () => {
  it("🔴 does NOT paginate the instant page one lands — this is the whole ship", () => {
    // The exact state at first paint: 20 cards arrived, the window still holds
    // the 20 it was seeded with, the reader has not scrolled.
    expect(
      shouldLoadNextPage({ ...untouched, ...landed, visibleCount: INITIAL_VISIBLE, renderedCount: 20 })
    ).toBe(false);
  });

  it("REVERSES an assertion LAT-P171 wrote, and the disagreement is the point", () => {
    // LAT-P171's file asserted this same state was `true`, under the name "still
    // paginates once cards are rendered and the reader nears the end". It is not
    // the reader nearing the end. `visibleCount === renderedCount` is the
    // DEFINITION of first paint — the window was seeded to exactly the page
    // size. Reading it as "nearing the end" is what put a second full feed build
    // on the cold path. Kept as an explicit reversal so the next reader does not
    // restore the old expectation thinking they are fixing a typo.
    const firstPaint = { visibleCount: INITIAL_VISIBLE, renderedCount: 20 };
    const preFix = firstPaint.visibleCount >= firstPaint.renderedCount - PAGINATION_LOOKAHEAD;
    expect(preFix).toBe(true); // what LAT-P171's predicate computed
    expect(shouldLoadNextPage({ ...untouched, ...landed, ...firstPaint })).toBe(false); // what it computes now
  });

  it("DOES paginate once the sentinel has advanced the window", () => {
    // The reader scrolled, the observer fired, the window went 20 → 40 and
    // outran the 20 loaded cards. This is the real "running out" and it must
    // still work, or the fix trades one uninvited fetch for a dead feed.
    expect(shouldLoadNextPage({ ...advanced, ...landed, renderedCount: 20 })).toBe(true);
  });

  it("keeps prefetching one page ahead once the reader is actually moving", () => {
    // Page two landed: 40 loaded, 40 visible. The reader HAS consumed a window
    // by now, so staying a page ahead is legitimate and is not on the cold path.
    expect(
      shouldLoadNextPage({
        visibleCount: 40,
        loadedCount: 40,
        renderedCount: 40,
        initialVisibleCount: INITIAL_VISIBLE,
        hasMore: true,
        loadingMore: false,
      })
    ).toBe(true);
  });

  it("a short page one is NOT stranded — the sentinel reaches it without a scroll", () => {
    // The failure this precondition could plausibly cause: page one renders
    // fewer cards than fill the screen, so the reader can never scroll, so the
    // window never advances, so the feed dead-ends holding six cards with
    // has_more still true.
    //
    // It does not happen, and the mechanism is the sentinel: with six cards the
    // sentinel is already inside the viewport (+400 px rootMargin), the observer
    // fires without a scroll, and the window advances. Both states asserted so
    // the claim is a test, not a comment.
    expect(
      shouldLoadNextPage({ ...untouched, ...landed, visibleCount: INITIAL_VISIBLE, renderedCount: 6 })
    ).toBe(false); // before the observer fires
    expect(shouldLoadNextPage({ ...advanced, ...landed, renderedCount: 6 })).toBe(true); // after
  });

  it("the page passes its own mount seed, not a literal that can drift", () => {
    // `initialVisibleCount` is only meaningful if it is the value `visibleCount`
    // was actually seeded with. Pin both ends: the state seed and the argument.
    expect(PAGE_SOURCE).toMatch(/useState\(PAGE_SIZE\)/);
    expect(PAGE_SOURCE).toMatch(/initialVisibleCount:\s*PAGE_SIZE/);
  });

  it("🔴 the sentinel is not observed against the loading skeleton", () => {
    // The other half of the fix, and without it the precondition is forgeable.
    // `hasMore` is optimistically `true` from the first commit, so the sentinel
    // rendered underneath DiscoverSkeletonGrid's nine placeholders while page
    // one was in flight. Nine placeholders are ~870 px in the three-column
    // desktop layout — inside the observer's 400 px rootMargin — so on a desktop
    // viewport the observer intersected an EMPTY page and advanced the window
    // before a single card existed. `visibleCount > initialVisibleCount` would
    // then be satisfied by a loading state rather than by a reader.
    const sentinelGuard = PAGE_SOURCE.match(/\{!isLoading && !feedUnavailable && \(visibleCount < processedItems\.length \|\| hasMore\) && \(/);
    expect(sentinelGuard).not.toBeNull();
  });

  it("passes the RAW loaded count, not just the filtered one", () => {
    // `loadedCount` only means anything if the page passes the PRE-filter count.
    // `processedItems` is the filtered one; the raw one is the two item arrays.
    expect(PAGE_SOURCE).toMatch(/const loadedCount = page1Items\.length \+ allItems\.length;/);
    expect(PAGE_SOURCE).toMatch(/loadedCount,/);
    expect(PAGE_SOURCE).toMatch(/renderedCount: processedItems\.length,/);
    // …and it must be a dependency of the effect, or a page that lands and
    // filters to nothing never re-evaluates the predicate that rescues it.
    const deps = PAGE_SOURCE.match(
      /loadNextPage\(\);\s*\n\s*\}\s*\n\s*\}, \[([^\]]*)\]\);/
    );
    expect(deps).not.toBeNull();
    expect(deps![1]).toContain("loadedCount");
  });

  it("🔴 the observer effect re-runs when the skeleton clears, or scroll is dead", () => {
    // The regression the sentinel gate invites, and it is worse than the bug it
    // fixes: the observer effect resolves `sentinelRef.current` at effect time.
    // With the node now absent on the first commit, an effect that does not
    // depend on `isLoading` never re-runs, the ref stays null, and infinite
    // scroll never arms on ANY cold load.
    const observerDeps = PAGE_SOURCE.match(
      /observer\.observe\(sentinel\);\s*\n\s*return \(\) => observer\.disconnect\(\);\s*\n\s*\}, \[([^\]]*)\]\);/
    );
    expect(observerDeps).not.toBeNull();
    expect(observerDeps![1]).toContain("isLoading");
  });
});

describe("CERT-603 — a landed page that filters to nothing must still paginate", () => {
  // The P1 that blocked `72fed553`. `renderedCount === 0` was read as "page one
  // has not landed", but the caller passes `processedItems.length`, which is
  // downstream of the L2-215 renderability filter, staleness, local dismissal
  // and category suppression. A good non-empty page can land with backend
  // `has_more = true` and render zero rows — and the old precondition then
  // disabled pagination permanently. Nothing rendered so it never paged; it
  // never paged so nothing ever rendered. A blank Discover surface, forever,
  // with later pages sitting there.

  it("🔴 pages when a non-empty page landed and every row was filtered away", () => {
    // The exact reachable state the cert named: 20 items received, 0 survived
    // filtering, backend still says there is more.
    expect(
      shouldLoadNextPage({
        visibleCount: INITIAL_VISIBLE,
        loadedCount: 20,
        renderedCount: 0,
        initialVisibleCount: INITIAL_VISIBLE,
        hasMore: true,
        loadingMore: false,
      })
    ).toBe(true);
  });

  it("and it does NOT wait for a window the reader cannot possibly advance", () => {
    // The trap in fixing this half-way: with nothing on screen there is nothing
    // to scroll, so the sentinel cannot rescue it and requiring an advanced
    // window would move the deadlock rather than remove it. The filtered-empty
    // branch must fire on the untouched window, which is the only window that
    // state can ever have.
    const stranded = {
      loadedCount: 20,
      renderedCount: 0,
      initialVisibleCount: INITIAL_VISIBLE,
      hasMore: true,
      loadingMore: false,
    };
    expect(shouldLoadNextPage({ ...stranded, visibleCount: INITIAL_VISIBLE })).toBe(true);
  });

  it("still distinguishes it from the cold mount, which must NOT page", () => {
    // Both states have `renderedCount === 0`. Only `loadedCount` separates
    // them, and getting this wrong in the other direction reinstates LAT-P171's
    // `offset=1` race against the request that gates the first card.
    const zeroRendered = {
      visibleCount: INITIAL_VISIBLE,
      renderedCount: 0,
      initialVisibleCount: INITIAL_VISIBLE,
      hasMore: true,
      loadingMore: false,
    };
    expect(shouldLoadNextPage({ ...zeroRendered, loadedCount: 0 })).toBe(false); // cold mount
    expect(shouldLoadNextPage({ ...zeroRendered, loadedCount: 20 })).toBe(true); // filtered empty
  });

  it("the walk forward is serialised and terminates", () => {
    // Why paging on every filtered-empty render is a walk and not a storm: an
    // in-flight request suppresses it, and an exhausted feed ends it. Without
    // both, this branch would spin.
    const filteredEmpty = {
      visibleCount: INITIAL_VISIBLE,
      loadedCount: 20,
      renderedCount: 0,
      initialVisibleCount: INITIAL_VISIBLE,
    };
    expect(shouldLoadNextPage({ ...filteredEmpty, hasMore: true, loadingMore: true })).toBe(false);
    expect(shouldLoadNextPage({ ...filteredEmpty, hasMore: false, loadingMore: false })).toBe(false);
  });

  it("the L2-215 contract this restores is still written where it is enforced", () => {
    // The comment at `processedItems` promises the auto-pager keeps fetching
    // when renderability filtering shortens a page. That promise is the thing
    // the precondition revoked; pin it so the two cannot drift apart again.
    expect(PAGE_SOURCE).toMatch(
      /The auto-pager \(below\) keeps\s*\n?\s*\/\/\s*fetching when this shortens a page, so it can never leave a blank tab\./
    );
  });
});
