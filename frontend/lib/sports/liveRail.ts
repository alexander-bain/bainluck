// UX-1035 / #2709 — the "Live Now" rail is sourced from every live match.
//
// THE DEFECT. `/sports` renders "Live Now · N" by sectioning the items it has
// loaded, and at first paint that is one bounded page of 20, ranked by score
// (L2-240 / LAT-P171 — the bounded page is deliberate and stays). So the
// heading said "live items in the top 20" and printed it as "live". Measured on
// production 2026-09-02 22:5xZ (banked verbatim as
// `backend/tests/fixtures/sports_feed_live_rail_2709.json`): the ranked
// `mode=sports` list held 83 items, **14** of them in progress, **6** of those
// inside the first page. Nine US Open matches were being played and exactly one
// — Wang vs Kalinskaya at rank 16 — was above the cut, so a reader at phone
// width saw "Live Now · 5", a cycling card, three baseball games and a Grand
// Prix, and no tennis at all.
//
// THE FIX IS A SECOND SMALL REQUEST, NOT A BIGGER FIRST ONE. `live_only=true`
// is a projection the server takes off the SAME stored page base the scroll
// reads, so it costs no extra build and cannot re-rank: the rail is the live
// part of the list below it, in the list's own order. The alternatives were
// both worse — raising the page limit undoes a measured latency fix, and
// eagerly paging to the end reinstates the 200-item pull L2-240 removed.
//
// 🔴 THE RAIL DOES NOT RENDER ITSELF. Its items are merged into the same pool
// `groupFeedIntoSections` already sections, so there is exactly one sectioner
// and one "Live Now" heading on the page. If the server's predicate
// (`app/utils/feed_live_section.py`) and the client's sectioner ever disagree,
// a mismatched card lands under "Upcoming" — visibly wrong rather than silently
// missing, which is the direction we want the failure to fall.
// `__tests__/lib/liveRailParity2709.test.ts` pins the two against each other on
// the banked payload.

import type { FeedItem } from "@/lib/types";

/**
 * How many live cards the rail will ask for.
 *
 * Generous rather than tuned: 14 were in progress on a mid-tournament Tuesday
 * with one Grand Slam running, and the number a Saturday in the NFL season
 * produces has not been measured. The cost of asking for more than exist is
 * nothing — the projection is a filter over a list that is already built and
 * already in Redis — while the cost of asking for too few is the exact defect
 * being fixed, one cut moved.
 */
export const LIVE_RAIL_LIMIT = 100;

/**
 * Merge the live projection into the paged feed pool, live items first.
 *
 * Live first so "Live Now" comes out in the projection's (= the build's) score
 * order rather than in "whatever page-1 happened to hold, then the rest". The
 * other sections are unaffected: a live item is not in them, so their relative
 * order is exactly what it was.
 *
 * De-duplication is the CALLER's existing one, passed in, because the pool
 * already has a stable-id contract and a second hand-rolled notion of item
 * identity is how two counts of one population drift apart.
 */
export function mergeLiveRail(
  liveItems: readonly FeedItem[] | undefined,
  pagedItems: readonly FeedItem[],
): FeedItem[] {
  return [...(liveItems ?? []), ...pagedItems];
}
