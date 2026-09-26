/**
 * #8025 — ONE BOARD RULE, READ BY BOTH FUTURES CARDS.
 *
 * ## The defect this exists to close
 *
 * There are two futures cards, and only one of them was ever wired to the
 * distribution board:
 *
 *   • `components/discover/FuturesCard.tsx` → `/discover`. Draws a leader-first
 *     board of four off `discover_card.distribution_outcomes`, plus a remainder
 *     row saying how many outcomes it did not draw.
 *   • the local `FuturesFeedCard` in `components/FeedCard.tsx` → `/sports`,
 *     `/categories/*`, `/my-stuff`. Read `top_outcomes` and nothing else — it
 *     contained no reference to `discover_card` at all.
 *
 * So `2027 IPL Champion` — a ten-team field, eight of them priced — rendered on
 * `/categories/cricket` as three teams totalling 43%, with no signal that seven
 * more existed. The same market on `/discover` was a ranked board of four over
 * "Field and 6 more outcomes". Same question, two answers, decided by which page
 * the reader came in through (notice 35: ONE CARD FAMILY EVERYWHERE).
 *
 * ## Why a module and not a copied branch
 *
 * The rule below is not one line, it is five years of measured bends —
 * #1526 (sort before slicing), #6505 (a row we cannot price is not a row, and
 * the minimum-row bar bends for a board that HAD the rows), CERT-2456 / #4610
 * (a refused ladder is still a field), #6586 (the remainder counts off the
 * unfiltered list), #7844 half two (an independent set is not a podium and has
 * no residual field). Porting that into a second card is how the two drifted
 * apart in the first place. The ROW TEMPLATE stays each card's own — Discover
 * draws a podium with rank digits, the browse card draws its own compact row —
 * but WHICH rows, HOW MANY, and WHAT THE REMAINDER SAYS is decided here, once.
 *
 * ## Faithful extraction, deliberately
 *
 * Every line below is `discover/FuturesCard.tsx`'s own arithmetic, moved rather
 * than rewritten, so that no card which renders correctly today changes shape.
 * That includes one sharp edge kept exactly as it was: `remaining_outcome_count`
 * is added WITHOUT a `?? 0`, so a payload that omits it yields `NaN` and the
 * remainder row does not draw (`NaN > 0` is false). Defaulting it to 0 would
 * start drawing a remainder row on a payload shape that draws none today, which
 * is a behaviour change wearing the clothes of a tidy-up. Every one of the 44
 * board-clearing cards measured on `GET /api/feed?limit=200` (2026-09-22 15:4xZ)
 * serves the field.
 */

import { leaderFirstSlice, printsAPercent } from "./leaderOrder";
import { renderedRaceBoardPercents } from "@/lib/renderedPercent";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type { FeedFuturesData } from "@/lib/types";

/** One row of `discover_card.distribution_outcomes` as a card renders it. */
export type FuturesBoardRow = {
  label: string;
  probability: number | null;
  movement?: number | null;
};

export type FuturesBoard = {
  /** Leader-first, priced, capped at `FUTURES_BOARD_ROW_LIMIT`. */
  rows: FuturesBoardRow[];
  /** How many outcomes the board does not draw. Zero ⇒ no remainder row. */
  remainingCount: number;
  /**
   * #7844 half two — may this board be read as a podium? False only when the
   * route says so explicitly; an absent field fails to today's rendering.
   */
  fieldIsARace: boolean;
  /**
   * #8033 — the printed percent for each row of `rows`, or `null` at a position
   * meaning "no override, keep `formatProbabilityPercent`'s own rounding".
   *
   * Parallel to `rows` by index. Only ever non-null for the top two rows of a
   * board that is a confirmed complement pair whose independent roundings
   * already exceed 100 — see `renderedRaceBoardPercents` for all six clauses.
   */
  rowPercents: Array<number | null>;
};

/**
 * Four. The same four on both cards — a browse surface showing three rows and
 * Discover showing four of the same board is the disagreement this ship closes,
 * so the count is not a per-caller option.
 */
