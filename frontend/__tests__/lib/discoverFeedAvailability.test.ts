// L2-238 Item 0/1 — the Discover client's availability contract, case for case
// against C129 (backend/tests/evals/fixtures/cold_feed_generation_contract.json).
//
// The bug this locks down: `/api/feed` has three ways of returning zero cards —
// typed-unavailable, degraded-and-empty, and genuine exhaustion — and until this
// module existed the clients rendered all three as "all caught up", closed
// pagination on all three, and let all three blank a populated feed.

import {
  readFeedAvailability,
  isFeedUnavailable,
  decideFeedPage,
} from "@/lib/discover/feedAvailability";

/** The exact body backend/app/routes/feed.py returns on the waiter-unavailable path. */
const UNAVAILABLE = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  has_more: false,
  cache: {
    status: "unavailable",
    ttl_seconds: 60,
    stale_ttl_seconds: 900,
    reason: "leader_unavailable",
  },
};

const FRESH = {
  items: [{ type: "futures", data: { id: 1 } }],
  total: 40,
  limit: 20,
  offset: 0,
  has_more: true,
  cache: { status: "miss", ttl_seconds: 60, stale_ttl_seconds: 900 },
};

/** Genuine exhaustion: a COMPLETE build that really has nothing left. */
const GENUINELY_EMPTY = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  has_more: false,
  cache: { status: "hit", ttl_seconds: 60, stale_ttl_seconds: 900 },
};

describe("readFeedAvailability — C129 cache/build-quality decode", () => {
  test("response-cache-hit / shared-candidate-base-hit read as available", () => {
    for (const status of ["hit", "stale", "coalesced", "miss", "last_good"]) {
      const a = readFeedAvailability({ items: [], cache: { status } });
      expect(a.unavailable).toBe(false);
      expect(a.cacheStatus).toBe(status);
    }
  });

  test("typed-unavailable is the only status that reads unavailable", () => {
    const a = readFeedAvailability(UNAVAILABLE);
    expect(a.unavailable).toBe(true);
    expect(a.cacheStatus).toBe("unavailable");
    expect(a.reason).toBe("leader_unavailable");
    expect(isFeedUnavailable(UNAVAILABLE)).toBe(true);
  });

  test("redis-timeout-process-last-good is available, not unavailable", () => {
    const a = readFeedAvailability({
      items: [{ type: "futures", data: { id: 1 } }],
      cache: { status: "last_good", reason: "redis_unavailable" },
    });
    // "redis_unavailable" is a REASON on a served last-good payload. Reading the
    // substring rather than the status would have blanked a working feed.
    expect(a.unavailable).toBe(false);
    expect(a.reason).toBe("redis_unavailable");
  });

  test("old-payload-unavailable-not-zero: no metadata at all stays compatible", () => {
    const old = { items: [{ type: "futures", data: { id: 1 } }], has_more: true };
    const a = readFeedAvailability(old);
    expect(a.unavailable).toBe(false);
    expect(a.degraded).toBe(false);
    expect(a.cacheStatus).toBeNull();
    expect(a.reason).toBeNull();
  });

  test("malformed metadata never fabricates unavailability", () => {
    const malformed: unknown[] = [
      { items: [], cache: null },
      { items: [], cache: "unavailable" },
      { items: [], cache: ["unavailable"] },
      { items: [], cache: { status: 7 } },
      { items: [], cache: {} },
      { items: [], cache: { status: "" } },
      {},
      null,
      undefined,
    ];
    for (const payload of malformed) {
      const a = readFeedAvailability(payload);
      expect(a.unavailable).toBe(false);
      expect(a.cacheStatus).toBeNull();
    }
  });

  test("build_quality is only degraded when present AND not complete", () => {
    expect(readFeedAvailability({ items: [] }).degraded).toBe(false);
    expect(
      readFeedAvailability({ items: [], build_quality: "complete" }).degraded,
    ).toBe(false);
    const degraded = readFeedAvailability({
      items: [],
      build_quality: "degraded",
      degraded_reason: "futures_timeout",
    });
    expect(degraded.degraded).toBe(true);
    expect(degraded.reason).toBe("futures_timeout");
  });
});

