/**
 * The match page's types and pure presentation logic (UX-P149).
 *
 * Pure functions, for the same reason as `lib/slate.ts` and `lib/tournament.ts`:
 * the jest gate runs in the node environment with no jsdom, so logic that only
 * exists inside a component body is logic no guard can reach (ruling 005).
 *
 * ═══ WHAT THIS PAGE IS ═══
 *
 * Lane1's Q426 note made the routing call — match props belong on the match's
 * own surface, grouped under the match-winner market — and named the blocker
 * that made the surface a ux job: there was no per-match surface. This is it.
 * The hero is the match-winner duel, exactly the row the match list already
 * prints; everything under it is a question about the same match, from the
 * same Polymarket group, with the same freshness vocabulary.
 *
 * ═══ THE TWO RULES THAT ARE LOAD-BEARING RATHER THAN COSMETIC ═══
 *
 * 1. **A DECIDED MATCH PRINTS THE OPENING NUMBER, NOT THE CURRENT ONE.**
 *
 *    Standing Alex ruling: settled means settled. A prop market does not
 *    reliably settle — measured on the Fearnley / Rodionov specimen, the
 *    match-winner market read 0.05% while "Who wins set 1" still read the
 *    pre-match 62.5%, hours after that set had been played and won by the
 *    other man. Printing the current number under a finished match is a live
 *    question with a stale answer.
 *
 *    So `answerProbability` reads `opening_probability` once the match is
 *    decided, and `propFreshnessLabel` returns `null` there — an opening quote
 *    is not stale, it is historical, and an age beside it would be answering a
 *    question nobody asked. This is the same argument `_prematch_by_pair`
 *    makes for the results section, applied to the props.
 *
 * 2. **A PAIR IS ROUNDED ONCE, TOGETHER** (UX-P147, Alex's item 4). Two
 *    probabilities rounded independently print 74% and 27%. `renderedDuelPercents`
 *    rounds the favourite and derives the other, so a two-answer card cannot
 *    sum to 101. A ladder is NOT a pair — its rungs are separate questions and
 *    each rounds on its own.
 */

import { MATCH_ROUND_LABELS, slateRoundKey } from "./matchList";
import { renderedDuelPercents, renderedPercent } from "./renderedPercent";
import type { Broadcast, PriceState, SlateMatch } from "./slate";
import type { TournamentResult } from "./tournamentResults";

export interface MatchPropAnswer {
  /** The sentence a reader sees — never `Yes`, `No`, `Over` or `Under`. */
  label: string;
  /** The player this answer belongs to, when it belongs to one. */
  entity_key: string | null;
  probability: number | null;
  /**
   * What the market said before the match. The only number this page may
   * print once the match is decided — see rule 1 above.
   */
  opening_probability: number | null;
  probability_is_live: boolean;
  observed_at: string | null;
  age_hours: number | null;
  price_state: PriceState;
}

export interface MatchProp {
  key: string;
  /** `duel` two players · `handicap` a margin · `threshold`/`ladder` a count. */
  kind: "duel" | "handicap" | "threshold" | "ladder" | "other";
  family: "set_winner" | "handicap" | "total" | "other";
  /** "Who wins set 1" — the question, in the reader's words, from the server. */
  question: string;
  /** A caveat the server attaches; today only for an unrecognised market. */
  note: string | null;
  answers: MatchPropAnswer[];
  market_ids: (number | null)[];
  coherent: boolean;
  opening_coherent: boolean;
  probability_is_live: boolean;
  price_state: PriceState;
  observed_at: string | null;
  age_hours: number | null;
  stale_answers: string[];
  mixed_freshness: boolean;
}

export interface MatchDetailPayload {
  slug: string;
  title: string;
  subtitle: string;
  tournament: string;
  season: string;
  matchup_key: string;
  match: SlateMatch;
  /** ESPN's verdict, or `null` while the match is still to come. */
  result: TournamentResult | null;
  /** ESPN's verdict, not a clock comparison — a late match is still on. */
  decided: boolean;
  props: MatchProp[];
  props_count: number;
  /** Named reasons a sibling market did not render. Never a silent short list. */
  props_dropped: Record<string, number>;
  /**
   * Where to watch, per region. Tournament-wide until a session feed exists —
   * see `matchBroadcast`, which tags the scope so a guard can prove which
   * answer this is rather than a per-match one that coincidentally matched.
   */
  broadcasts?: Broadcast[];
  generated_at: string;
}

/** The section's name. One constant, so a re-wording is one line. */
export const PROPS_HEADING = "More on this match";
export const PROPS_HEADING_DECIDED = "What the market thought beforehand";

/**
 * The number to print for one answer — current, or the opening quote.
 *
 * `decided` is the whole switch. See rule 1 in the module docstring for the
 * measured specimen this exists to stop.
 */
export function answerProbability(
  answer: MatchPropAnswer,
  decided: boolean
): number | null {
  return decided ? answer.opening_probability : answer.probability;
}

/**
 * The card's answers as whole percents, rounded ONCE for a pair.
 *
 * A two-answer card is a duel and its two numbers are complements, so they go
 * through `renderedDuelPercents` and cannot sum to 101 (UX-P147, item 4). A
 * ladder's rungs are three separate markets answering three separate
 * questions; rounding them together would be arithmetic on unrelated numbers.
 */
