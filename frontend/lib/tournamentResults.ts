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

import { ROUND_LABELS, ROUND_NAMES, type RoundName } from "./bracket";
import { formatProbabilityPercent } from "./probabilityDisplay";
import { renderedDuelPercents } from "./renderedPercent";
import type { PlayerImage } from "./slate";
import { matchupEventHref, type MatchupEventIds } from "./tournamentEventLink";

export interface ResultPlayer {
  entity_key: string;
  display_name: string;
  seed: number | null;
  is_winner: boolean;
  /**
   * The register-pinned face + flag (ruling 8, wired here by UX-P206).
   *
   * The SAME block `build_slate` puts on a live row and `build_board` puts on
   * a contender — one pin per player, read by `player_image`, so the person
   * who was on the page an hour ago is the same person in the result. Optional
   * so a payload cached from before the field existed still renders: the
   * avatar falls through to initials rather than throwing.
   */
  image?: PlayerImage | null;
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
  /**
   * Ruling 8's coverage gate, counted in PLAYER SLOTS (`2 * count`), not rows
   * (UX-P206). `player_slots - with_face - with_flag` is the initials tail.
   * Optional on payloads cached from before the fields existed.
   */
  player_slots?: number;
  with_face?: number;
  with_flag?: number;
}

/**
 * Ruling 8's gate, computed rather than remembered (UX-P206).
 *
 * Alex: *"enable ONLY if coverage is ~complete per draw — half-covered looks
 * worse than none."* The thing the gate is about is whether the COLUMN is
 * uniform, and a flag makes it uniform exactly as a face does — that is the
 * whole reason `PlayerAvatar` has a flag step. So the fraction that matters is
 * any-image, not face.
 *
 * Returns `null` when the payload does not carry the counts (an old cache), so
 * a caller can tell "not measured" from "measured at zero" — gotcha #53.
 */
