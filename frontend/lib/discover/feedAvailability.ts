// L2-238 Item 0 — Discover client availability: an UNAVAILABLE feed response is
// not an empty one.
//
// `/api/feed` has three ways of returning zero cards and they mean different
// things. The backend already distinguishes them in the payload
// (`backend/app/routes/feed.py` + `build_feed_cache_metadata`); until now no
// client read that metadata, so all three rendered as "all caught up":
//
//   • cache.status = "unavailable"  — the singleflight waiter ran out of budget
//     with no last-good to serve. `items: []`, `has_more: false`, and NOTHING is
//     known about the feed. Transient. Retryable.
//   • build_quality != "complete"   — a degraded/partial build. Real cards, but
//     the backend deliberately refuses to publish it as shared truth, so an
//     EMPTY one must not overwrite what is already on screen either.
//   • everything else with items: [] — genuine exhaustion. "All caught up" is
//     the honest thing to say.
//
// This mirrors the C129 contract fixtures in
// backend/tests/evals/fixtures/cold_feed_generation_contract.json:
//   typed-unavailable / current-clients-drop-unavailable  → CLIENT_DROPS_UNAVAILABLE_STATE
//   unavailable-looks-empty                               → UNAVAILABLE_MASQUERADES_AS_EMPTY
//   degraded-preserves-last-good / -overwrites-last-good  → DEGRADED_REPLACED_LAST_GOOD
//   old-payload-unavailable-not-zero                      → old payloads stay compatible
//
// Everything here is pure and tolerant: a payload from an older backend (no
// metadata at all) and a payload with MALFORMED metadata both read as
// "available", because only an explicit, well-formed `unavailable` is evidence
// of unavailability. Fabricating the state from absent metadata would turn every
// legitimately empty feed into a permanent retry screen.

/** The backend's bounded, identity-free feed cache metadata. */
export interface FeedCacheMetadata {
  status: string;
  ttl_seconds?: number;
  stale_ttl_seconds?: number;
  reason?: string;
}

/** The cache status the backend uses for the truthful no-data terminal. */
export const UNAVAILABLE_CACHE_STATUS = "unavailable";

/** The build quality the backend reports for a whole, publishable build. */
export const COMPLETE_BUILD_QUALITY = "complete";

export interface FeedAvailability {
  /** True only when the backend explicitly typed this response unavailable. */
  unavailable: boolean;
  /** True when the backend flagged this build as degraded/partial. */
  degraded: boolean;
  /** The decoded cache status, or null when absent/malformed. */
  cacheStatus: string | null;
  /** The bounded reason token, or null when absent/malformed. */
  reason: string | null;
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Decode the bounded cache / build-quality metadata off a feed payload.
 *
 * Never throws and never infers: an absent or malformed `cache` object reads as
 * available with a null status, exactly like a pre-metadata payload.
 */
export function readFeedAvailability(payload: unknown): FeedAvailability {
  const body = (payload ?? {}) as {
    cache?: unknown;
    build_quality?: unknown;
    degraded_reason?: unknown;
  };

  const rawCache = body.cache;
  const cache =
    rawCache && typeof rawCache === "object" && !Array.isArray(rawCache)
      ? (rawCache as Record<string, unknown>)
      : null;

  const cacheStatus = cache ? readString(cache.status) : null;
  const buildQuality = readString(body.build_quality);

  return {
    unavailable: cacheStatus === UNAVAILABLE_CACHE_STATUS,
    // The key is only present when the build was NOT complete, but tolerate a
    // backend that starts sending it unconditionally.
    degraded: buildQuality !== null && buildQuality !== COMPLETE_BUILD_QUALITY,
    cacheStatus,
    reason:
      (cache ? readString(cache.reason) : null) ?? readString(body.degraded_reason),
  };
}

/** Convenience predicate for the one state clients must never render as empty. */
export function isFeedUnavailable(payload: unknown): boolean {
  return readFeedAvailability(payload).unavailable;
}

function itemCount(payload: unknown): number {
  const items = (payload as { items?: unknown } | null | undefined)?.items;
  return Array.isArray(items) ? items.length : 0;
}

function readHasMore(payload: unknown): boolean {
  const value = (payload as { has_more?: unknown } | null | undefined)?.has_more;
  return value === true;
}

export interface FeedPageDecisionInput {
  /** The decoded response body, as returned by `fetchFeed`. */
  payload: unknown;
  /** The client's current `hasMore`, held if this payload cannot speak to it. */
  previousHasMore: boolean;
  /** Whether the client already has cards on screen from an earlier generation. */
  hasRenderedItems: boolean;
}

export interface FeedPageDecision {
  /** Whether this payload's `items` may replace (page 1) or extend (page n) the feed. */
  acceptItems: boolean;
  /** The `hasMore` the client should hold AFTER this payload. */
  hasMore: boolean;
  /** Whether the client must show its existing retryable error/unavailable state. */
  showUnavailable: boolean;
  /** The decoded metadata, for telemetry/tests. */
  availability: FeedAvailability;
}

/**
 * The single decision both the initial load and pagination run on a feed page.
 *
 * An unavailable page is inert: it contributes no items, does not advance or
 * close pagination, and raises the surface's retry state. An incomplete
 * (degraded) page that decoded to zero items is equally barred from blanking a
 * feed that already has cards. Everything else — including a genuinely empty,
 * genuinely exhausted feed — applies normally.
 */
export function decideFeedPage(input: FeedPageDecisionInput): FeedPageDecision {
  const availability = readFeedAvailability(input.payload);

  if (availability.unavailable) {
    return {
      acceptItems: false,
      // Never advance and never CLOSE pagination from a page that carries no
      // knowledge of the feed. `has_more: false` on an unavailable response is
      // an artifact of the empty body, not an exhaustion claim.
      hasMore: input.previousHasMore,
      showUnavailable: true,
      availability,
    };
  }

  const empty = itemCount(input.payload) === 0;
  if (availability.degraded && empty && input.hasRenderedItems) {
    // A partial build that produced nothing is not evidence the feed ended, and
    // it must not replace the complete generation already rendered.
    return {
      acceptItems: false,
      hasMore: input.previousHasMore,
      showUnavailable: false,
      availability,
    };
  }

  return {
    acceptItems: true,
    hasMore: readHasMore(input.payload),
    showUnavailable: false,
    availability,
  };
}