export function answerPercents(
  prop: MatchProp,
  decided: boolean
): Array<number | null> {
  const values = prop.answers.map((answer) => answerProbability(answer, decided));
  if (values.length === 2 && prop.kind !== "ladder") {
    return renderedDuelPercents(values[0], values[1]);
  }
  return values.map((value) => renderedPercent(value));
}

/** `48%`, or the em-dash the page uses for "no number to show". */
export function formatAnswerPercent(percent: number | null): string {
  return percent === null ? "—" : `${percent}%`;
}

/**
 * May this card be printed in the confident type?
 *
 * A decided match's card is NEVER live — it is a historical number and
 * dressing it as current is the defect rule 1 exists to prevent. Otherwise the
 * SERVER decides, exactly as it does on the boards and the slate; this file is
 * not allowed to talk itself into a yes.
 */
export function propIsPresentedAsLive(prop: MatchProp, decided: boolean): boolean {
  if (decided) return false;
  return prop.probability_is_live === true;
}

/** Human age, rounded DOWN — "8 days ago" must never flatter to "7". */
export function propStalenessLabel(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "no reading yet";
  if (ageHours < 1) return `${Math.max(1, Math.floor(ageHours * 60))} min ago`;
  if (ageHours < 48) {
    const hours = Math.floor(ageHours);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  return `${Math.floor(ageHours / 24)} days ago`;
}

/**
 * The line beside a muted card, saying WHY it is muted. `null` when it is not.
 *
 * Same posture and same vocabulary as `slateRowFreshnessLabel` — a page that
 * words one admission two ways teaches the reader that one of them is
 * decorative. `null` on a decided match: an opening quote has no age, and
 * "20 days ago" beside it would name the wrong problem.
 */
export function propFreshnessLabel(prop: MatchProp, decided: boolean): string | null {
  if (decided) return null;
  if (propIsPresentedAsLive(prop, decided)) return null;
  // Ruling 138 says the word is PROBABILITY; "No market yet" answered a
  // probability question with an inventory fact. Same slot, same length, the
  // page's own noun.
  if (prop.price_state === "unpriced") return "No probability yet";
  if (!prop.coherent && prop.price_state === "live") return null;
  return propStalenessLabel(prop.age_hours);
}

/**
 * Cards that have something to show, in the server's order.
 *
 * A card with no printable number on ANY answer is dropped: on a decided match
 * that means we hold no opening quote for it, and a question with an em-dash
 * against every answer teaches the reader nothing except that the page is
 * broken. It is a filter and not a truncation — `hiddenPropCount` reports it.
 */
export function visibleProps(payload: MatchDetailPayload): MatchProp[] {
  return (payload.props ?? []).filter((prop) =>
    answerPercents(prop, payload.decided).some((percent) => percent !== null)
  );
}

/** How many cards `visibleProps` left out. Never a silent shrink. */
export function hiddenPropCount(payload: MatchDetailPayload): number {
  return (payload.props ?? []).length - visibleProps(payload).length;
}

/**
 * The one sentence under the section heading.
 *
 * It has one job: say where these questions came from. A reader who has just
 * scrolled past a match probability needs to know that the numbers below are
 * the same market's answers to other questions about the same match, and not a
 * different source, a model, or our opinion.
 */
export function propsProvenance(payload: MatchDetailPayload): string {
  if (payload.decided) {
    return "These are the numbers the market was showing before the match, not readings taken after the result was known.";
  }
  return "Same market as the probability above, asked about other parts of the same match.";
}

/**
 * "Men's Singles · Qualifying · Thu, Aug 27, 3:00 PM" — the one metadata line.
 *
 * The round goes through `MATCH_ROUND_LABELS` rather than being printed raw.
 * The register's own value is `qualifying`, lowercase, and a line reading
 * "Men's Singles · qualifying" looks like a field somebody forgot to format —
 * which is exactly what it was.
 */
export function matchSubheading(match: SlateMatch, now: Date = new Date()): string {
  const parts: string[] = [];
  if (match.draw_label) parts.push(match.draw_label);
  if (match.round) parts.push(MATCH_ROUND_LABELS[slateRoundKey(match.round)]);
  const at = new Date(match.scheduled_date);
  if (!Number.isNaN(at.getTime())) {
    const sameYear = at.getFullYear() === now.getFullYear();
    parts.push(
      at.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        ...(sameYear ? {} : { year: "numeric" }),
        hour: "numeric",
        minute: "2-digit",
      })
    );
  }
  return parts.join(" · ");
}

/**
 * The two sides in the order the hero draws them: favourite first.
 *
 * `null` when the pair is incoherent — with no trustworthy split there is no
 * favourite, and picking the larger of two numbers we have refused to display
 * would smuggle the refused comparison back onto the page. Mirrors
 * `orderedSides` on the slate deliberately.
 *
 * On a DECIDED match the order is the result's, not the market's: the winner
 * leads. A finished match whose loser is listed first because the market liked
 * them is a page arguing with its own headline.
 */
export function heroOrder(
  match: SlateMatch,
  result: TournamentResult | null
): SlateMatch["sides"] | null {
  const sides = match.sides ?? [];
  if (sides.length !== 2) return null;
  if (result) {
    const winner = result.winner_entity_key;
    const ordered = [...sides].sort((a, b) =>
      a.entity_key === winner ? -1 : b.entity_key === winner ? 1 : 0
    );
    return ordered;
  }
  if (!match.coherent) return null;
  return (sides[0].probability ?? 0) >= (sides[1].probability ?? 0)
    ? sides
    : [sides[1], sides[0]];
}
