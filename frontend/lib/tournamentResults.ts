/**
 * DECIDED MATCHES, WITH THE SCORE (UX-P139, Alex's item 9).
 *
 *     "Decided-match scores come from the ESPN API we already use for other
 *     scores — wire it; 'no data behind it' is not accepted."
 *
 * UX-P138 declared `winner_entity_key` and `score`, rendered them when filled,
 * and had nothing to fill them with. This is the read side of the fill. The
 * data comes from ESPN's tennis scoreboard, which carries the US Open with
 * per-set line scores and a winner flag, grouped by slugs that ARE the
 * register's own draw names — see `backend/app/services/espn_tennis.py`.
 *
 * ═══ WHY RESULTS ARE THEIR OWN SECTION AND NOT A FLAG ON THE MATCH LIST ═══
 *
 * `build_slate` drops a matchup the moment it starts, deliberately: the
 * register is a committed file, the clock is not, and a slate still showing
 * this morning's matches at midnight is the defect that rule prevents. So a
 * finished match was never a slate row, which is the real reason UX-P138's
 * score seam rendered nothing — it was attached to a list that structurally
 * cannot contain a finished match.
 *
 * ═══ ITEM 12: DOUBLES ═══
 *
 *     "Doubles/mixed-doubles markets: the measurement lane is cataloging what
 *     Polymarket carried for US Open 2025 — build the section to accept those
 *     market classes when the catalog lands."
 *
 * `DRAW_ORDER` below carries all five draws, and every consumer groups by it
 * rather than by a two-element singles list. Censused 2026-08-26: **zero** US
 * Open doubles markets exist at either source (3,581 markets platform-wide
 * match "doubles", none of them this tournament), so the two doubles sections
 * and the mixed section are empty today and will populate with no code change
 * the moment the register carries them. The RESULTS for all three are already
 * live in the ESPN feed — 63 men's, 63 women's, 21 mixed competitions — so the
 * section has something true to show before it has anything priced.
 */

import { formatProbabilityPercent } from "./probabilityDisplay";

export interface ResultPlayer {
  entity_key: string;
  display_name: string;
  seed: number | null;
  is_winner: boolean;
  /**
   * What the market gave this player BEFORE the match (UX-P146), 0-1, or
   * `null` where no match market was ever registered for the pair.
   *
   * The opening quote, normalized against its own pair — see
   * `_prematch_by_pair` in `tournament_slate.py` for why the opening and not
   * the last one we saw.
   */
  prematch_probability: number | null;
}

export interface TournamentResult {
  matchup_key: string;
  draw: string;
  draw_label: string;
  round: string;
  players: ResultPlayer[];
  winner_entity_key: string;
  /** Winner's games first, set by set. `null` for a retirement. */
  score: string | null;
  completed_at: string | null;
  /** ESPN's own round wording — finer than ours, kept beside it. */
  source_round: string | null;
  source: string;
}

export interface TournamentResults {
  matches: TournamentResult[];
  count: number;
  /**
   * Finished matches at this tournament whose two players the register does
   * not both carry — a COVERAGE fact, and most of the qualifying draw by
   * design. Distinct from `winner_not_registered`, which is a join problem.
   */
  unregistered_pairs: number;
  winner_not_registered: number;
  source_competitions: number;
  source_scored: number;
  source_errors: string[];
  /** How many `matches` carry a pre-match probability (UX-P146). */
  with_prematch?: number;
}

/**
 * Every draw the tournament can have, in the order a page shows them.
 *
 * Singles first because that is what the markets price; doubles after, ready
 * (item 12). A list rather than a pair, so adding a market class is a register
 * change and not a component change.
 */
export const DRAW_ORDER = [
  "mens-singles",
  "womens-singles",
  "mens-doubles",
  "womens-doubles",
  "mixed-doubles",
] as const;

export const DRAW_LABELS: Record<string, string> = {
  "mens-singles": "Men's Singles",
  "womens-singles": "Women's Singles",
  "mens-doubles": "Men's Doubles",
  "womens-doubles": "Women's Doubles",
  "mixed-doubles": "Mixed Doubles",
};

/** Is this draw one the page currently prices, or one it is only ready for? */
export function drawIsPriced(draw: string): boolean {
  return draw === "mens-singles" || draw === "womens-singles";
}

export function resultsForDraw(
  results: TournamentResults | null | undefined,
  draw: string
): TournamentResult[] {
  return (results?.matches ?? []).filter((match) => match.draw === draw);
}

