/**
 * Advance-to-stage markets, for a round nobody has reached (UX-P137, ruling 4).
 *
 * "A future round with markets on reaching it is content, not emptiness."
 *
 * UX-P136 replaced sixteen identical empty cards with one honest sentence,
 * which was right as far as it went and still left the Quarter-finals chip
 * opening onto a paragraph. It was never empty: the register carries EIGHT
 * curated "Does <player> reach the <round>?" markets, priced, sitting one tab
 * away in a section the reader has to scroll to. The round the reader just
 * asked about is the best possible place for them.
 *
 * THE PATTERN IS BORROWED, and the report says from where. Alex recalled the
 * Masters doing this; it does not — `lib/golfRelatedSections.ts` buckets golf
 * props into labelled sections and has no notion of a stage. The MLB/NBA
 * playoff table is `components/ProgressionLadder.tsx` (fed by
 * `playoff_progression`, rendered on the feed and `/my-stuff`), and its row
 * grammar is what gets reused: dot, stage name, mini bar, percentage. Not the
 * component itself — it pulls framer-motion and fires Wikipedia image lookups,
 * which a tennis round view does not want and the static capture rig cannot
 * run.
 *
 * The mapping is by explicit suffix, never by fuzzy match. A prop whose round
 * cannot be read returns `null` and is simply not shown: a market filed under
 * the wrong round is worse than one filed under none, because it renders as a
 * confident answer to a question nobody asked.
 */

import { ROUND_LABELS, type RoundName } from "./bracket";
import { answerOutcome, type PropMarket } from "./tournamentProps";

/**
 * Curated key suffix -> the round the market is about.
 *
 * Ordered longest-first so `round-of-16` is tested before any shorter token
 * could claim it. Keys come from the register and are written by hand, so this
 * is a closed set, not a heuristic over free text.
 */
const ROUND_SUFFIXES: { suffix: string; round: RoundName }[] = [
  { suffix: "round-of-128", round: "R128" },
  { suffix: "round-of-64", round: "R64" },
  { suffix: "round-of-32", round: "R32" },
  { suffix: "round-of-16", round: "R16" },
  { suffix: "quarterfinals", round: "QF" },
  { suffix: "quarter-finals", round: "QF" },
  { suffix: "semifinals", round: "SF" },
  { suffix: "semi-finals", round: "SF" },
  { suffix: "final", round: "F" },
];

/**
 * Which round a curated prop is about reaching, or `null`.
 *
 * `null` for every prop that is not an advance-to-stage market at all — "Will
 * Sinner actually play?" and "Can Alcaraz win a second major this year?" are
 * both curated, both good, and neither belongs in a round view.
 */
export function advanceRound(market: PropMarket): RoundName | null {
  const key = (market.key ?? "").toLowerCase();
  for (const entry of ROUND_SUFFIXES) {
    if (key.endsWith(`-${entry.suffix}`)) return entry.round;
  }
  return null;
}

export interface AdvanceEntry {
  key: string;
  /** The player, not the question — the round is already the column header. */
  displayName: string;
  probability: number;
  isLive: boolean;
}

/**
 * The player's name, recovered from the curated question.
 *
 * The card's title is the question ("Does Alcaraz reach the semifinals?"); in
 * a table whose header already says "To reach the semi-finals", repeating the
 * round in every row is noise. Falls back to the whole title if the shape is
 * not the expected one, because a slightly long row beats a blank one.
 */
export function advanceSubject(market: PropMarket): string {
  const match = /^Does\s+(.+?)\s+reach\b/i.exec(market.title ?? "");
  return match ? match[1] : (market.title ?? "");
}

/**
 * Priced advance-to-stage markets for one round and draw, best first.
 *
 * Unpriced markets are dropped rather than listed at zero: a market with no
 * reading has no place in a ranking, and rendering it at the bottom would read
 * as "the market thinks this is impossible".
 */
export function advanceMarketsForRound(
  markets: PropMarket[],
  round: RoundName,
  draw: string
): AdvanceEntry[] {
  return markets
    .filter((market) => market.draw === null || market.draw === draw)
    .filter((market) => advanceRound(market) === round)
    .map((market) => {
      const answer = answerOutcome(market);
      if (answer === null || answer.probability === null) return null;
      return {
        key: market.key,
        displayName: advanceSubject(market),
        probability: answer.probability,
        isLive: answer.probability_is_live === true,
      };
    })
    .filter((entry): entry is AdvanceEntry => entry !== null)
    .sort((a, b) => b.probability - a.probability);
}

/** Every round this draw has priced advance markets for — for the report and tests. */
export function roundsWithAdvanceMarkets(
  markets: PropMarket[],
  draw: string
): RoundName[] {
  const seen = new Set<RoundName>();
  for (const round of Object.keys(ROUND_LABELS) as RoundName[]) {
    if (advanceMarketsForRound(markets, round, draw).length > 0) seen.add(round);
  }
  return [...seen];
}
