// My Stuff — which feed futures belong on the page, and where (ux/1070 item 5).
//
// My Stuff has always thrown away every `futures` item the feed serves it:
//
//     if (item.type === "futures") continue;  // team futures section handles them
//
// which was true while the backend admitted futures ONLY when they touched one
// of the viewer's teams — those all arrive again, merged and laddered, from
// `/api/feed/my-team-futures`.
//
// It stopped being true when a FOLLOWED sport with no teams began admitting its
// own markets (see `MY_STUFF_FOLLOW_WINDOW_DAYS` in `routes/feed.py`). Alex
// follows PGA golf at 1.0; this week the site holds the whole Omega European
// Masters grid — Winner, Top 5, Top 10, Top 20, Make the Cut — and there is no
// team in golf for the team section to hang it off. Dropped here, it would have
// been admitted by the server and shown by nobody.
//
// So the partition is by SPORT SHAPE, and it is exact rather than heuristic:
// the six categories below are precisely the ones the server admits on a TEAM
// match (`MY_STUFF_ALLOWED_CATEGORIES`), so anything else in the futures half
// arrived on a follow and has no team block to live in.

import type { FeedFuturesData, FeedItem } from "./types";

/**
 * The exact params My Stuff asks `/api/feed` for.
 *
 * Exported, and the page imports it, because the ONE thing that made ux/1070
 * item 5 ship as no visible change was invisible from both ends: the server
 * admitted the followed-sport markets, the page knew how to render them, and
 * the request in between said `include_futures: false`, so `_score_futures`
 * never ran (CERT-942). Producer and consumer were each tested and each passed.
 *
 * A test can only catch that by exercising the REQUEST the page actually makes,
 * and it can only do that honestly if the params have one owner instead of being
 * retyped in the test. `__tests__/lib/myStuffFeedRequest.test.ts` builds a URL
 * from this object through the real `fetchFeed` and asserts futures are not
 * switched off.
 *
 * `include_futures` is ABSENT rather than `true` on purpose: the backend
 * defaults it to true, and `fetchFeed` only ever serializes the `false` case, so
 * naming it here would add a param to the URL for no behaviour. What matters is
 * that it is never set to false — which is what the test asserts.
 */
export const MY_STUFF_FEED_PARAMS = {
  limit: 100,
  my_teams_only: true,
} as const;

/**
 * The categories whose futures reach My Stuff through a TEAM.
 *
 * Mirrors `MY_STUFF_ALLOWED_CATEGORIES` in `backend/app/routes/feed.py`. Keep
 * them equal: a category here that the server admits on a follow would be
 * dropped by this page, and a category missing here would print twice — once as
 * a card and once inside "Your Teams' Odds".
 */
export const MY_STUFF_TEAM_SPORT_CATEGORIES: ReadonlySet<string> = new Set([
  "basketball",
  "football",
  "baseball",
  "hockey",
  "soccer",
  "mma",
]);

/**
 * Does this futures item belong in the followed-sport section?
 *
 * True for a market in a sport the viewer follows that has no team dimension —
 * golf and tennis today. False for a team-sport market, which the team section
 * already renders from its own endpoint, and false for a market with no
 * category at all: an unlabelled market is not evidence of a followed sport.
 */
export function isFollowedSportFutures(item: FeedItem): boolean {
  if (item.type !== "futures") return false;
  const category = (item.data as FeedFuturesData).llm_sport_category;
  if (!category || typeof category !== "string") return false;
  return !MY_STUFF_TEAM_SPORT_CATEGORIES.has(category.trim().toLowerCase());
}

/**
 * Followed-sport futures, soonest resolution first.
 *
 * Resolution order, not score order: this section answers "what is on right
 * now in the sports I follow", so the tournament finishing on Sunday leads the
 * one finishing next month. Undated markets sort last rather than first — the
 * server's window means there should be none, and a missing date is not a
 * reason to headline a card.
 */
export function followedSportFutures(items: FeedItem[]): FeedItem[] {
  const stamp = (item: FeedItem) => {
    const raw = (item.data as FeedFuturesData).resolution_date;
    const t = raw ? new Date(raw).getTime() : NaN;
    return Number.isNaN(t) ? Number.POSITIVE_INFINITY : t;
  };
  return items.filter(isFollowedSportFutures).sort((a, b) => stamp(a) - stamp(b));
}
