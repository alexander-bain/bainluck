/**
 * #11296 — A FINISHED GAME'S ACTUAL RESULT BESIDE THE SCORE FORECAST BEFORE IT.
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: a finished game's card and headline show
 * its actual result with one honest "Projection before scheduled start"
 * forecast band, in the same units, the same period and the same team order.
 *
 * Why `current_odds` cannot be the forecast here: on a finished game it is each
 * sportsbook's LATEST row, which is in-play (event 15328569: kick-off 17:00Z,
 * pair captured 20:25Z). The producer (`backend/app/utils/pregame_projection.py`,
 * `select_pregame_projection`) serves a separate `pregame_projection` instead:
 * each sportsbook's last pair strictly before the SCHEDULED start, or
 * `pregame_projection_unavailable` naming why not. This file is the one place
 * the web decides whether that object may be printed under a final, and how.
 *
 * It decides nothing the existing files already decide:
 *
 *   - finished      `isFinishedStatus` (completed AND closed), the predicate
 *                   every card and page uses, and the producer's own
 *                   `SETTLED_STATUSES`.
 *   - sport, unit,  `cardProjectedFinal` → `sportsbookProjectedPair` →
 *     rounding      `projectedFinalFormat`: the same sport table, sign gate,
 *                   per-side rounding and level-score refusal the pre-game card
 *                   prints with. Hockey, baseball, tennis and fights answer
 *                   null there, so they answer null here.
 *
 * What it adds is only what a FINAL comparison needs that a pre-game card does
 * not, each refused rather than guessed:
 *
 *   - KIND. Only `last_before_scheduled_start` is admitted, because the label
 *     says exactly that. `latest_before_play` and `opening` are reserved by the
 *     producer and refused here, so a new kind can never print under words that
 *     describe a different reading.
 *   - BOUNDARY. `scheduled_start` only. Nothing here claims an observed
 *     kick-off: the label says "scheduled", and `boundary_at` is the listed
 *     start, not the first whistle.
 *   - UNIT. The served `unit` must equal `projectedFinalFormat(sportKey).unit`.
 *   - PERIOD. The actual score must cover the same period the forecast lines
 *     settle on. Football and basketball forecasts are `full_game`; soccer's
 *     are `regulation` (its sportsbook lines settle on 90 minutes). A soccer
 *     final is compared only when the producer serves `final_score_period:
 *     "regulation"` beside it (the row's own stored period says the match
 *     ended at full time); extra time, penalties and an unknown finish serve
 *     no key and stay withheld. `finalScorePeriod` is the callers' one read of
 *     it. This file does not infer it from the score, clock or competition.
 *
 * No grading: nothing here says who the forecast favoured, whether it was
 * right, or picks a colour. Team order is keyed (home/away), never by value.
 * The actual pair is not returned: the caller already prints it.
 */

import { isFinishedStatus } from "@/lib/eventState";
import {
  cardProjectedFinal,
  projectedFinalFormat,
  projectedFinalPeriod,
  type ProjectedFinalFormat,
  type ProjectedScorePair,
} from "@/lib/projectedFinalPair";

/** The one kind the producer serves today, and the only one admitted here. */
export const PREGAME_KIND_LAST_BEFORE_SCHEDULED_START = "last_before_scheduled_start";

/**
 * The one basis the producer serves (`BASIS_CONSENSUS_SPREAD_TOTAL`), and the
 * only one admitted here: the card's rounding path solves the pair from a
 * spread point and a total, so a band read any other way is refused.
 */
export const PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL = "consensus_spread_total";

/**
 * The visible label over the forecast band. It names what the numbers ARE (a
 * projection) and the boundary they were read before: the band stands on its
 * own under a final, so "Before scheduled start" alone left a reader to guess
 * what two numbers from before play were (Design R1 on PR #11311). Contextual
 * to this band only; the pre-game line keeps its own label.
 */
export const FINAL_FORECAST_LABEL = "Projection before scheduled start";

/**
 * The same band over a soccer final, which compares 90-minute quantities on
 * both sides: the forecast lines settle on 90 minutes, and the band is only
 * admitted when the actual score is the regulation one. The basis is said AT
 * the comparison, in the "(90 min)" the soccer pre-game line already uses, so
 * a reader never has to open Details to learn which score the pair is about.
 */
export const FINAL_FORECAST_LABEL_90_MIN = "Projection (90 min) before scheduled start";

export type FinalForecastLabel = typeof FINAL_FORECAST_LABEL | typeof FINAL_FORECAST_LABEL_90_MIN;

/** Whether a band label is one of the final-comparison labels (the long, wrapping ones). */
export function isFinalForecastLabel(label: string): label is FinalForecastLabel {
  return label === FINAL_FORECAST_LABEL || label === FINAL_FORECAST_LABEL_90_MIN;
}

/** The period a set of scores covers. `regulation` = play ended without extra time. */
export type ScorePeriod = "full_game" | "regulation";

