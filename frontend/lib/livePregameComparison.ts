/**
 * #11296 / #9483 — A LIVE GAME'S CURRENT PROJECTED FINAL, AND THE ONE BEFORE IT.
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: during a game, a reader sees the retained
 * pregame projected final directly beneath the current forecast, with the same
 * team order and the same units and period.
 *
 * The producer (`backend/app/utils/pregame_projection.py`, PR #11401) now also
 * serves `pregame_projection` on the event detail of a row printed `live`:
 * each sportsbook's last pair strictly before the SCHEDULED start, the same
 * object a final carries. `current_odds.live_projection` is the separate
 * in-play pair, built only from rows confirmed at or after the same start, so
 * the two never share a reading taken after kick-off. They may still print the
 * same numbers: a line quoted before the start and confirmed unchanged after it
 * is an honest reading in both (Discover's write-time-dedup control on
 * `a333d40931`), so nothing here asks the pairs to differ.
 *
 * `finalForecastComparison` is NOT reused: it requires a finished status and
 * an actual final score with its period, and a live game has neither. Calling
 * it with a made-up status, or with the current forecast standing in for a
 * score, would print a comparison the page does not hold. This file checks the
 * same baseline fields it checks, field for field (a parity guard in
 * `livePregameComparison11296.test.ts` holds the two to one answer), and
 * replaces the final-only half with a live-only one:
 *
 *   - LIVE. The caller's `isLive` (status `live` AND the start passed, the
 *     predicate the current forecast is chosen by), and never a finished row.
 *   - A TYPED CURRENT FORECAST. Only `admittedLiveProjection` establishes the
 *     current pair's unit and period. The ladders' in-game pair carries
 *     neither, so a page printing it shows no baseline — the period is never
 *     inferred from the sport's name.
 *   - THE PAIR ON SCREEN IS THAT ONE. The baseline sits beneath the printed
 *     current forecast, so it is admitted only when the page printed one
 *     (every existing gate — suspension, reachability, a possible result, a
 *     score to frame it — already decided `heroProjected`) and it is the typed
 *     pair, rounded the way the page rounds it.
 *   - SAME UNIT, SAME PERIOD, SAME START. Both objects carry `unit` and
 *     `period` and they must be equal; both are measured from the row's own
 *     start, and the baseline was read strictly before it.
 *
 * Soccer: the baseline is a 90-minute forecast and stays one in extra time.
 * The producer withholds `live_projection` once regulation ends, so there is
 * no compatible current pair and nothing is compared — the 90-minute pair is
 * never set beside an extra-time game as if it covered it.
 *
 * Every refusal answers null and the caller prints only what it already
 * printed: a missing or incompatible baseline never removes a valid current
 * forecast. No grading, no difference row, no colour: the two pairs are keyed
 * home/away and rounded the way the cards round them.
 */

import {
  FINAL_FORECAST_LABEL,
  FINAL_FORECAST_LABEL_90_MIN,
  PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL,
  PREGAME_KIND_LAST_BEFORE_SCHEDULED_START,
  type FinalForecastComparison,
  type FinalForecastLabel,
  type PregameProjection,
} from "@/lib/finalForecastComparison";
import {
  admittedLiveProjection,
  cardProjectedFinal,
  projectedFinalFormat,
  projectedFinalPeriod,
  type LiveProjection,
  type ProjectedScorePair,
  type SportsbookProjectionFields,
} from "@/lib/projectedFinalPair";

export interface LivePregameComparisonInput {
  sportKey: string | null | undefined;
  status: string | null | undefined;
  /** The page's own live predicate (`status === "live"` and the start passed). */
  isLive: boolean;
  /** The row's `commence_time`: both pairs must be measured from it. */
  commenceTime: string | null | undefined;
  /** `event.current_odds`, whose `live_projection` is the typed current pair. */
  odds: SportsbookProjectionFields | null | undefined;
  /** The current pair the headline prints, after every page gate; null when it prints none. */
  heroProjected: ProjectedScorePair | null | undefined;
  /** `event.pregame_projection`. */
  projection: PregameProjection | null | undefined;
}

export interface LivePregameComparison {
  /** The final band's own words: the reading is the same one, before the same start. */
  label: FinalForecastLabel;
  /** Rounded exactly as the card and the final band round it. Keyed, never sorted. */
  baseline: ProjectedScorePair;
  /** For the existing closed Details disclosure, same fields as a final's. */
  details: FinalForecastComparison["details"];
}

function finiteNonNegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function instant(value: unknown): number | null {
  if (typeof value !== "string" || value === "") return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/**
 * The retained pregame pair to print beneath a live game's current projected
 * final, or null when it cannot be compared honestly. Null adds nothing.
 */
export function livePregameComparison(
  input: LivePregameComparisonInput,
): LivePregameComparison | null {
  const { sportKey, status, isLive, commenceTime, odds, heroProjected, projection: p } = input;

  // Live only. A final has its own band; a scheduled game has no "before".
  if (!isLive || status !== "live") return null;

  // The typed current pair, and the page printing exactly it.
  const live = admittedLiveProjection(odds, sportKey, commenceTime);
  if (!live || !heroProjected) return null;
  if (heroProjected.home !== Math.round(live.home) || heroProjected.away !== Math.round(live.away)) {
    return null;
  }
  // `admittedLiveProjection` checked every field below; read them for the comparison.
  const current = odds?.live_projection as LiveProjection;

  // The baseline's own fields, as `finalForecastComparison` checks them.
  if (!p || typeof p !== "object") return null;
  if (p.kind !== PREGAME_KIND_LAST_BEFORE_SCHEDULED_START) return null;
  if (p.boundary !== "scheduled_start") return null;
  if (p.source !== "sportsbooks") return null;
  if (p.basis !== PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL) return null;

  const format = projectedFinalFormat(sportKey);
  if (!format || p.unit !== format.unit) return null;
  if (p.period !== projectedFinalPeriod(sportKey)) return null;

  // Comparable with the pair above it: the same quantity over the same period.
  if (p.unit !== current.unit || p.period !== current.period) return null;

  if (!Number.isInteger(p.bookmaker_count) || p.bookmaker_count < 1) return null;
  const earliest = instant(p.earliest_captured_at);
  const latest = instant(p.latest_captured_at);
  const boundary = instant(p.boundary_at);
  if (earliest === null || latest === null || boundary === null) return null;
  if (earliest > latest || latest >= boundary) return null;

  // Same game, same start: the baseline was read before the start this row
  // carries, which is the start the in-play pair was measured from.
  const rowStart = instant(commenceTime);
  const currentBoundary = instant(current.boundary_at);
  if (rowStart === null || currentBoundary === null) return null;
  if (boundary !== rowStart || boundary !== currentBoundary) return null;

  if (!finiteNonNegative(p.projected_home_score) || !finiteNonNegative(p.projected_away_score)) {
    return null;
  }
  const baseline = cardProjectedFinal(p, sportKey);
  if (!baseline) return null;

  return {
    label: p.period === "regulation" ? FINAL_FORECAST_LABEL_90_MIN : FINAL_FORECAST_LABEL,
    baseline: { home: baseline.home, away: baseline.away },
    details: {
      sourceLabel: "Sportsbooks",
      bookmakerCount: p.bookmaker_count,
      earliestCapturedAt: p.earliest_captured_at,
      latestCapturedAt: p.latest_captured_at,
      boundaryAt: p.boundary_at,
    },
  };
}
