/**
 * #10294 — THE HERO'S SCORE IS THE NEWEST READ OF THE EVENT ROW THE PAGE HOLDS.
 *
 * Two responses on a live game page print the same event row's score:
 * `/api/events/{id}` and `/api/events/{id}/game-markets`. Both serialize
 * `event.home_score` / `event.away_score` and stamp them through the same
 * `score_observation_fields` helper (`routes/events.py`). They differ only in how
 * often the page asks. Detail is re-read every 120 s while the price stream is
 * connected (`makeEventRefreshInterval`: the stream carries prices, not scores).
 * Game markets is re-read every few seconds by `useGameMarketsStream`.
 *
 * The hero read detail only. On production 15320207 (CFL, 2026-10-03) the score
 * went 13–20 → 13–27 at 03:54:22Z. The page's own game-markets read carried it
 * at 03:55:11Z, and the hero printed 13–20 until the detail read at 03:56:02Z.
 * A same-score confirmation at 04:05:06Z waited 92 s the same way. The clock
 * was honest throughout (#4571). It was just late.
 *
 * So the pair comes from whichever read carries the strictly newer
 * `score_observed_at`. Detail is kept whenever the question cannot be answered:
 *
 *   - a different event id (detail can answer with a canonical row, Q050);
 *   - either read not `live` — finals, starts and stoppages arrive with detail's
 *     status, and a final score must not sit under a live hero;
 *   - half a pair on the game-markets side, so one side never moves alone;
 *   - detail carries a `linescore` (tennis sets/games). Only detail serves that
 *     line, so a newer pair would sit beside an older line — "1–1" over
 *     "7-6, 2-1". Found driving the page, not by a unit;
 *   - either stamp missing or unparseable. An unknown age is not upgraded by a
 *     guess, and the backend clears the stamp on some changed writes.
 *
 * This is the event-row arm only. `computeLastChartPoint` still ranks it against
 * the history series exactly as before. `score_history` is still not allowed to
 * fill in for absent ESPN rows (#5521's boundary).
 */

export interface ServedScoreRead {
  id?: number | null;
  event_id?: number | null;
  status?: string | null;
  home_score?: number | null;
  away_score?: number | null;
  score_observed_at?: string | null;
  linescore?: unknown;
}

export interface ServedScore {
  home_score: number | null;
  away_score: number | null;
  score_observed_at: string | null;
  /** Which read supplied the pair. `null` when there is no detail read yet. */
  from: 'detail' | 'game-markets' | null;
}

const stampMs = (stamp: string | null | undefined): number => (stamp ? Date.parse(stamp) : NaN);

export function newestServedScore(
  detail: ServedScoreRead | null | undefined,
  gameMarkets: ServedScoreRead | null | undefined,
): ServedScore {
  if (!detail) return { home_score: null, away_score: null, score_observed_at: null, from: null };
  const held: ServedScore = {
    home_score: detail.home_score ?? null,
    away_score: detail.away_score ?? null,
    score_observed_at: detail.score_observed_at ?? null,
    from: 'detail',
  };
  if (!gameMarkets) return held;
  if (detail.id == null || gameMarkets.event_id !== detail.id) return held;
  if (detail.status !== 'live' || gameMarkets.status !== 'live') return held;
  if (detail.linescore != null) return held;
  if (gameMarkets.home_score == null || gameMarkets.away_score == null) return held;
  const heldMs = stampMs(detail.score_observed_at);
  const offeredMs = stampMs(gameMarkets.score_observed_at);
  if (Number.isNaN(heldMs) || Number.isNaN(offeredMs) || offeredMs <= heldMs) return held;
  return {
    home_score: gameMarkets.home_score,
    away_score: gameMarkets.away_score,
    score_observed_at: gameMarkets.score_observed_at ?? null,
    from: 'game-markets',
  };
}
