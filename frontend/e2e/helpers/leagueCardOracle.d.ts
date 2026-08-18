/** UX-P087 (#1860) — see `leagueCardOracle.js` for why this is a restatement. */

export interface OracleOutcome {
  name?: string | null;
}

export interface OracleMarket {
  id?: number;
  name?: string;
  top_outcomes?: OracleOutcome[] | null;
}

export interface LeaguePayloadBody {
  sections?: Record<string, OracleMarket[]> | null;
  markets?: OracleMarket[] | null;
  upcoming_games?: unknown[] | null;
  recent_results?: unknown[] | null;
}

/** One question with one answer: 1–2 outcomes drawn from {Yes, No}, both when 2. */
export function isBinary(market: OracleMarket): boolean;

/** One question at 3+ dated thresholds; EVERY outcome must parse. */
export function isDateLadder(market: OracleMarket): boolean;

/** Flatten the `sections` mapping. THROWS on a shape it cannot read. */
export function leagueMarkets(body: LeaguePayloadBody): OracleMarket[];

/** How many of each ruled shape the page owes for this payload. */
export function leagueOwed(body: LeaguePayloadBody): {
  binaries: number;
  ladders: number;
  games: number;
};
