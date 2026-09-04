/**
 * How often an open event page re-reads `/api/events/{id}` — one pure rule.
 *
 * ═══ WHY THIS IS A FUNCTION AND NOT AN INLINE LAMBDA (live/058, CERT-854) ═══
 *
 * It used to be three nested ternaries inside the SWR config, which is exactly
 * where a defect can live unexamined: live/034 S2 correctly stopped polling
 * while the SSE stream delivers, and that silently froze every field the stream
 * does not carry. Nothing could assert the rule because nothing could call it.
 *
 * A frame carries the probability and its source. Nothing else. So the question
 * this function answers is not "is the stream up" but **"can the stream keep
 * THIS payload current"** — and for a tennis match, whose line moves on every
 * game won, the answer is no.
 *
 * ═══ CAPABILITY, NOT EVIDENCE (CERT-858 repair) ═══
 *
 * The first repair asked that question of the payload alone: `hasLinescore`.
 * That is the right question one poll too late. A reader who opens a live
 * tennis page in the seconds before `poll_live_tennis_scores` has written its
 * first line — or on a match ESPN has in play with no set line yet, which is
 * every match's own first game — gets a payload with no `linescore`, a
 * connected stream, an interval of `0`, and therefore **no request that could
 * ever fetch the line**. The page that most needs the score is the one that
 * never acquires it, and it stays that way for as long as the reader watches.
 *
 * So the rule reads the SPORT as well. A live tennis row is going to carry a
 * line whether or not this particular response does yet, and the poll is the
 * only thing that can go and get it. Absence is not evidence of absence
 * (gotcha #53) — here it is evidence of earliness.
 */

/** The 32 s poll that matches the backend's own live cadence. */
export const LIVE_REFRESH_INTERVAL = 32000;
export const SCHEDULED_REFRESH_INTERVAL = 120000;

/**
 * The bounded refresh for a streaming page whose score is finer than the stream.
 *
 * 15 s, derived rather than picked, and it is the third leg of a budget whose
 * other two are stated at `poll-live-tennis-scores`' beat entry:
 *
 *     server write grid   20 s  ->  median 10.0 s
 *     detail cache        10 s  ->  median  5.0 s
 *     this poll           15 s  ->  median  7.5 s
 *                                   ─────────────
 *                                        22.5 s, inside the 30 s bar
 *
 * Polling faster than the server writes buys nothing but requests.
 */
export const LIVE_LINESCORE_REFRESH_INTERVAL = 15000;

/** The one `linescore.state` that means "this score will not change again". */
const LINESCORE_DECIDED = "decided";

/**
 * Sport-key PREFIXES whose live row carries a score finer than `home_score`.
 *
 * The twin of `_EVENT_DETAIL_LIVE_TTL_BY_SPORT_PREFIX` in
 * `backend/app/routes/events.py`, and a prefix list for the same reason: the
 * tennis key space grows by tournament (`tennis_atp_us_open`,
 * `tennis_wta_wimbledon`), so a literal list of sport keys would silently miss
 * the next Slam and put its live pages back on a frozen line.
 */
export const FINER_GRAIN_SPORT_PREFIXES: readonly string[] = ["tennis"];

/** Does this sport publish a score the SSE frame cannot carry? */
export function sportKeepsALinescore(sport: string | null | undefined): boolean {
  return FINER_GRAIN_SPORT_PREFIXES.includes(String(sport ?? "").split("_")[0]);
}

/**
 * The shape this module reads. The full type is `TennisLinescore`.
 *
 * live/059 addendum (D59 = A′): `state` is now nullable. The line's SCORE may
 * come from StatPal while its STATE comes from ESPN, and on the rare pass where
 * ESPN refused the fixture entirely there is a score with no state — `null`
 * rather than a borrowed word, because a state from anything but the state
 * authority is the mix that build forbids. `null !== "decided"`, so such a page
 * keeps polling, which is the right answer: it has a score and no idea whether
 * the match is still on.
 */
interface LinescoreLike {
  state?: string | null;
}

export interface LiveDetailRefreshInput {
  streamConnected: boolean;
  status: string | undefined;
  /** The event's sport key, e.g. `tennis_atp_us_open`. */
  sport?: string | null;
  /** The payload's `linescore`, passed whole — see `streamIsBlindToTheScore`. */
  linescore?: LinescoreLike | null;
}

/**
 * Is there a score on this row that moves and the stream does not carry?
 *
 * Three states, and the middle one is the CERT-858 repair:
 *
 *   line present, `in_progress`   blind — it moves on every game
 *   NO line, live, finer-grained  blind — the line is coming and only a
 *                                 request can fetch it (first acquisition)
 *   line present, `decided`       NOT blind — the score cannot move again, so
 *                                 a poll would be requests for nothing
 *
 * Note the third: `decided` arrives on the 20 s score grid and `completed`
 * arrives on the 60 s status grid, so a decided line under a still-`live`
 * status is an ordinary minute-long window, not an anomaly. Reading the line's
 * own state rather than the row's status is what stops that minute from being
 * a minute of pointless requests.
 *
 * The linescore is passed WHOLE rather than as a boolean because presence and
 * decidedness are two facts about one object, and two booleans is two chances
 * for a caller to hand this function a combination that cannot exist.
 */
export function streamIsBlindToTheScore({
  status,
  sport,
  linescore,
}: Omit<LiveDetailRefreshInput, "streamConnected">): boolean {
  if (linescore) return linescore.state !== LINESCORE_DECIDED;
  return status === "live" && sportKeepsALinescore(sport);
}

export function liveDetailRefreshInterval({
  streamConnected,
  status,
  sport,
  linescore,
}: LiveDetailRefreshInput): number {
  if (streamConnected) {
    // A connected stream silences the poll only for a payload it can keep
    // current. `0` here on a live tennis page is a card that shows the
    // scoreline it had when the reader arrived — or NO scoreline at all,
    // forever, if it arrived first — while the probability ticks beside it.
    return streamIsBlindToTheScore({ status, sport, linescore })
      ? LIVE_LINESCORE_REFRESH_INTERVAL
      : 0;
  }
  // The stream is down, refused, or never opened. A push path that dies must
  // degrade to polling, never to a frozen number.
  return status === "live" ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;
}
