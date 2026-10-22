/**
 * A SETTLEMENT POINT IS A RESULT, NOT AN OBSERVATION.
 *
 * #10955 / #11158, Step 2 (Authority's 0545Z point-kind contract; Design's
 * result-mark disposition of 2026-10-22).
 *
 * `/api/futures/{id}/history` ends a graded leg with one synthetic point —
 * `bookmaker: "settlement"`, probability `1.0` for a graded winner or `0.0` for
 * an evidenced loss (`routes/futures.py`, the winner and loser freezes). Its
 * VALUE is the grade. Its TIMESTAMP is never a market time: depending on the
 * served `settlement_basis` it is a scheduled close (`resolution_date`), the
 * moment this system noticed the settlement (`settled_at`, which can lag by
 * years), a nudge past the last trade (`last_observation`), the reading clock,
 * or nothing at all.
 *
 * Drawn as a series point, it became the one thing `chartSeriesPath` promises a
 * solid stroke never is: an unobserved move. A past `resolution_date` an hour
 * after the last trade sits inside the gap threshold, so the leg drew a solid
 * drop to 0% (or climb to 100%) at a time nobody traded, the tooltip printed
 * that time, the domain stretched to it and the combined line summed it.
 *
 * So the point is classified by KIND first, here, and the basis is never
 * consulted — no basis earns a stroke or a timed readout, and an unknown or
 * missing one fails the same way. `FuturesChart` plots only `real`; the grade
 * rides `results` to a separate result mark.
 *
 * Pure and total. A leg with no settlement point is returned as the SAME object,
 * and a field with none anywhere returns the input array itself, so the healthy
 * charts every surface plots nearly all of the time are untouched by
 * construction rather than by equivalence.
 */

import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

/** What a leg's settlement point says. `recorded` = a settlement point whose
 *  value is neither the winner's 1 nor the loser's 0: the result exists but this
 *  chart will not name it. Never a guess, and never "lost". */
export type SettlementResult = "won" | "lost" | "recorded";

export interface SettlementSplit {
  /** The displayed legs, same order, with every settlement point removed. */
  real: FuturesOutcomeHistory[];
  /** outcome_id → the grade its settlement point carried. Only legs that had one. */
  results: Map<number, SettlementResult>;
}

export function isSettlementPoint(point: Pick<FuturesHistoryPoint, "bookmaker">): boolean {
  return point.bookmaker === "settlement";
}

/** The grade as served — the point's own value, read and never repaired. */
function resultOf(point: FuturesHistoryPoint): SettlementResult {
  if (point.probability === 1) return "won";
  if (point.probability === 0) return "lost";
  return "recorded";
}

export function splitSettlementPoints(
  outcomes: readonly FuturesOutcomeHistory[],
): SettlementSplit {
  const results = new Map<number, SettlementResult>();
  let changed = false;
  const real = outcomes.map((outcome) => {
    if (!outcome.history.some(isSettlementPoint)) return outcome;
    changed = true;
    const kept: FuturesHistoryPoint[] = [];
    let last: FuturesHistoryPoint | null = null;
    for (const point of outcome.history) {
      if (isSettlementPoint(point)) last = point;
      else kept.push(point);
    }
    // The last one in served order speaks for the leg if a payload ever
    // carries two; today's freezes append exactly one.
    if (last) results.set(outcome.outcome_id, resultOf(last));
    return { ...outcome, history: kept };
  });
  return { real: changed ? real : (outcomes as FuturesOutcomeHistory[]), results };
}

/** The reader's word for a result, in the product's one settled vocabulary
 *  (`SettledOutcomeMark`). `null` when the chart will not name one. */
export function settlementResultWord(result: SettlementResult): "Won" | "Lost" | null {
  if (result === "won") return "Won";
  if (result === "lost") return "Lost";
  return null;
}
