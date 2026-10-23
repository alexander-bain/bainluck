/**
 * #11493 — is this leg of a still-open FIELD market one the venue has already
 * knocked out?
 *
 * Production 2026-10-23 09:37Z, `/search?q=Brewers`: the "MLB World Series
 * Champion 2026" card (polymarket 114584, `status: "open"`) printed Astros 1%,
 * D-backs 1% and Yankees <1%. All three are out of the playoffs and the payload
 * already says so: each leg is served `is_winner: false` +
 * `resolution_source: "api_settlement"`, while the two clubs still playing
 * (Brewers 0.64, Rays 0.3655) carry `resolution_source: null`.
 *
 * `outcomeRowVerdict` deliberately answers only the `won` arm on an open market
 * (#6082 / #8640) and this does NOT widen it: every other surface sharing that
 * rule keeps its answer. A caller opts in, today only Search's futures cards.
 *
 * The test is the backend's `_outcome_is_settled` (`routes/league_futures.py`),
 * which already renders an open market's authoritative loser as settled:
 *   - the retraction (`ungradeable_result`) earns nothing — it is outside the
 *     tier-3 set, as are a served null, an absent source and the guess family;
 *   - a leg the book still prices as a live contender (>= 0.20, the backend's
 *     `_TERMINAL_LOSER_CEILING`) keeps its price, so a defaulted or residue
 *     `false` (#4597) cannot pull a live contender off the card;
 *   - only a ranked field reads "Out". A ladder rung or a Yes/No side graded
 *     false is not a contender eliminated, and keeps today's render.
 */

import type { FuturesMarket } from "@/lib/types";
import { SHAPE_FIELD } from "@/lib/marketShape";
import { isAuthoritativeResolution } from "@/lib/resolutionAuthority";

/** Mirror of `_TERMINAL_LOSER_CEILING` in `routes/league_futures.py`. */
export const TERMINAL_LOSER_CEILING = 0.2;

export interface OpenFieldLeg {
  probability?: number | null;
  is_winner?: boolean | null;
  resolution_source?: string | null;
}

export function openFieldLegIsOut(
  market: Pick<FuturesMarket, "status" | "market_type">,
  leg: OpenFieldLeg,
): boolean {
  if (market.status !== "open") return false;
  if (market.market_type !== SHAPE_FIELD) return false;
  if (leg.is_winner !== false) return false;
  if (!isAuthoritativeResolution(leg.resolution_source)) return false;
  return leg.probability == null || leg.probability < TERMINAL_LOSER_CEILING;
}