export const FUTURES_BOARD_ROW_LIMIT = 4;

/**
 * `discover_card` is still untyped debt on `FeedFuturesData` (frontend tsc
 * baseline, #1521), so it is read here through one narrow local cast rather than
 * as five bare accesses that each bill a baselined error.
 */
type DiscoverCardBoardFields = {
  suggested_format?: string | null;
  distribution_outcomes?: FuturesBoardRow[] | null;
  /** Not optional on purpose — see the `NaN` note in the module docblock. */
  remaining_outcome_count: number;
  ladder_treatment_refused?: boolean | null;
  field_is_a_race?: boolean | null;
};

/**
 * The board this payload earns, or `null` when it does not clear the bar and the
 * card should render its ordinary leader treatment instead.
 */
export function futuresDistributionBoard(data: FeedFuturesData): FuturesBoard | null {
  const card = (data as { discover_card?: DiscoverCardBoardFields | null }).discover_card;
  const allRows: FuturesBoardRow[] = card?.distribution_outcomes ?? [];
  // #6505 — a row the card cannot put a number on is not a row.
  const priced = allRows.filter((row) => printsAPercent(row.probability));
  // CERT-2456 / #4610 — a ladder served as a distribution BECAUSE the backend
  // refused to say which rung is wrong has three rows, not four.
  const ladderTreatmentRefused = card?.ladder_treatment_refused === true;
  // #6505 — a board that HAD enough rows and lost them only to the price filter
  // is still a board.
  const droppedBelowTheBar = allRows.length >= 4 && priced.length < 4;
  const minRows = ladderTreatmentRefused || droppedBelowTheBar ? 2 : 4;

  if (card?.suggested_format !== "outcome_distribution" || priced.length < minRows) {
    return null;
  }

  // #1526 — sort BEFORE slicing, or the slice drops the leader.
  const rows = leaderFirstSlice(priced, FUTURES_BOARD_ROW_LIMIT);
  return {
    rows,
    // #6586 — counted off the UNFILTERED list, so a row we declined to draw is
    // still a row the reader is told exists.
    remainingCount: card.remaining_outcome_count + Math.max(0, allRows.length - rows.length),
    fieldIsARace: card.field_is_a_race !== false,
    // #8033 — THE TOP TWO MAY NOT OWN MORE THAN THE RACE, ON BOTH CARDS.
    //
    // Taken over `rows` and not `priced`, because the pair a reader can add up
    // is the pair that is DRAWN, and after the slice, because the helper's
    // leader-first clause is a check on the list it is handed.
    //
    // The two `field_is_a_race` derivations on this object are deliberately
    // different and must stay so. The podium question above fails to today's
    // rendering on an absent key (`!== false`); this one fails CLOSED
    // (`=== true`). A payload with no flag has not told us the field is
    // exclusive, and deriving a row down a point on a board that turns out to be
    // independent would be a wrong number rather than a missing repair. It costs
    // nothing to wait — the feed blob's TTL is 30s — and the live specimen
    // serves the key explicitly.
    rowPercents: renderedRaceBoardPercents(
      rows.map((row) => row.probability),
      card.field_is_a_race === true,
    ),
  };
}

/**
 * #8837 — HOW MANY OUTCOMES THIS MARKET HAS, counted the way the board counts
 * them, for a surface that draws its own rows and still owes the reader the rest.
 *
 * The related rail (`components/RelatedByTag.tsx`) draws three rows off
 * `top_outcomes` and used to say how many it left out off the payload's raw
 * `outcome_count` — every stored leg. On `Next French Presidential Election`
 * that is 128, so the rail said "+125 more" while the Discover card for the same
 * market, two taps earlier, said "Field and 39 more outcomes" under four rows:
 * 43. The route builds `remaining_outcome_count` as
 * `len(card_outcomes) - len(distribution_outcomes)`, so their sum is the card's
 * own outcome set — and it is exactly `rows.length + remainingCount` of the board
 * above for any payload the board draws. One market, one total, on every card.
 *
 * `null` when the payload does not carry the count: a surface then prints no
 * remainder rather than falling back to the raw leg count this exists to retire.
 * PURE.
 */
