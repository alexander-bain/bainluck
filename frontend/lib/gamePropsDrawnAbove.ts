/**
 * #8596: ONE MARKET, ONE PLACE ON THE EVENT PAGE.
 *
 * Additional Markets (`SpecialEventMarkets`, from `/game-markets` → `other`) and
 * Bigger Picture's game props (`RelatedFutures`, from `/related-futures`) can
 * carry the same market. On `/events/15318549` (Cubs @ Red Sox, 2026-09-25)
 * "Will there be a run scored in the first inning?" (market 62308451) printed
 * in both, at the same price, one section apart. Bigger Picture's `hasGameMarkets`
 * gate counts only totals / player props / team totals, so an `other`-only game
 * never tripped it.
 *
 * The ids come from `buildMarketSection`, the builder Additional Markets renders
 * from, and only from cards it actually draws. So the lower section stands down
 * for exactly the markets shown above it, and a market Additional Markets drops
 * (the hero's own moneyline, a market-map rung) keeps its only other copy.
 */
import type { GameMarketsResponse } from "@/lib/api";
import { buildMarketSection, type MarketSectionOptions } from "@/lib/otherMarketGroups";

/**
 * The event page mounts Additional Markets at this many `other` rows.
 *
 * #9633: this was 3, a count of WIRE ROWS, while one yes/no question is two
 * rows. `/events/15320530` (Tomic v Sun) served exactly one extra market, Set 1
 * Winner, and the page drew no section for it. #5540 had already dropped
 * `buildMarketSection`'s own floor for this case; the page gate never followed.
 * Any row is enough now: the builder decides what it draws, and
 * `SpecialEventMarkets` returns null when that is nothing (the hero's own
 * moneyline, a market-map rung).
 */
export const SPECIAL_MARKETS_MIN_WIRE_ROWS = 1;

export function specialMarketsDrawnIds(
  gameMarkets: Pick<GameMarketsResponse, "other" | "home_team" | "away_team"> | null | undefined,
  options: MarketSectionOptions = {},
): number[] {
  const other = gameMarkets?.other;
  if (!other || other.length < SPECIAL_MARKETS_MIN_WIRE_ROWS) return [];
  return buildMarketSection(other, {
    homeTeam: gameMarkets?.home_team,
    awayTeam: gameMarkets?.away_team,
    ...options,
  }).drawnMarketIds;
}

/** Drop the game props whose market is already drawn by Additional Markets. */
export function withoutGamePropsDrawnAbove<T extends { market_id: number }>(
  statProps: T[],
  drawnIds: readonly number[] | undefined,
): T[] {
  if (!drawnIds || drawnIds.length === 0) return statProps;
  const drawn = new Set(drawnIds);
  return statProps.filter((f) => !drawn.has(f.market_id));
}
