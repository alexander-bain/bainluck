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
  probability_is_live: boolean;
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
  price_state: PriceState;
  observed_at: string | null;
  age_hours: number | null;
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

/** The leading outcome, for the collapsed one-line summary. */
export function leadingOutcome(market: PropMarket): PropOutcome | null {
  const priced = market.outcomes.filter((outcome) => outcome.probability !== null);
  if (priced.length === 0) return null;
  return priced.reduce((best, outcome) =>
    (outcome.probability as number) > (best.probability as number) ? outcome : best
  );
}

export function formatPropProbability(probability: number | null): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return `${Math.round(probability * 100)}%`;
}
