import {
  FEED_PAGE_LIMIT,
  shouldAdvanceWindow,
  shouldLoadNextPage,
} from "@/lib/discover/feedPaging";

/**
 * #8176 — Discover's end of feed was a spinner that never stopped.
 *
 * Measured on production, 390px, signed out: the feed served three pages
 * (`offset=0,20,40`), reported `total=115` and `has_more=true` on every one of
 * them, and then stopped — 0 `/api/*` requests across the next 71 seconds, with
 * a loading spinner animating the whole time and no end-of-feed card. 55 of 115
 * cards never reached the reader.
 *
 * The cause was NOT `shouldLoadNextPage`. The reveal window advanced only on an
 * `IntersectionObserver` transition, and the reveal window is the only thing
 * that makes the document taller (rendering is
 * `processedItems.slice(0, visibleCount)`). So the moment the window stopped,
 * the document stopped, the sentinel stayed parked inside the 400px
 * `rootMargin` band, and no further transition could ever be delivered. The
 * window was frozen by the fact that it was frozen.
 *
 * The discriminating measurement: scrolling up 200px (INSIDE the band) produced
 * 0 requests; scrolling up 1600px (OUT of the band, forcing a real exit and
 * re-entry) resumed paging immediately — `offset=60, 80, 100`, articles
 * 31 -> 48 -> 64 -> 75 -> 86, spinner gone.
 *
 * These tests pin the escape, the two states that must still refuse, and the
 * bound that keeps the level-trigger from becoming a fetch storm.
 */

/** The window the page advances by (`PAGE_SIZE` in `discover/page.tsx`). */
const PAGE_SIZE = 20;

/** The stall, exactly as measured: 40 revealed against 48 available. */
const STALL = { visibleCount: 40, renderedCount: 48 } as const;

const advance = (o: Partial<Parameters<typeof shouldAdvanceWindow>[0]> = {}) =>
  shouldAdvanceWindow({
    sentinelVisible: true,
    visibleCount: STALL.visibleCount,
    renderedCount: STALL.renderedCount,
    restorePending: false,
    pageSize: PAGE_SIZE,
    ...o,
  });

/** The pager, as the page calls it, at a given window. */
const pagerAt = (visibleCount: number, renderedCount: number) =>
  shouldLoadNextPage({
    visibleCount,
    loadedCount: 60, // three pages of 20 had landed
    renderedCount,
    initialVisibleCount: PAGE_SIZE,
    hasMore: true,
    loadingMore: false,
  });