describe("decideFeedPage — initial load / background revalidation", () => {
  test("a fresh page applies normally", () => {
    const d = decideFeedPage({
      payload: FRESH,
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(d).toMatchObject({
      acceptItems: true,
      hasMore: true,
      showUnavailable: false,
    });
  });

  test("UNAVAILABLE_MASQUERADES_AS_EMPTY: unavailable never reads as exhaustion", () => {
    const d = decideFeedPage({
      payload: UNAVAILABLE,
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(d.showUnavailable).toBe(true);
    expect(d.acceptItems).toBe(false);
    // `has_more: false` on an unavailable body is an artifact of the empty
    // response, NOT an exhaustion claim — pagination must not close on it.
    expect(d.hasMore).toBe(true);
  });

  test("CLIENT_DROPS_UNAVAILABLE_STATE: the state is surfaced, not swallowed", () => {
    expect(
      decideFeedPage({
        payload: UNAVAILABLE,
        previousHasMore: false,
        hasRenderedItems: true,
      }).showUnavailable,
    ).toBe(true);
  });

  test("unavailable never replaces a nonempty rendered generation with empty", () => {
    const d = decideFeedPage({
      payload: UNAVAILABLE,
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(d.acceptItems).toBe(false);
    expect(d.hasMore).toBe(true);
  });

  test("unavailable preserves the client's hasMore in BOTH directions", () => {
    for (const previousHasMore of [true, false]) {
      expect(
        decideFeedPage({
          payload: UNAVAILABLE,
          previousHasMore,
          hasRenderedItems: true,
        }).hasMore,
      ).toBe(previousHasMore);
    }
  });

  test("genuine empty exhaustion stays distinct and still applies", () => {
    const d = decideFeedPage({
      payload: GENUINELY_EMPTY,
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(d.showUnavailable).toBe(false);
    expect(d.acceptItems).toBe(true);
    expect(d.hasMore).toBe(false);
  });

  test("an OLD payload with genuine exhaustion is unaffected by this change", () => {
    const d = decideFeedPage({
      payload: { items: [], has_more: false },
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(d).toMatchObject({ acceptItems: true, hasMore: false, showUnavailable: false });
  });

  test("DEGRADED_REPLACED_LAST_GOOD: an empty partial build cannot blank the feed", () => {
    const degradedEmpty = {
      items: [],
      has_more: false,
      cache: { status: "miss" },
      build_quality: "degraded",
      degraded_reason: "futures_timeout",
    };
    const overLastGood = decideFeedPage({
      payload: degradedEmpty,
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(overLastGood.acceptItems).toBe(false);
    expect(overLastGood.hasMore).toBe(true);
    // With nothing on screen there is no last-good to protect — apply it.
    const coldStart = decideFeedPage({
      payload: degradedEmpty,
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(coldStart.acceptItems).toBe(true);
  });

  test("a degraded build WITH cards is real content and applies", () => {
    const d = decideFeedPage({
      payload: { ...FRESH, build_quality: "degraded", degraded_reason: "futures_skipped_budget" },
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(d.acceptItems).toBe(true);
    expect(d.hasMore).toBe(true);
  });
});

describe("decideFeedPage — pagination (load more)", () => {
  test("an unavailable page never closes pagination", () => {
    const d = decideFeedPage({
      payload: UNAVAILABLE,
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(d.hasMore).toBe(true);
    expect(d.showUnavailable).toBe(true);
    expect(d.acceptItems).toBe(false);
  });

  test("a real last page still ends the feed honestly", () => {
    const d = decideFeedPage({
      payload: {
        items: [{ type: "futures", data: { id: 9 } }],
        has_more: false,
        cache: { status: "miss" },
      },
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(d.acceptItems).toBe(true);
    expect(d.hasMore).toBe(false);
    expect(d.showUnavailable).toBe(false);
  });

  test("a non-boolean has_more is never trusted as 'more'", () => {
    // poolState.ts learned this the hard way: the string "false" is truthy.
    for (const has_more of ["true", "false", 1, null, undefined]) {
      expect(
        decideFeedPage({
          payload: { items: [], has_more, cache: { status: "hit" } },
          previousHasMore: true,
          hasRenderedItems: false,
        }).hasMore,
      ).toBe(false);
    }
  });
});