export function resultsImageCoverage(
  results: TournamentResults | null | undefined
): { slots: number; withImage: number; withFace: number; fraction: number } | null {
  const slots = results?.player_slots;
  if (typeof slots !== "number" || slots <= 0) return null;
  const withFace = results?.with_face ?? 0;
  const withImage = withFace + (results?.with_flag ?? 0);
  return { slots, withImage, withFace, fraction: withImage / slots };
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
 * ═══ ONE TOURNAMENT, ONE NAME PER ROUND (#2449) ═══
 *
 * Alex, on `/tournaments/us-open`: *"the left column header reads `ROUND OF
 * 128` while every row in the Finished list reads `ROUND 1`. Same round, two
 * names, one screen."*
 *
 * He was reading two vocabularies at once, and the page had three:
 *
 *   - **the register's**, `R128` → `Round of 128` (`ROUND_LABELS`), which the
 *     round pills, the match-list heading, the bracket and the playoff grid all
 *     speak, because the register is this tournament's ladder;
 *   - **ESPN's**, `Round 1`, which arrives on every results row as
 *     `source_round` and — measured on the live payload 2026-09-01 — as
 *     `round` too, since `build_results` sets both from `espn_round`;
 *   - **this table's own**, which used to say `First round` for `R128` and was
 *     a third name for the same thing that nothing on the page ever printed,
 *     because `source_round` always won the branch above it.
 *
 * The register's is the one that survives. It is not a preference: the pills,
 * the grid columns and the bracket are structural surfaces keyed on `RoundName`
 * and they cannot speak ESPN's ordinal without inventing a mapping in four more
 * places. So the results list translates INTO the register's vocabulary here,
 * once, and everything downstream of `roundHeading` is consistent by
 * construction.
 *
 * ### What is kept, and why it is not a second vocabulary
 *
 * `Qualifying 1st Round` / `2nd Round` / `Final` pass through verbatim. The
 * register buckets all three as `qualifying` because the MARKETS do not
 * distinguish them, so ESPN's is strictly finer information and the pill's
 * `Qualifying` visibly CONTAINS it. That is a refinement a reader resolves
 * without being told. `Round 1` beside `Round of 128` is not — the two names
 * share no token and neither contains the other.
 *
 * ### The one assumption, stated
 *
 * ESPN's late rounds name themselves (`Round of 16`, `Quarterfinals`,
 * `Semifinals`, `Final`) and need no anchor. Its early rounds are ORDINALS, and
 * an ordinal only resolves against a known ladder length: `Round 1` is the
 * round of 128 in a 128-draw and the round of 32 in a 32-draw.
 *
 * `roundCount` is therefore a parameter, anchored at the END of `ROUND_NAMES`
 * exactly as `buildBracket` anchors the fold — the final is always the last
 * round, so a shorter draw starts further in. When the caller does not know it,
 * it defaults to the full 7-round ladder, which is not a new assumption: it is
 * the same one `MATCH_ROUND_LABELS`, the pill strip and the grid already make
 * on this page, and a Grand Slam singles draw is 128 by definition.
 *
 * Anything unrecognised passes through VERBATIM rather than being guessed into
 * a round. A wrong round heading on a finished match is worse than ESPN's own
 * words, and silence is not available — the row has to say something.
 */

/** ESPN's self-naming rounds. No ladder length needed to resolve these. */
const ESPN_NAMED_ROUNDS: Record<string, RoundName> = {
  "round of 128": "R128",
  "round of 64": "R64",
  "round of 32": "R32",
  "round of 16": "R16",
  quarterfinal: "QF",
  quarterfinals: "QF",
  "quarter-final": "QF",
  "quarter-finals": "QF",
  semifinal: "SF",
  semifinals: "SF",
  "semi-final": "SF",
  "semi-finals": "SF",
  final: "F",
  championship: "F",
};

/**
 * The register round an ESPN round name denotes, or `null` when we cannot say.
 *
 * Exported because the guard asserts the MAPPING as well as the rendered
 * heading, and because a future surface that needs the same translation must
 * get it from here rather than growing a second table.
 */
export function registerRoundFromSource(
  sourceRound: string | null | undefined,
  roundCount: number = ROUND_NAMES.length
): RoundName | null {
  const raw = (sourceRound ?? "").trim().toLowerCase();
  if (raw === "") return null;
  // Qualifying is NOT a `RoundName` and must never be folded onto one: a
  // qualifying final is not the tournament's final.
  if (raw.startsWith("qual")) return null;

  const named = ESPN_NAMED_ROUNDS[raw];
  if (named) return named;

  const ordinal = /^round\s+(\d+)$/.exec(raw);
  if (!ordinal) return null;
  const n = Number(ordinal[1]);
  const count = Math.min(Math.max(Math.trunc(roundCount), 1), ROUND_NAMES.length);
  const index = ROUND_NAMES.length - count + n - 1;
  if (n < 1 || index >= ROUND_NAMES.length) return null;
  return ROUND_NAMES[index];
}

export function roundHeading(
  result: TournamentResult,
  roundCount: number = ROUND_NAMES.length
): string {
  // The register's own key, when the payload carries one. `build_results` sets
  // `round` from ESPN today, so this branch is the forward-compatible one — it
  // costs nothing and stops this function needing a second edit the day the
  // backend starts emitting `R128` for the 65 of 82 Round-1 rows it still holds
  // a register matchup for.
  const direct = ROUND_LABELS[result.round as RoundName];
  if (direct) return direct;

  const translated = registerRoundFromSource(result.source_round, roundCount);
  if (translated) return ROUND_LABELS[translated];

  if (result.source_round) return result.source_round;
  return ROUND_HEADINGS[result.round] ?? result.round;
}

/**
 * The register's vocabulary, plus the one bucket that is not a `RoundName`.
 *
 * `R128`…`F` are `ROUND_LABELS` verbatim and are NOT restated here — this table
 * having its own wording for them is how the page grew a third name for the
 * first round. Spread, so the two can never drift again.
 */
export const ROUND_HEADINGS: Record<string, string> = {
  qualifying: "Qualifying",
  ...ROUND_LABELS,
};

/**
 * ═══ WHAT THIS COUNT COUNTS (#2450, the second half) ═══
 *
 * `FINISHED · Men's Singles · 71` sat beside `ROUND OF 128 · 25 matches` and
 * neither number named its population, so Alex tried to reconcile them and
 * could not. The match list's half is answered by `matchRoundReconciliation`;
 * this is the other side of the same sentence.
 *
 * The number is every finished match in the draw across EVERY round — and on
 * the live payload 2026-09-01 rather more than half of it was qualifying: the
 * men's singles held 84 rows, 41 in the main draw and 43 across three
 * qualifying rounds. A reader counting a 128-draw's main-draw matches will
 * never reach 84, and the section never told them qualifying was in the total.
 *
 * Counted off the RENDERED rows rather than any payload total, for the reason
 * `prematchCoverage` gives: a note about a different list is worse than no
 * note. `null` when there is no qualifying in the list, because then the total
 * already means what a reader assumes it means and a clause saying so is noise.
 */
export function resultsPopulationNote(matches: TournamentResult[]): string | null {
  const qualifying = matches.filter((match) =>
    /^qual/i.test((match.source_round ?? match.round ?? "").trim())
  ).length;
  if (qualifying === 0) return null;
  return `Includes ${qualifying} qualifying ${qualifying === 1 ? "match" : "matches"}.`;
}

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

/**
 * The prefix `build_results` gives a row whose PAIRING the draw register does
 * not carry — `espn:182730` rather than
 * `mens-singles:ben-shelton-vs-tallon-griekspoor:2026-08-30`.
 *
 * `matchup_by_pair.get(..., f"espn:{comp_id}")` is the exact line, and the
 * fallback is reached only when the register has no matchup for the two
 * players. Both players ARE registered on such a row — a result with an
 * unregistered player never reaches this list at all; it is counted in
 * `unregistered_pairs`. So the prefix means precisely: *we know both these
 * people and we could not tie this fixture to a market of ours*.
 */
const SCOREBOARD_MATCHUP_PREFIX = "espn:";

export interface PrematchCoverage {
  /** Rows that print a prior. */
  withPrior: number;
  total: number;
  /**
   * Rows the register carries a matchup for, that still print no prior.
   *
   * We hold this fixture. A market for it was registered or it was not, and
   * either way no OPENING price was captured before play — which is a
   * different fact from the one below and the reason ux/1034 A3 exists.
   */
  heldWithoutOpening: number;
  /** Rows whose pairing the register does not carry — see the prefix note. */
  untied: number;
}

/**
 * How many of these results carry a prior, and WHY THE REST DO NOT (ux/1034 A3).
 *
 * ═══ THE SENTENCE THAT WAS WRONG ═══
 *
 * Alex, on the live hub: Shelton–Hurkacz shows no pre-match number, and the
 * footnote under it said *"The rest are matches nobody ran a market on"*. That
 * is false for that row, measurably: Polymarket had a market on it, its price
 * history simply starts at 17:38Z and the match started at 17:08Z — so what we
 * lack is an OPENING, not a market. He was explicit: *"say 'no pre-match
 * reading captured' when a market exists but no opening snapshot does.
 * Distinguish the two cases honestly."*
 *
 * The two cases the payload CAN distinguish are counted here. What it cannot
 * distinguish is a third: whether a venue ran a market on a fixture our
 * register never tied to one. Nothing in this payload knows that, so the
 * footnote stops claiming it — a sentence about what Kalshi and Polymarket
 * chose to list is a claim about a venue, and it was being made from a field
 * that only ever described US.
 */
export function prematchCoverage(matches: TournamentResult[]): PrematchCoverage {
  let withPrior = 0;
  let heldWithoutOpening = 0;
  let untied = 0;

  for (const match of matches) {
    if (match.players.some((player) => typeof player.prematch_probability === "number")) {
      withPrior += 1;
    } else if (String(match.matchup_key ?? "").startsWith(SCOREBOARD_MATCHUP_PREFIX)) {
      untied += 1;
    } else {
      heldWithoutOpening += 1;
    }
  }

  return { withPrior, total: matches.length, heldWithoutOpening, untied };
}

/**
 * Why the rows without a prior have not got one — the replacement for
 * *"The rest are matches nobody ran a market on"* (ux/1034 A3).
 *
 * Two counts, each said in the terms the payload can actually support, and a
 * closing clause that refuses the third. On the men's list as served on
 * 2026-09-03 this reads: *"Of the rest, 55 are fixtures we could not tie to a
 * market of ours and 3 are matches we hold but caught no price on before play
 * started — neither is a statement about whether a venue listed one."*
 *
 * Empty string when every row has a prior; the caller only prints it in the
 * branch where some row does not.
 */
export function prematchAbsenceNote(coverage: PrematchCoverage): string {
  const clauses: string[] = [];
  if (coverage.untied > 0) {
    clauses.push(
      `${coverage.untied} ${
        coverage.untied === 1 ? "is a fixture" : "are fixtures"
      } we could not tie to a market of ours`
    );
  }
  if (coverage.heldWithoutOpening > 0) {
    clauses.push(
      `${coverage.heldWithoutOpening} ${
        coverage.heldWithoutOpening === 1 ? "is a match" : "are matches"
      } we hold but caught no price on before play started`
    );
  }
  if (clauses.length === 0) return "";
  return (
    `Of the rest, ${clauses.join(" and ")} — neither is a statement about ` +
    `whether a venue listed one.`
  );
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

/* ═══ WHERE A FINISHED ROW GOES WHEN YOU CLICK IT (#2568) ═════════════════════
 *
 * On 2026-09-01 the Men's tab rendered 100 match rows — 11 upcoming from the
 * slate and 89 finished from here — and exactly ONE of them was a link. Not a
 * styling bug and not a per-match data gap: the slate row type carries an
 * `event_id` and this one never had the field at all, so the whole finished
 * half of the page was inert by construction.
 *
 * The address was already on the payload. `event_links.by_matchup` is the
 * server's own id-anchored resolution of `matchup_key -> events.id`, published
 * beside the results for exactly this reason, and it covered 63 of the 192
 * finished rows on that payload while every one of them rendered as dead text.
 *
 * TWO RULES, AND THEY ARE THE WHOLE FUNCTION:
 *
 *  1. **The map or nothing.** A missing key returns `null` and the row renders
 *     as text. We never fall back to a name join against the events table —
 *     ruling 048 and `tournament_event_link.py` both say it and the reason is
 *     that a link to the WRONG match is worse than no link, especially in a
 *     draw where `Auger-Aliassime` and `Auger Aliassime` are the same person
 *     to a reader and two rows to a matcher.
 *  2. **A synthetic key is not a key.** `build_results` mints `espn:{id}` for a
 *     finished match the register does not carry (90 of those 192 rows). Those
 *     can never be in `by_matchup` — the guard is here anyway, and explicit,
 *     so a future overlay that starts writing `espn:`-prefixed entries has to
 *     come and delete this line rather than silently start routing rows we
 *     have no register evidence for.
 *
 * ux/1002: BOTH RULES NOW LIVE IN `lib/tournamentEventLink.ts`, and the match
 * list calls the same function. They were written here because this list was
 * the first to need them; leaving them here made "where does a match link to"
 * a property of the FINISHED list rather than of the hub, which is how the
 * live half ended up answering the question differently. This wrapper stays so
 * the call sites and their guards do not move in the same change.
 */
export function resultEventHref(
  result: TournamentResult,
  eventIds: MatchupEventIds
): string | null {
  return matchupEventHref(result.matchup_key, eventIds);
}

/**
 * How many of THESE rows we can route, for the section's own footnote.
 *
 * Counted over the rendered draw rather than read off `event_links.linked`,
 * which is the all-draws total across the slate as well — the same mistake
 * `prematchCoverage` exists to avoid. A page that says "28 of 89" under a list
 * of 89 is saying something true about the list the reader is looking at.
 */
export function resultLinkCoverage(
  matches: TournamentResult[],
  eventIds: Record<string, number> | null | undefined
): { linked: number; total: number } {
  return {
    linked: matches.filter((match) => resultEventHref(match, eventIds) !== null)
      .length,
    total: matches.length,
  };
}
