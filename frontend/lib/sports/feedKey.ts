// L2-240 Item 1 — the Sports feed's SWR cache key, as pure, testable logic.
//
// The blocker this replaces: the Sports page keyed SWR to `null` while Firebase
// auth was still resolving (`authLoading ? null : …`), so a signed-OUT visitor's
// first `/api/feed?mode=sports` request could not even start until the SDK had
// decided there was no user. That auth-before-fetch gap is dead weight on the
// public feed — the HTTP layer already sends the request anonymously until a
// token exists (`AuthProvider` wires the token getter to `null` unless
// `isAuthenticated`), so gating the KEY only delayed the fetch, it never changed
// what the anonymous request returned.
//
// The contract encoded here:
//   • The key is NEVER null — the anonymous request starts immediately, before
//     auth resolves. `authLoading` is deliberately not an input.
//   • Anonymous and signed-in reads live under DISTINCT keys. SWR caches and
//     races per key, so a late-arriving anonymous response cannot overwrite the
//     personalized generation, and a personalized response cannot poison the
//     anonymous cache — the original `authLoading` gate's real fear, solved by
//     key separation rather than by blocking.
//   • A late identity (sign-in that resolves after first paint) changes the key
//     from anon → user, which makes SWR revalidate through the personalized path
//     on its own; `keepPreviousData` on the hook keeps the visible cards up
//     during that transition instead of blanking.
//
// `userId` is `user?.uid ?? null`. Because an unresolved auth state has no user,
// passing the live `user` value already yields the anonymous key during loading
// — which is exactly the "start anonymous immediately" behavior we want.

export type SportsFeedKey = readonly [string] | readonly [string, string];

/** The stable SWR key for the anonymous Sports feed. */
export const SPORTS_FEED_ANON_KEY: SportsFeedKey = ["feed-sports-anon"];

/**
 * The Sports feed SWR key for the current identity.
 *
 * Returns the anonymous key whenever there is no resolved user (including while
 * auth is still loading), and a user-scoped key once an identity exists. Never
 * returns null — the request must not wait on auth.
 */
export function sportsFeedKey(userId: string | null | undefined): SportsFeedKey {
  return userId ? ["feed-sports", userId] : SPORTS_FEED_ANON_KEY;
}

/** The grouped-futures (player props / progressions) SWR key for the current identity. */
export function groupedFeedKey(userId: string | null | undefined): SportsFeedKey {
  return userId ? ["grouped-feed", userId] : ["grouped-feed-anon"];
}

/**
 * A stable identity token for the current key, used to detect a genuine
 * identity change (anon → user, user → different user, user → logout). When this
 * changes the page must drop paginated tail state accumulated under the previous
 * identity so an anonymous page 2+ never rides under a signed-in identity.
 */
export function sportsFeedIdentity(userId: string | null | undefined): string {
  return userId ?? "anon";
}