export function futuresOutcomeTotal(data: FeedFuturesData): number | null {
  const card = (data as { discover_card?: Partial<DiscoverCardBoardFields> | null })
    .discover_card;
  const remaining = card?.remaining_outcome_count;
  if (typeof remaining !== "number" || !Number.isFinite(remaining)) return null;
  return (card?.distribution_outcomes ?? []).length + remaining;
}

/**
 * #8112 — MAY THIS BOARD DRAW A LEADER AT ALL?
 *
 * ## The defect
 *
 * `2026-27 Stanley Cup® Finals Winner` prices Colorado Avalanche and Florida
 * Panthers at `0.1031` each. Both rows print **10%**. The board gave one of them
 * the rank digit `1`, `font-bold` and the `bg-accent-brand` bar, and the other
 * `2`, `font-semibold` and a muted grey bar — a podium built on a dead heat,
 * with which club stood on it decided by nothing (`leaderFirstSlice` is a STABLE
 * sort, so it is whichever order the payload happened to arrive in).
 *
 * ## The rule already existed; it was wired to the copy and not to the paint
 *
 * #6187 is the same card and the same tie ("A futures card says 'Florida
 * Panthers leads at 10%' above a board where the runner-up also reads 10%"). It
 * shipped `lead_is_printable` (`app/utils/feed_reasons.py:1997`), which asks
 * whether "a reader checking the board can see the lead the sentence asserts",
 * and the backend obeys it today — this card's headline is `Colorado Avalanche
 * at 10%` with no comparative, while its four siblings in the same edition all
 * clear the gate and all say "leads". So the SENTENCE already refuses the claim
 * that the BOARD then makes in bold and brand green. This function is that same
 * question asked of the chrome.
 *
 * ## Competition ranking, on the PRINTED STRING
 *
 * Rows printing the same percentage as the row above share its rank; the next
 * distinct row takes the position it actually occupies (1, 1, 3, 4). That keeps
 * the remainder row's `rows.length + 1` correct with no special case, because
 * competition ranking never renumbers the tail.
 *
 * The tie test is the string `formatProbabilityPercent` EMITS, not a second
 * rounding of the probability. That is deliberate and load-bearing twice over:
 * it is exactly what a reader can check by looking at two cells, and it is the
 * same call the value cell makes with the same `rendered` override, so the
 * chrome and the number can never disagree about whether two rows are level. A
 * private `Math.round(p * 100)` here would be a second scale wearing the first
 * one's name — it would miss `<1%` rows that print identically from different
 * probabilities, and it would drift the moment #8033's override moved.
 *
 * FAILS CLOSED: a row that cannot print a percent (#6505) never shares a rank,
 * so an unpriced row can neither become a co-leader nor absorb one.
 *
 * PURE: no I/O, no clock, no ambient state.
 */
export function boardRowRanks(board: FuturesBoard): number[] {
  const printed = board.rows.map((row, index) =>
    printsAPercent(row.probability)
      ? formatProbabilityPercent(row.probability ?? 0, { rendered: board.rowPercents[index] })
      : null,
  );
  const ranks: number[] = [];
  printed.forEach((value, index) => {
    const tiesWithRowAbove = index > 0 && value !== null && value === printed[index - 1];
    ranks.push(tiesWithRowAbove ? ranks[index - 1] : index + 1);
  });
  return ranks;
}

/**
 * The remainder row's sentence, or `null` when there is nothing left to say.
 *
 * #6586 pinned the copy ("+N more outcome" / "…outcomes", singular slip and all)
 * and #7844 half two took "Field and " off the non-exclusive arm — on an
 * independent set there is no residual field, only more separate questions. Both
 * cards say it identically because they call this.
 */
export function futuresBoardRemainderLabel(board: FuturesBoard): string | null {
  if (!(board.remainingCount > 0)) return null;
  return `${board.fieldIsARace ? "Field and " : ""}${board.remainingCount} more outcome${
    board.remainingCount === 1 ? "" : "s"
  }`;
}
