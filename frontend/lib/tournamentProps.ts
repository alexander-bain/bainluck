/**
 * Curated tournament props and futures (UX-P132 re-skin, Alex's item 5).
 *
 * "Beyond the two winner markets and today's matches, surface a section of
 * interesting tournament props/futures — curated, not a dump."
 *
 * The curation lives in the REGISTER, not here and not at request time. Same
 * doctrine as every other row on this page: a market not in the register does
 * not render. That is what makes "curated, not a dump" a structural property
 * rather than a promise — there is no code path that could surface an
 * uncurated market, because the page never asks the database what exists.
 *
 * The interestingness bar is applied by the agent when the register is written.
 * A prop earns its place by being a question a person would actually ask about
 * this tournament — "can Sinner complete the calendar slam" — not by having
 * volume.
 */

export type PriceState = "live" | "stale" | "dark";

export interface PropOutcome {
  entity_key: string;
  display_name: string;
  probability: number | null;
  /**
   * THIS outcome's own freshness, not the card's (UX-P135). The old rule let
   * one outcome refreshed an hour ago mark a twenty-day-old answer live.
   */
  probability_is_live: boolean;
  observed_at: string | null;
  age_hours: number | null;
  price_state: PriceState;
  /** Does this outcome answer the card's question? Curated, never inferred. */
  is_answer: boolean;
}

export interface PropMarket {
  key: string;
  /** The question, phrased as a person would ask it. */
  title: string;
  /** Why it is interesting — one clause, or null. Never an LLM hook. */
  hook: string | null;
  draw: string | null;
  source: string;
  outcomes: PropOutcome[];
  /**
   * The outcome whose probability answers `title`, or `null` for a field
   * market where no single outcome does. `null` is a supported state, not a
   * missing value: it selects the ranked-list rendering.
   */
  answer_entity_key: string | null;
  /** The AND over the card's PRICED outcomes — a ranked field is published too. */
  price_state: PriceState;
  observed_at: string | null;
  age_hours: number | null;
  freshest_observed_at: string | null;
  freshest_age_hours: number | null;
  /** Entity keys of priced outcomes that are not live. */
  stale_outcomes: string[];
  mixed_freshness: boolean;
}

/**
 * Props for the selected draw, plus the tournament-wide ones.
 *
 * A prop with `draw: null` belongs to the whole tournament and shows under
 * both pills — hiding "who wins the calendar slam" from the women's tab
 * because it was filed as tournament-wide would be a filter bug that looks
 * like a curation decision.
 */
export function propsForDraw(markets: PropMarket[], draw: string): PropMarket[] {
  return markets.filter((market) => market.draw === null || market.draw === draw);
}

/**
 * The outcome whose number the card prints as its headline.
 *
 * REPLACES `leadingOutcome`, which took the highest-probability outcome and
 * was wrong in the most dangerous possible way. The props census measured it:
 * "Can Sinner complete the calendar slam?" is backed by a Kalshi threshold
 * ladder whose outcomes are `1+ / 2+ / 3+ Grand Slam wins`. The max is `1+` at
 * 99%, so the card printed **99%** under a question whose real answer is
 * ~1%. The number was true of *something*; it just was not an answer to the
 * question printed above it, which is the worst kind of wrong because it reads
 * as authoritative.
 *
 * Now the register names the answer and this function only looks it up. A
 * market with no named answer returns `null` — the caller must then rank
 * rather than invent a headline.
 */
export function answerOutcome(market: PropMarket): PropOutcome | null {
  if (market.answer_entity_key === null) return null;
  return (
    market.outcomes.find(
      (outcome) => outcome.entity_key === market.answer_entity_key
    ) ?? null
  );
}

/**
 * A field market's outcomes, best first — the rendering for a question no
 * single outcome answers. Unpriced outcomes are dropped from the ranking
 * because there is nothing to rank them by, not hidden as a judgement.
 */
export function rankedOutcomes(market: PropMarket): PropOutcome[] {
  return market.outcomes
    .filter((outcome) => outcome.probability !== null)
    .sort((a, b) => (b.probability as number) - (a.probability as number));
}

export function formatPropProbability(probability: number | null): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return `${Math.round(probability * 100)}%`;
}
