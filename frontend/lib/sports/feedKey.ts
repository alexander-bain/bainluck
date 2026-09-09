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
 * The DEFERRED lookup that fills the Finished section (#4454, second pass).
 *
 * ═══ WHY A SECOND REQUEST EXISTS AT ALL ═══
 *
 * The first pass of #4454 shipped, deployed, and rendered nothing. The section
 * logic was right; it was never handed a settled game. Page one asks for 20
 * items and the ranker puts last night's finals from position 30 down —
 * measured on production 2026-09-09:
 *
 *     limit=20  16 events   0 settled          <- what the page asks for
 *     limit=40  25 events   1 settled          Shelton-Alcaraz at position 30
 *     limit=100 60 events  20 settled
 *
 * So the reader only ever met a Finished section by scrolling past thirty cards,
 * which is not "findable the morning after" in any sense Alex would accept.
 *
 * ═══ WHY NOT JUST RAISE THE PAGE'S LIMIT ═══
 *
 * Because `app/sports/page.tsx` tracks that request's ~1.8s wire time and the
 * latency lane is actively defending it. Tripling the FIRST-PAINT payload to
 * populate a section below the fold is the wrong trade. This key is deliberately
 * distinct so the deferred lookup lands in its own SWR cache slot and can never
 * overwrite, delay or race the payload page one renders from.
 *
 * ═══ WHY IT IS CHEAPER THAN IT LOOKS ═══
 *
 * The lookup passes `include_futures=false`, which makes the window far denser
 * in the only card type it cares about. Measured the same afternoon:
 *
 *     limit=60 WITH futures      36 events   7 settled
 *     limit=40 WITHOUT futures   36 events   7 settled   marquee at position 22
 *
 * Same yield, a third smaller payload. `FINISHED_LOOKUP_LIMIT` is that 40.
 */
export function sportsFinishedLookupKey(userId: string | null | undefined): SportsFeedKey {
  return userId ? ["feed-sports-finished", userId] : ["feed-sports-finished-anon"];
}

/**
 * How deep the deferred lookup reads.
 *
 * 40 with futures excluded, which is the measured knee: it clears the marquee
 * final (position 22) with room to spare and returns seven of them, while
 * staying smaller on the wire than a 60-item pull that yields exactly the same
 * seven. Raising it buys more of the day's results, not a better chance at the
 * one that matters, and the section is capped for the reader anyway.
 */
export const FINISHED_LOOKUP_LIMIT = 40;

/**
 * A stable identity token for the current key, used to detect a genuine
 * identity change (anon → user, user → different user, user → logout). When this
 * changes the page must drop paginated tail state accumulated under the previous
 * identity so an anonymous page 2+ never rides under a signed-in identity.
 */
export function sportsFeedIdentity(userId: string | null | undefined): string {
  return userId ?? "anon";
}
