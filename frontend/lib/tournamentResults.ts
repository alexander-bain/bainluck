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
import { renderedDuelPercents } from "./renderedPercent";

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
  /** Winner's games first, set by set. `null` for a walkover. */
  score: string | null;
  /**
   * HOW it ended (UX-P147) — `final`, `retired`, `walkover`, `abandoned` or
   * `unknown`, from ESPN's own `status.type.name`.
   *
   * Optional so a cached payload from before this field existed still renders;
   * `resultScoreLine` treats a missing value exactly like `unknown`, which
   * reproduces the old wording rather than inventing a completion.
   */
  completion?: string | null;
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
  /** Finished with no set played at all (UX-P147). Optional on old payloads. */
  source_walkovers?: number;
  /** Finished mid-match, so the score is real but partial (UX-P147). */
  source_retirements?: number;
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
export function formatPrematch(
  probability: number | null | undefined,
  rendered?: number | null
): string | null {
  if (typeof probability !== "number" || !Number.isFinite(probability)) return null;
  return formatProbabilityPercent(probability, { rendered });
}

/**
 * ═══ UX-P147, ALEX'S ITEM 4: THE TWO PRIORS MUST SUM TO 100 ═══
 *
 * On the UX-P146 artifact he read four rows off the finished list — 74/27,
 * 40/61, 60/41, 67/34 — every one of them 101, and asked whether the
 * underlying pair is normalized at all.
 *
 * **It is.** `_prematch_by_pair` runs the same `normalize_pair` a live row
 * uses, and the shipped payload proves it: the four pairs he named arrive as
 * `0.735/0.265`, `0.395/0.605`, `0.595/0.405`, `0.665/0.335` — exactly 1.000,
 * to the last place, all twelve rows. Nothing upstream is wrong.
 *
 * The 101 is made HERE, at the last step, and it is the oldest arithmetic
 * defect in the product: a normalized pair on a half-cent grid puts BOTH sides
 * on a `.5` boundary at once, and half-up rounds both of them UP. `73.5 → 74`
 * and `26.5 → 27`. Two individually-correct numbers, one impossible card.
 *
 * This is #2060's defect exactly, and it already has a home — so this rounds
 * the pair through `renderedDuelPercents` rather than growing a seventh
 * private copy of the rule. That function normalizes by the true total, rounds
 * the FAVOURITE once, and DERIVES the other as `100 − favourite`; the pair
 * cannot sum to anything but 100 because only one number was ever rounded.
 *
 * Returns integers by `entity_key`. A player with no prior is absent from the
 * map, and a row where only one side carries a prior falls through
 * `renderedDuelPercents`' non-pair branch untouched — there is no complement
 * to derive from, and inventing one would be worse than the 101 was.
 */
export function prematchPercents(
  result: TournamentResult
): Record<string, number | null> {
  const players = result.players ?? [];
  const out: Record<string, number | null> = {};
  if (players.length !== 2) {
    for (const player of players) {
      const p = player.prematch_probability;
      out[player.entity_key] =
        typeof p === "number" && Number.isFinite(p) ? Math.round(p * 100) : null;
    }
    return out;
  }
  const [first, second] = players;
  const [firstPct, secondPct] = renderedDuelPercents(
    first.prematch_probability,
    second.prematch_probability
  );
  out[first.entity_key] = firstPct;
  out[second.entity_key] = secondPct;
  return out;
}

/**
 * What the score column says, and what KIND of thing it is saying (UX-P147).
 *
 * ═══ ALEX'S ITEM 5: THE "no score" ROW ═══
 *
 * He pointed at the Dimitrov qualifying final printing **no score** and asked
 * for the root cause — ingest gap or render fallback. It is neither. ESPN
 * carries that fixture as `STATUS_WALKOVER` with the note "Grigor Dimitrov
 * (BUL) bt Otto Virtanen (FIN) w/o" and no line scores on either competitor,
 * because Virtanen withdrew before a ball was struck. There is no score to
 * have ingested, and `format_score` was right to return nothing.
 *
 * What was wrong is what the page then SAID. "no score" describes our data
 * rather than the tournament, and its tooltip guessed "usually a retirement" —
 * a guess, about the one row on the page where the source had already told us
 * the answer in as many words. A reader deserves the fact: **walkover**.
 *
 * ═══ AND THE EIGHT ROWS NOBODY HAD LOOKED AT ═══
 *
 * The same census found the mirror-image defect. A RETIREMENT reports equal
 * set counts (ESPN fills the abandoned set in on both sides), so it sails
 * through `format_score` and printed as an ordinary final score: Lajovic beat
 * Kwon `4-6, 7-5, 3-1`, which is not a scoreline a completed tennis match can
 * have. Eight rows, all of them silently claiming a match ran its course.
 *
 * The score is not suppressed — it is true, and it is most of what happened.
 * It is MARKED. `ret.` is the marker the sport itself uses.
 *
 * `kind` is returned beside the text so the component can style a fact
 * (`walkover`) differently from an absence (`unknown`) without matching on
 * English, and so a guard can assert the branch rather than the wording.
 */
export type ScoreLineKind = "score" | "retired" | "walkover" | "absent";

export function resultScoreLine(result: TournamentResult): {
  text: string;
  kind: ScoreLineKind;
  /** The sentence a screen reader and a tooltip get. Always a full one. */
  explanation: string;
} {
  const completion = result.completion ?? null;
  const score = result.score;

  if (completion === "walkover") {
    return {
      text: "walkover",
      kind: "walkover",
      explanation:
        "A walkover — the loser withdrew before the match started, so no set was played.",
    };
  }
  if (score && completion === "retired") {
    return {
      text: `${score} ret.`,
      kind: "retired",
      explanation: `${score}, when the loser retired. The match did not run its course, so the last set is unfinished.`,
    };
  }
  if (score) {
    return {
      text: score,
      kind: "score",
      explanation: `${score}, winner's games first.`,
    };
  }
  // Genuinely unaccounted for: a finished competition with no line scores and
  // no status we recognise. Kept as its own branch rather than folded into
  // "walkover", because guessing here is the defect this whole function exists
  // to remove — a wrong reason reads more authoritative than no reason.
  return {
    text: "no score",
    kind: "absent",
    explanation:
      "The source reported a winner but no set scores, and did not say why.",
  };
}

/**
 * The provenance clause about matches that did not run their course, or `null`
 * when every rendered row is an ordinary completed match (UX-P147).
 *
 * Counted over THIS draw's rendered rows, for the same reason `prematchCoverage`
 * is: the payload's `source_walkovers` is the all-draws total, and a sentence
 * about a different list is a wrong sentence with a real number in it.
 *
 * It replaces `"N finished without a completed set score (retirement or
 * walkover)"` — a clause that hedged between two possibilities the source had
 * already distinguished, and that counted only the walkovers while the
 * retirements it named were sitting above it printed as ordinary results.
 */
export function completionNote(matches: TournamentResult[]): string | null {
  const walkovers = matches.filter((m) => m.completion === "walkover").length;
  const retirements = matches.filter((m) => m.completion === "retired").length;
  const clauses: string[] = [];
  if (retirements > 0) {
    clauses.push(
      `${retirements} ended in a retirement, so ${
        retirements === 1 ? "its score is" : "those scores are"
      } marked ret. and the last set is unfinished`
    );
  }
  if (walkovers > 0) {
    clauses.push(
      `${walkovers} ${walkovers === 1 ? "was a walkover" : "were walkovers"}, with no set played`
    );
  }
  if (clauses.length === 0) return null;
  return `${clauses.join("; ")}.`;
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
