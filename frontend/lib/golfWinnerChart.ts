/**
 * #6243 — which market the golf hub's "Win Probability" chart may draw, and when a
 * market can actually draw one.
 *
 * The backend sorts `current_event.market_ids` DataGolf Winner first (the progression
 * table binds to `market_ids[0]`, so that order stays). DataGolf's Winner can hold a
 * whole week of history at ONE timestamp — 30 outcomes, 1 point each — and the chart's
 * fallback used to advance only on `outcomes.length === 0`, so it stopped there and
 * printed "Limited price history available" while Kalshi's traded Winner field for
 * the same tournament sat next in the list with a real curve.
 */
import type { FuturesHistoryResponse } from "@/lib/types";

/** The tournament Winner question — the same test the backend's sort uses
 *  ("winner" and not "round"). A Round Leader or Top-N curve may not be drawn
 *  under a "Win Probability" heading (#955). */
export function isGolfWinnerQuestion(name: string | null | undefined): boolean {
  if (!name) return false;
  return /\bwinner\b/i.test(name) && !/\bround\b/i.test(name);
}

/** The ids the chart may walk, in the backend's order. When the names line up,
 *  only Winner questions; when there are none (or no names), the list unchanged. */
export function winnerChartCandidates(
  marketIds: number[],
  marketNames: string[] | null | undefined,
): number[] {
  if (!marketNames || marketNames.length !== marketIds.length) return marketIds;
  const winners = marketIds.filter((_, i) => isGolfWinnerQuestion(marketNames[i]));
  return winners.length > 0 ? winners : marketIds;
}

/** The chart's own drawability test (`FuturesChart`: at least 2 priced points and
 *  more than one moment in time), asked before the chart is committed to. */
export function isDrawableHistory(data: Pick<FuturesHistoryResponse, "outcomes">): boolean {
  let points = 0;
  const times = new Set<number>();
  for (const outcome of data.outcomes ?? []) {
    for (const point of outcome.history ?? []) {
      if (point.probability === null || point.probability === undefined) continue;
      const t = new Date(point.timestamp).getTime();
      if (Number.isNaN(t)) continue;
      points += 1;
      times.add(t);
    }
  }
  return points >= 2 && times.size >= 2;
}
