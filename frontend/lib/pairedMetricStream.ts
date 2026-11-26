/**
 * #10090: Market-ID extraction for server-blended PairedMetricSet cards
 * (`AwardCategoryPairedCard`, Oscars hub/concept, and `paired_stage_bars`
 * machinery sections).
 *
 * Strictly enforces `visualForms.ts` Rule #1: equivalent venue legs (`stage_1`
 * Kalshi + `companion_polymarket_id`, etc.) are NEVER blended in the browser.
 * Live stream invalidations trigger an authoritative server refresh instead.
 */
import type { PairedMetricSet } from '@/lib/discover/visualForms';

export function pairedMetricSetMarketIds(sets: readonly PairedMetricSet[]): number[] {
  const ids = new Set<number>();
  for (const ps of sets) {
    if (!ps.stage_1_settled) {
      if (typeof ps.stage_1_market?.id === 'number' && ps.stage_1_market.id > 0) {
        ids.add(ps.stage_1_market.id);
      }
      if (
        typeof ps.stage_1_market?.companion_polymarket_id === 'number' &&
        ps.stage_1_market.companion_polymarket_id > 0
      ) {
        ids.add(ps.stage_1_market.companion_polymarket_id);
      }
    }
    if (!ps.stage_2_settled && typeof ps.stage_2_market?.id === 'number' && ps.stage_2_market.id > 0) {
      ids.add(ps.stage_2_market.id);
    }
  }
  return [...ids];
}
