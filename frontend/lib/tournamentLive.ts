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
 * page stop contradicting itself — #9596 was that ship: it retired the price
 * arm (see the last line of `isTournamentLive`), for every reader at once.
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
  champion?: string | null;
}

export function isTournamentLive(tournament: TournamentLiveInput): boolean {
  // #9212 — a tournament with a champion is over, and every arm below can still
  // say yes to one: the calendar window runs to the end of the last day's UTC
  // date (so "LIVE" hours after the final putt in Europe), and a winner's 24h
  // movement outlives the tournament. The server's `_tournament_is_live` asks
  // this first too. Absent or null is "not known to be decided", and the arms
  // below decide exactly as before.
  if (tournament.champion) return false;
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
  // #9596 — no dates of play and no in-progress status: we do not know, and
  // "not known to be live" is not LIVE. This arm used to fall back to the price
  // signal (any golfer's 24h movement ≥ 0.01), but a price move is not evidence
  // golf is being played — it is likeliest right after a book opens, which is
  // always BEFORE round 1. Production 2026-09-29: the LPGA LOTTE Championship
  // (no `start_date`/`end_date` served) read ● LIVE under Live Now a day after
  // Kalshi opened it and two days before its first tee time.
  return false;
}

/**
 * #9212 — has this tournament been DECIDED? Either the server named its champion
 * (ESPN called it final) or it is a calendar marquee in its post-settlement
 * WHAT-HIT window. A decided tournament is filed with the finished items and its
 * card leads with the result — never "LIVE" over a 100% "Leader", and never
 * "Upcoming". The web does not infer "decided" from a price.
 */
export function isTournamentDecided(tournament: {
  champion?: string | null;
  marquee_whathit?: boolean;
}): boolean {
  return !!tournament.champion || tournament.marquee_whathit === true;
}

/** A player's name folded for matching: accents, case and spacing dropped. */
function foldName(name: string): string {
  return name.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * #9212 — the index of the champion's own row, or -1. The server spells the
 * champion as the payload's golfer row does, so this is a name match; folding
 * only absorbs accents and case. -1 means "no row is the champion" (a team side,
 * or a champion outside the rows served), and a caller must then name the
 * champion WITHOUT borrowing the price leader's number.
 */
export function championRowIndex(
  golfers: readonly { name: string }[] | null | undefined,
  champion: string | null | undefined,
): number {
  if (!champion || !golfers) return -1;
  const want = foldName(champion);
  if (!want) return -1;
  return golfers.findIndex((g) => foldName(g.name ?? "") === want);
}

/**
 * #9378 — has this tournament's first day not begun yet? True only when
 * `start_date` parses and `now` is before it; absent or unparseable is "not
 * known to be before the start", so callers decide exactly as before.
 *
 * `start_date` is the first CALENDAR DAY stamped at midnight UTC (see
 * `isTournamentLive` above), so this flips at the same instant the live window
 * opens — the two never both say no to a tournament in progress.
 *
 * The card reads it to caption its hero: before a shot is hit, the rank-1 row is
 * the PRICE favourite, and "Leader" in golf means the top of the leaderboard.
 * /sports on 2026-09-28 read "11.8% Ludvig Aberg · Leader" three days before
 * the Alfred Dunhill Links began.
 */
export function isTournamentBeforeStart(tournament: { start_date?: string | null }): boolean {
  if (!tournament.start_date) return false;
  const start = new Date(tournament.start_date).getTime();
  if (Number.isNaN(start)) return false;
  return Date.now() < start;
}