/**
 * `select_pregame_projection`'s served object, field for field
 * (`backend/app/utils/pregame_projection.py`). Times are ISO-8601 strings.
 * `kind` keeps the two reserved producer kinds in its type so a test (and a
 * future reader) can see they exist and are refused.
 */
export interface PregameProjection {
  projected_home_score: number;
  projected_away_score: number;
  kind: "last_before_scheduled_start" | "latest_before_play" | "opening";
  earliest_captured_at: string;
  latest_captured_at: string;
  boundary: "scheduled_start";
  boundary_at: string;
  source: "sportsbooks";
  basis: typeof PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL;
  bookmaker_count: number;
  unit: ProjectedFinalFormat["unit"];
  period: ScorePeriod;
}

/** The producer's refusal reasons for a settled row with no projection. */
export type PregameProjectionUnavailable =
  | "no_start"
  | "start_not_from_schedule"
  | "start_is_placeholder"
  | "format_unsupported"
  | "no_pregame_reading"
  | "read_failed";

export interface FinalForecastComparisonInput {
  sportKey: string | null | undefined;
  status: string | null | undefined;
  /** The actual final score, as the caller already prints it. */
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  /**
   * What the actual score covers, from evidence the caller holds. A
   * scoreboard final in football or basketball is `"full_game"` (overtime
   * included, which is what those lines settle on). `"regulation"` only when
   * something says play ended inside regulation. Null when unknown: refused.
   */
  actualPeriod: ScorePeriod | null | undefined;
  projection: PregameProjection | null | undefined;
}

/**
 * What a finished game's actual score covers, for the three callers to pass as
 * `actualPeriod`. Football and basketball: a scoreboard final is the full
 * game, overtime included. Soccer (and any sport whose lines settle on
 * `regulation`): only the producer's served `final_score_period`, and only its
 * one value `"regulation"`; absent, null or anything else is null, so the
 * comparison is withheld. Never `full_game` for soccer, and never the
 * forecast's own `period`, which says nothing about the scoreboard.
 */
export function finalScorePeriod(
  sportKey: string | null | undefined,
  servedFinalScorePeriod: string | null | undefined,
): ScorePeriod | null {
  const settlesOn = projectedFinalPeriod(sportKey);
  if (settlesOn === "full_game") return "full_game";
  if (settlesOn === "regulation" && servedFinalScorePeriod === "regulation") return "regulation";
  return null;
}

export interface FinalForecastComparison {
  label: FinalForecastLabel;
  /** Rounded exactly as the pre-game card rounds it. Keyed, never sorted. */
  forecast: ProjectedScorePair;
  details: {
    sourceLabel: "Sportsbooks";
    bookmakerCount: number;
    /** The contributing readings span a range; there is no single "recorded at". */
    earliestCapturedAt: string;
    latestCapturedAt: string;
    /** The listed start the readings were taken before. Not an observed start. */
    boundaryAt: string;
  };
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
 * The forecast band to print under a finished game's actual result, or null
 * when any part of it cannot be shown honestly. Null prints nothing: no
 * placeholder, no explanation on the page.
 */
export function finalForecastComparison(
  input: FinalForecastComparisonInput,
): FinalForecastComparison | null {
  const { sportKey, status, homeScore, awayScore, actualPeriod, projection: p } = input;
  if (!isFinishedStatus(status)) return null;
  if (!finiteNonNegative(homeScore) || !finiteNonNegative(awayScore)) return null;
  if (!p || typeof p !== "object") return null;

  if (p.kind !== PREGAME_KIND_LAST_BEFORE_SCHEDULED_START) return null;
  if (p.boundary !== "scheduled_start") return null;
  if (p.source !== "sportsbooks") return null;
  if (p.basis !== PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL) return null;

  const format = projectedFinalFormat(sportKey);
  if (!format || p.unit !== format.unit) return null;

  if (actualPeriod == null || p.period !== actualPeriod) return null;

  if (!Number.isInteger(p.bookmaker_count) || p.bookmaker_count < 1) return null;
  const earliest = instant(p.earliest_captured_at);
  const latest = instant(p.latest_captured_at);
  const boundary = instant(p.boundary_at);
  if (earliest === null || latest === null || boundary === null) return null;
  // The producer reads strictly before the boundary; anything else is not
  // the reading this label describes.
  if (earliest > latest || latest >= boundary) return null;

  if (!finiteNonNegative(p.projected_home_score) || !finiteNonNegative(p.projected_away_score)) {
    return null;
  }
  const forecast = cardProjectedFinal(p, sportKey);
  if (!forecast) return null;

  return {
    label: p.period === "regulation" ? FINAL_FORECAST_LABEL_90_MIN : FINAL_FORECAST_LABEL,
    forecast: { home: forecast.home, away: forecast.away },
    details: {
      sourceLabel: "Sportsbooks",
      bookmakerCount: p.bookmaker_count,
      earliestCapturedAt: p.earliest_captured_at,
      latestCapturedAt: p.latest_captured_at,
      boundaryAt: p.boundary_at,
    },
  };
}
