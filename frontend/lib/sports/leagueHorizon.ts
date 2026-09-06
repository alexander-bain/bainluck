/**
 * ux/1096 — #3028: A LEAGUE PAGE'S WINDOW STOPS BEING SHORTER THAN ITS OFFSEASON.
 *
 * ═══ WHAT A READER SAW, MEASURED ═══
 *
 * `/sports/basketball_nba`, 2026-09-06, above the fold, whole page:
 *
 *     No games
 *     This page lists games for this league.
 *
 * while `/api/leagues/basketball_nba` was answering `8 upcoming games` and
 * `94 markets`, and the database held 41 NBA rows with `status='scheduled'`
 * and a future `commence_time`.
 *
 * `app/sports/[key]/page.tsx` asked `fetchEvents({ sport, days: 14 })`. NBA's
 * first game is 2026-10-20 — **44 days out**. The window is six weeks short of
 * the season, so the league reads as though it does not exist.
 *
 * ═══ WHY THE FIX IS NOT "MAKE THE WINDOW BIGGER" ═══
 *
 * 🔴 THE LOAD-BEARING MEASUREMENT. Production, the same morning:
 *
 *     icehockey_nhl         days=14 ->   1    days=90 ->  32
 *     basketball_nba        days=14 ->   0    days=90 ->  36
 *     americanfootball_nfl  days=14 ->  17    days=60 -> 120
 *     baseball_mlb          days=14 -> 151    days=90 -> 151
 *
 * The NFL row is the whole argument. A globally widened horizon would bury
 * this Sunday's slate under the remaining four months of the season — trading
 * a dead page for a useless one, on a league that is working today. So the
 * widening has to be CONDITIONAL, and the condition has to name the thing that
 * is actually wrong.
 *
 * The NHL row is why the condition is not "the window came back empty". NHL's
 * opener drifted from 15 days out to 13 while this issue sat, so it has just
 * crossed into the fixed window: the page no longer says "No games", it shows
 * **1 of the 32 NHL games we hold**. Same defect, quieter face. A trigger that
 * only fires on zero would call that page fixed.
 *
 * ═══ THE CONDITION ═══
 *
 * A fixed window is trustworthy exactly when it is not the binding constraint,
 * and the signal that it IS binding is that the league is not playing yet:
 * nothing live, and the next game further out than the near term. In season
 * that is never true — every league with games this week clears it — and out
 * of season it is always true, whether the window returned nothing (NBA) or
 * grazed one fixture at its far edge (NHL).
 *
 * So: **widen when nothing is being played and the next game is more than
 * `LEAGUE_NEAR_TERM_DAYS` away.** That is a statement about the LEAGUE, not
 * about the size of the payload, which is why it does not need a row-count
 * floor picked out of the air.
 *
 * ═══ WHY THIS IMPORTS `eventSectionKey` ═══
 *
 * "Is this event still to play" already has an owner — `lib/eventState.ts` —
 * and `lib/sports/leagueSections.ts` documents at length why a surface must
 * join that authority rather than write a fourth `=== "closed"` chain. This
 * module needs the same partition the page is about to render with, so it asks
 * the same function. A `suspended` fixture therefore counts as still-to-play
 * here for the same reason it renders in the live bucket there, and cannot
 * silently make an in-season league look dormant.
 *
 * ═══ NO CLOCK READ INSIDE A LOOP ═══
 *
 * `now` is a PARAMETER with a `Date.now()` default (gotcha #44: offset from a
 * fixed anchor, never branch on the wall clock). Both the near-term boundary
 * and `eventSectionKey`'s own grace rung are evaluated against that one anchor,
 * so a test can stand on either side of the boundary and get a stable answer.
 *
 * PURE — reads its arguments, allocates nothing the caller can see.
 */

import type { Event } from "@/lib/types";
import { eventSectionKey } from "@/lib/eventState";

/**
 * The window the page asks for first, and the only one an in-season league
 * ever sees. Unchanged from what `app/sports/[key]/page.tsx` has always sent —
 * this fix does not touch the working case.
 */
export const LEAGUE_WINDOW_DAYS = 14;

/**
 * How soon a league's next game has to be for the fixed window to be believed.
 *
 * Half the window, deliberately: a league whose next fixture is inside the
 * first half of the window is plainly playing, and one whose only fixture sits
 * at day 13 of 14 is plainly not — that is exactly the NHL page this issue was
 * re-measured on. Every in-season league in the table above clears this by
 * days, not hours, so the boundary is nowhere near a live surface.
 */
export const LEAGUE_NEAR_TERM_DAYS = 7;

/**
 * The horizon used once the fixed window is known to be the binding
 * constraint.
 *
 * 90 days rather than 60 because 60 was measured short: NBA at `days=60`
 * returns 24 of the 36 games we hold, cutting the schedule off in the middle
 * of November for no reason a reader could see. 90 returns everything either
 * league has (NHL's last held game is 2026-10-10, NBA's 2026-11-28), so the
 * page is bounded by what we actually hold rather than by a second arbitrary
 * date. `/api/events` caps its own page at `limit=200`, which is the real
 * ceiling and is not reached here.
 */
export const LEAGUE_OFFSEASON_HORIZON_DAYS = 90;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/**
 * Is the 14-day window the reason this page looks empty?
 *
 * `true` when nothing in the payload is being played and no game still to play
 * starts within `LEAGUE_NEAR_TERM_DAYS` — including the case where there is
 * nothing still to play at all, which is the dead-page report as filed.
 *
 * `false` for every league that has a game on this week, so an in-season page
 * issues exactly the one request it always did.
 */
export function needsWiderHorizon(
  events: Event[],
  now: number = Date.now(),
): boolean {
  const nearTermCutoff = now + LEAGUE_NEAR_TERM_DAYS * MS_PER_DAY;

  for (const event of events) {
    const section = eventSectionKey(event.status, event.commence_time, now);
    if (section === "finished") continue;

    // Live (and suspended, which the shared ladder files as live) means the
    // league is playing right now. Nothing else needs asking.
    if (section === "live") return false;

    // An upcoming row with no usable commence_time cannot be shown to be far
    // out, so it is not evidence FOR widening. It is not evidence against
    // either — fall through and let the rest of the payload answer.
    const startsAt = event.commence_time
      ? new Date(event.commence_time).getTime()
      : NaN;
    if (Number.isFinite(startsAt) && startsAt <= nearTermCutoff) return false;
  }

  return true;
}
