/**
 * #7065 — ONE DECIDER FOR "IS THIS TOURNAMENT LIVE", SHARED BY THE CARD AND THE
 * SECTION IT IS FILED UNDER.
 *
 * The badge and the bucketer used to answer this question separately, and they
 * disagreed on production: `/sports` at 390px on 2026-09-18 headed a section
 * `📅 Upcoming 8` whose FIRST card read `🏌 PGA Tour ● LIVE — Biltmore
 * Championship Asheville`. One screen, two answers.
 *
 * The card was right. `lib/feedSections.ts` and `app/my-stuff/page.tsx` both
 * bucketed on `schedule_status === "in-progress"` ALONE — a string this repo had
 * already measured as never occurring (`__tests__/capture/
 * golfTournamentCardLiveWindowCapture.test.tsx:54`: 0 of 94 `pga_schedule` rows
 * and 0 of 7 tournaments, 2026-08-29; re-measured 0 of 2 on 2026-09-19). A dead
 * test makes its `else` unconditional, so NO tournament could reach Live Now on
 * those surfaces, whatever it was doing.
 *
 * This function is `TournamentCard._isLive` lifted verbatim — same arms, same
 * order, same thresholds. It is deliberately NOT an improved predicate: the card
 * has been deciding the badge this way since UX-P180 and the two sections now
 * agree with it BY CONSTRUCTION rather than by a second implementation that can
 * drift again. Changing what "live" means is a different ship from making one
 * page stop contradicting itself.
 *
 * NOT to be confused with `isTournamentLive` local to
 * `app/categories/golf/tournaments/[slug]/page.tsx`. That one answers a stronger
 * question — "does a live DataGolf LEADERBOARD confirm this tournament" — and it
 * can only be asked on a surface that fetched one. The feed carries no
 * leaderboard, so it cannot use it and is not converted here.
 */

/**
 * The structural minimum this decision reads. Satisfied by `GolfTournament`
 * (the card's prop) and by `FeedTournamentData` (what the feed envelope carries)
 * without either having to be converted first — they disagreed partly because
 * the bucketer only ever saw the feed shape and reached for the one field it
 * recognised.
 */
export interface TournamentLiveInput {
  start_date?: string | null;
  end_date?: string | null;
  schedule_status?: string | null;
  golfers?: readonly { movement_24h?: number | null }[];
}

export function isTournamentLive(tournament: TournamentLiveInput): boolean {
  const now = new Date();

  // ⚠️ `start_date` / `end_date` are CALENDAR DATES stamped at midnight UTC —
  // the first and LAST DAY of the tournament, not the instants it starts and
  // stops. Measured on the served payload: 188 of 188 `pga_schedule` stamps and
  // 6 of 6 tournament windows are exactly `T00:00:00+00:00`. Comparing `now`
  // against the raw `end_date` instant retired the tournament at the START of
  // its final day, so the card went dark for the whole of the final round — in
  // every timezone, UTC included. The window closes when that day is OVER.
  //
  // And the window is a VETO, not a last-resort fallback. The sibling deciders
  // of this same boundary already treat it that way: `isTournamentLive` (end +1d)
  // and `isCompleted` (end +24h) in app/categories/golf/tournaments/[slug]/page.tsx.
  // As a fallback it was unreachable whenever `movement_24h` was non-zero, and
  // residual 24h movement outlives a tournament by a day — which left a pulsing
  // LIVE dot on a card whose champion had already been decided.
  if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const endOfLastDay = new Date(new Date(tournament.end_date).getTime() + 86400000);
    return now >= start && now < endOfLastDay;
  }

  if (tournament.schedule_status === "in-progress") return true;
  // No schedule window to veto against — fall back to the price signal.
  return (tournament.golfers ?? []).some(
    (g) => g.movement_24h !== null && g.movement_24h !== undefined && Math.abs(g.movement_24h) >= 0.01,
  );
}
