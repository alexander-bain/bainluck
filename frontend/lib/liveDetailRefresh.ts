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
 * THIS payload current"** — and for a payload with a `linescore`, which moves on
 * every game won, the answer is no.
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

export function liveDetailRefreshInterval({
  streamConnected,
  status,
  hasLinescore,
}: {
  streamConnected: boolean;
  status: string | undefined;
  hasLinescore: boolean;
}): number {
  if (streamConnected) {
    // A connected stream silences the poll only for a payload it can keep
    // current. `0` here with a linescore on the row is a card that shows the
    // scoreline it had when the reader arrived, forever, while the probability
    // ticks beside it — MORE wrong than before the score existed, because now
    // it looks precise.
    return hasLinescore ? LIVE_LINESCORE_REFRESH_INTERVAL : 0;
  }
  // The stream is down, refused, or never opened. A push path that dies must
  // degrade to polling, never to a frozen number.
  return status === "live" ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;
}