describe("#8176 — the reveal window is a level, not an edge", () => {
  it("the page size the window advances by is the page size the feed requests", () => {
    // If these ever diverge the bound below stops meaning "one page past the
    // content", which is the whole safety argument for the level trigger.
    expect(FEED_PAGE_LIMIT).toBe(PAGE_SIZE);
  });

  describe("the measured stall", () => {
    it("is a real deadlock: at 40/48 the pager refuses, so nothing can move", () => {
      // This is the red. The pager's own lookahead puts the fetch threshold at
      // renderedCount - 5 = 43, and the window is stuck at 40. Every input the
      // pager reads is frozen, so it will refuse forever.
      expect(pagerAt(STALL.visibleCount, STALL.renderedCount)).toBe(false);
    });

    it("advances the window even though the sentinel never left the band", () => {
      // The edge-triggered version delivered nothing here: no transition, no
      // callback. The level-triggered question is answerable.
      expect(advance()).toBe(true);
    });

    it("escapes the deadlock and hands the pager a window it will act on", () => {
      // Drive the real loop: advance while the predicate says to, exactly as
      // the effect does, with the sentinel parked in view throughout.
      let visibleCount = STALL.visibleCount;
      let guard = 0;
      while (
        advance({ visibleCount }) &&
        guard++ < 50 // a non-terminating predicate must fail this test, not hang it
      ) {
        visibleCount += PAGE_SIZE;
      }

      expect(guard).toBeLessThan(50); // it terminated on its own
      // Every card already fetched is now revealed — the reader is no longer
      // held at 40 of 48.
      expect(visibleCount).toBeGreaterThanOrEqual(STALL.renderedCount);
      // ...and the pager now requests offset=60, which is the request the
      // browser was measured never to make.
      expect(pagerAt(visibleCount, STALL.renderedCount)).toBe(true);
    });

    it("reaches the end-of-feed branch once the server stops offering more", () => {
      // The spinner and EndOfFeedCard are mutually exclusive on
      // `visibleCount >= processedItems.length`. While the window was frozen
      // below renderedCount the end card was structurally unreachable, which is
      // why the reader got an indefinite loader instead of an honest end.
      let visibleCount = STALL.visibleCount;
      let guard = 0;
      while (advance({ visibleCount }) && guard++ < 50) visibleCount += PAGE_SIZE;

      expect(visibleCount >= STALL.renderedCount).toBe(true);
    });
  });

  describe("the bound — one page past the content, and no further", () => {
    it("refuses once the window is a full page beyond what exists", () => {
      // Without this the sentinel, parked in view while a page is in flight,
      // would advance on every commit: nothing new renders, so the document
      // never grows, so the sentinel never leaves the band. `visibleCount`
      // inflates without limit and the pager walks the feed to exhaustion while
      // the reader sits still (the LAT-P172 / #7417 uninvited-fetch class).
      expect(advance({ visibleCount: 48 + PAGE_SIZE, renderedCount: 48 })).toBe(false);
      expect(advance({ visibleCount: 48 + PAGE_SIZE * 3, renderedCount: 48 })).toBe(false);
    });

    it("allows exactly one page of headroom past the content, not zero", () => {
      // The boundary itself: one below the bound advances, the bound refuses.
      expect(advance({ visibleCount: 48 + PAGE_SIZE - 1, renderedCount: 48 })).toBe(true);
      expect(advance({ visibleCount: 48 + PAGE_SIZE, renderedCount: 48 })).toBe(false);
    });

    it("keeps the cold path alive when page one filters below the seed window", () => {
      // 🔴 Bounding at `renderedCount` instead of one page past it would kill
      // pagination outright here. Page one lands and filters to 16 rows while
      // the window is seeded at 20, so `visibleCount >= renderedCount` already.
      // A zero-headroom bound refuses, the window can never exceed
      // `initialVisibleCount`, and `shouldLoadNextPage`'s LAT-P172 gate reads
      // that as "the reader has not scrolled" for the rest of the session.
      expect(advance({ visibleCount: PAGE_SIZE, renderedCount: 16 })).toBe(true);

      // One advance is enough to open that gate.
      expect(
        shouldLoadNextPage({
          visibleCount: PAGE_SIZE + PAGE_SIZE,
          loadedCount: 20,
          renderedCount: 16,
          initialVisibleCount: PAGE_SIZE,
          hasMore: true,
          loadingMore: false,
        })
      ).toBe(true);
    });
  });

  describe("the two states that must still refuse", () => {
    it("refuses while the sentinel is out of the band", () => {
      // The natural terminator: revealing cards makes the document taller,
      // which pushes the sentinel out, which ends the advance.
      expect(advance({ sentinelVisible: false })).toBe(false);
      // ...and it dominates a window that would otherwise advance.
      expect(advance({ sentinelVisible: false, visibleCount: 0, renderedCount: 999 })).toBe(
        false
      );
    });

    it("refuses while a scroll restore is still landing (#7417)", () => {
      // The reader is clamped at the bottom of a growing document for reasons
      // that have nothing to do with running out of cards, and the restore is
      // about to move them away. This was the 20->40 doubling defect.
      expect(advance({ restorePending: true })).toBe(false);
      expect(advance({ restorePending: true, visibleCount: 0, renderedCount: 999 })).toBe(false);
    });

    it("refuses when both the sentinel is hidden and a restore is pending", () => {
      expect(advance({ sentinelVisible: false, restorePending: true })).toBe(false);
    });
  });
});