/**
 * `Fearnley beat Carballes Baena 7-6, 6-3` — the sentence a result is.
 *
 * Winner first, and the score winner-first too, so the reader never has to
 * reverse anything in their head. A missing score does not suppress the
 * sentence: knowing who won is most of the value, and "we have the result but
 * not the score" is an honest thing to show.
 */
export function resultSentence(result: TournamentResult): string {
  const winner = result.players.find((p) => p.is_winner);
  const loser = result.players.find((p) => !p.is_winner);
  if (!winner || !loser) return "";
  const surnameOf = (name: string) => name.split(" ").slice(1).join(" ") || name;
  const head = `${surnameOf(winner.display_name)} beat ${surnameOf(loser.display_name)}`;
  return result.score ? `${head} ${result.score}` : head;
}

/**
 * Round headings, coarse to fine.
 *
 * `source_round` is ESPN's ("Qualifying 1st Round"); `round` is the register's
 * ("qualifying"), which buckets all three qualifying rounds together because
 * the MARKETS do not distinguish them. The finer one is shown when it exists,
 * because a reader looking at results wants the round and only the register
 * needs the bucket.
 */
export function roundHeading(result: TournamentResult): string {
  if (result.source_round) return result.source_round;
  return ROUND_HEADINGS[result.round] ?? result.round;
}

export const ROUND_HEADINGS: Record<string, string> = {
  qualifying: "Qualifying",
  R128: "First round",
  R64: "Second round",
  R32: "Third round",
  R16: "Round of 16",
  QF: "Quarter-finals",
  SF: "Semi-finals",
  F: "Final",
};

/**
 * The prior, as a percentage — `0.495` -> `"50%"`, `null` -> `null`.
 *
 * ═══ UX-P146: WHY A FINISHED MATCH PRINTS A NUMBER AT ALL ═══
 *
 * Alex, on the UX-P145 artifact: "a result without the prior probability is
 * half the story on a probability product." He is right, and the men's
 * qualifying second round on 2026-08-26 is the argument: Alexandra Shubladze
 * went in at 65% and lost; Colton Smith went in at 40% and won. Without the
 * prior both rows read as "somebody beat somebody".
 *
 * WHOLE PERCENTAGES, no decimal. The board uses `formatBoardProbability` and
 * carries a decimal on tight numbers because it is a LIVE figure a reader may
 * watch move. This one is settled history; a tenth of a point on a number that
 * will never change again is precision for its own sake.
 *
 * THROUGH `formatProbabilityPercent`, and not a local `Math.round(p * 100)`.
 * UX-P046 made that boundary one module's job — a 0.4% prior printed as `0%`
 * tells a reader the market called it impossible, which it never did — and the
 * anti-drift guard in `probabilityDisplay.test.ts` fails on a seventh private
 * copy. This is the ONLY thing this wrapper adds to it: `null` in, `null` out,
 * so the caller can distinguish "no market" from "a market that said nothing".
 */
export function formatPrematch(probability: number | null | undefined): string | null {
  if (typeof probability !== "number" || !Number.isFinite(probability)) return null;
  return formatProbabilityPercent(probability);
}

/** How many of these results carry a prior — the ratio the section states. */
export function prematchCoverage(
  matches: TournamentResult[]
): { withPrior: number; total: number } {
  return {
    withPrior: matches.filter((match) =>
      match.players.some((player) => typeof player.prematch_probability === "number")
    ).length,
    total: matches.length,
  };
}

/** Newest first — a results list is read from the top for what just happened. */
export function sortedResults(matches: TournamentResult[]): TournamentResult[] {
  return [...matches].sort((a, b) =>
    String(b.completed_at ?? "").localeCompare(String(a.completed_at ?? ""))
  );
}

/**
 * The sentence a results section owes when it has nothing, or `null`.
 *
 * Three genuinely different empties, and they need different words. A source
 * error is OUR problem; results that exist for matches we never registered is a
 * COVERAGE problem; nothing having finished is just the schedule.
 */
export function resultsEmptyReason(
  results: TournamentResults | null | undefined
): string | null {
  if (!results) return "Results are not loaded.";
  if (results.matches.length > 0) return null;
  if (results.source_errors.length > 0) {
    return "We could not reach the results feed just now. Nothing here is missing on purpose.";
  }
  if (results.source_competitions > 0) {
    return `${results.source_competitions} matches have finished at this tournament. None of them involve two players we hold markets for.`;
  }
  return "No match has finished yet.";
}
