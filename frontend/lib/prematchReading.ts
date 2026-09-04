/**
 * WHAT THE MARKET GAVE EACH TEAM BEFORE THE MATCH — the settled card's half of
 * ux/1036 Tier A.
 *
 * ═══ THE DEFECT ═══
 *
 * Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none
 * of these show pre-event probability?"*
 *
 * Every FINAL card had exactly one pre-match figure on it — a grey `Opened
 * 40/60` footnote — and that footnote fails at the one job the number has. It
 * does not say WHICH TEAM is the 40. A reader has to pair two slash-separated
 * figures against a name order printed somewhere else on the card, and the order
 * is home/away while the names above are drawn away-first. The live card three
 * rows up gives each team its own number.
 *
 * So the footnote goes and the number moves beside the name it is about. This
 * module is the one place that decides WHICH number that is, because three
 * surfaces print it (`/sports` and every other `FeedCard` list, Discover's
 * `EventCard`) and a per-surface answer is how they would drift.
 *
 * ═══ THE LADDER, AND THE FALLBACK BENEATH IT ═══
 *
 * The server resolves Alex's ordered ladder — Kalshi → Polymarket → books —
 * and sends the winner plus its rung as `prematch_odds`. This module does not
 * re-derive the ladder; re-deriving a decision the server already made is how
 * two answers to one question get shipped.
 *
 * What it DOES own is the case where that key is absent. A feed response is
 * cached, so "the backend deployed it" is not "this payload carries it" — the
 * same reason `servedDuelPercents` exists. The fallback is `opening_odds`, and
 * the fallback is LABELLED `books`, because that is what `opening_odds` has
 * always been: the only writer of `Event.opening_*` is `_maybe_set_opening_odds`,
 * a median across whichever sportsbooks were still quoting (#1841). An
 * unlabelled fallback would be the old footnote with a new shape.
 *
 * ═══ WHY ONLY THE BOOKS RUNG WAS LABELLED (SUPERSEDED — read to the end) ═══
 *
 * Kept because it is the argument Alex overruled, and a deleted argument comes
 * back. Nothing below this heading describes the current render.
 *
 * Alex: *"labelled when not a prediction market."* A prediction-market opening
 * is the thing this product is about and reads as itself. A sportsbook median is
 * a different claim wearing the same shape, and ux/1034 A3 is the precedent for
 * why that matters: the hub's old footnote made a claim about a venue from a
 * field that only ever described us, and it was false on the very row Alex read.
 *
 * The label is the generic word and never a venue name — there is no single book
 * to name (it is a median), and ruling 141 keeps venue names out of narrative
 * copy regardless.
 *
 * ═══ AND THE GENERIC WORD WAS THE WRONG ONE (D57, Alex 2026-09-03) ═══
 *
 * Alex, on the US Open hub: *"90% BOOKS / 10% BOOKS on every finished row. Is
 * that a gambling reference? We wouldn't want that, but it's confusing either
 * way."* Both halves land. `books` is trade slang for the counterparties we buy
 * a line from; a reader who decodes it reads a gambling noun on a probability
 * product, and a reader who does not reads a word with no meaning stapled to
 * every number on the list.
 *
 * ═══ THE FIRST ANSWER WAS WRONG TOO (D57 CORRECTED, Alex 2026-09-03 4:15pm) ═══
 *
 * Round one deleted the word and kept the caveat: a dagger beside the figure, a
 * `title` reading "pre-match number, from sportsbooks", and a section legend
 * counting the daggers. Alex, on that:
 *
 *   > We don't need to say anything about sportsbooks. Our whole product is
 *   > probabilities and how they're moving. Just show the %, but if it's a
 *   > pre-match probability that we're comparing to the final score, THAT
 *   > should be visually clear — and we've solved that problem on event cards
 *   > elsewhere.
 *
 * So the DISTINCTION is overruled, not just its wording. ux/1034 A3 and CERT-812
 * both bought the rule "a sportsbook median may not be printed as a
 * prediction-market opening", and both were arguing about a surface that made a
 * VENUE CLAIM in words. This surface no longer makes one: nothing visible says
 * where the figure came from, so nothing visible can say it wrongly. What
 * remains to be true is what the number IS — a pre-match reading being compared
 * to a settled result — and that is a job for the treatment, not for a glyph.
 *
 * `PREMATCH_NUMBER_CLASS` below is that treatment, and it is one string because
 * Alex's instruction was "find it, reuse it, do not invent a third". The
 * distinction survives where it costs a reader nothing: in `data-prematch-source`
 * (a queryable fact, which is what a cert reads) and in the spoken clause, which
 * still names its own rung so the one reader who cannot see the layout is not
 * handed a claim the page never made in pixels.
 */

import type { FeedEventData } from "@/lib/types";
import { servedDuelPercents } from "@/lib/servedDuelPercents";

/** The rung a reading came from. Payload source ids, not display text. */
export const BOOKS_SOURCE = "books";
const PREDICTION_MARKET_SOURCES = new Set(["kalshi", "polymarket"]);

/**
 * THE ONE TREATMENT FOR A PRE-MATCH NUMBER ON A SETTLED SURFACE (D57 corrected).
 *
 * ═══ WHY IT IS A CONSTANT AND NOT FOUR CLASS LISTS ═══
 *
 * Alex: *"we've solved that problem on event cards elsewhere … find it, reuse
 * it, do not invent a third."* There were FOUR when he said it. `FeedCard` and
 * `EventCard` agreed (`font-mono text-[11px] tabular-nums text-text-muted`),
 * Discover's `EventCard` inherited `text-sm` from its strip, and the tournament
 * hub had invented its own (`text-[12px] text-text-secondary`, no mono) — which
 * is the surface Alex was reading. Four surfaces printing one thing four ways is
 * the same failure `prematchReading` was written to stop, one layer down: this
 * module already owned WHICH number, and did not own what it LOOKS like.
 *
 * ═══ WHAT THE TREATMENT HAS TO DO ═══
 *
 * Say "this is not the result" without a word. Three properties carry it, and
 * each is load-bearing:
 *
 *   - `text-text-muted` — grey on BOTH rows, winner included. Bold on a settled
 *     card means "this is what happened"; a prior is the opposite of that, so
 *     the winner's prior is grey too. This is the rule ux/1036 shipped.
 *   - `font-mono` + `tabular-nums` — the figure reads as a measurement in a
 *     column, and the two numbers in a pair line up digit for digit.
 *   - `text-[11px]` — smaller than the score it sits beside. The settled score
 *     is the loud thing on the row; the prior is context for it.
 *
 * The contrast against the bold score in the next column IS the "visually
 * clear" Alex asked for. It needs no legend, and a legend is what it replaced.
 */
export const PREMATCH_NUMBER_CLASS =
  "font-mono text-[11px] tabular-nums text-text-muted";

export interface PrematchReading {
  /** Whole percents, away first — rounded ONCE as a pair (UX-P114). */
  awayPercent: number | null;
  homePercent: number | null;
  /** The raw probabilities, for `data-` attributes and screen-reader prose. */
  awayProbability: number;
  homeProbability: number;
  /**
   * Which rung — for `data-prematch-source` and for the spoken clause, and for
   * nothing a reader can see.
   *
   * `label` (the word `books`) became `marker` (a dagger) in D57 round one and
   * is now GONE, not renamed a third time. A field whose only consumer is a
   * render site is how the caveat came back wearing a glyph; the rung is still
   * here, on the one field that was always a fact rather than a decoration, and
   * a surface that wants to print it has to reach for `isPredictionMarketSource`
   * on purpose.
   */
  source: string;
}

export function isPredictionMarketSource(source: string | null | undefined): boolean {
  return source != null && PREDICTION_MARKET_SOURCES.has(source);
}

/**
 * The pre-match reading this card should print, or `null` when we hold none.
 *
 * `null` is a real answer and the only one that licenses an empty space: the
 * settled card prints nothing rather than a number about a different question,
 * exactly as the tennis hub's finished list already does.
 */
export function prematchReading(
  data: Pick<FeedEventData, "prematch_odds" | "opening_odds">,
): PrematchReading | null {
  const served = data.prematch_odds;
  if (served && isUsable(served.home_probability)) {
    const away = isUsable(served.away_probability)
      ? served.away_probability
      : 1 - served.home_probability;
    // Served pair or neither (#2279) — a served percent beside a derived one is
    // the 101 UX-P114 closed, arriving from the other direction.
    const [awayPercent, homePercent] = servedDuelPercents(
      away,
      served.home_probability,
      served.away_rendered_percent,
      served.home_rendered_percent,
    );
    return {
      awayPercent,
      homePercent,
      awayProbability: away,
      homeProbability: served.home_probability,
      source: served.source,
    };
  }

  // The pre-rollout / cached-payload path. `opening_odds` carries no rendered
  // percents from any serializer, so the pair is rounded locally — `null` for
  // both served values, per `servedDuelPercents`' red note.
  const opening = data.opening_odds;
  if (!opening || !isUsable(opening.home_probability)) return null;
  const away = isUsable(opening.away_probability)
    ? (opening.away_probability as number)
    : 1 - opening.home_probability;
  const [awayPercent, homePercent] = servedDuelPercents(
    away,
    opening.home_probability,
    null,
    null,
  );
  return {
    awayPercent,
    homePercent,
    awayProbability: away,
    homeProbability: opening.home_probability,
    source: BOOKS_SOURCE,
  };
}

/**
 * Rejects the endpoints as well as the out-of-range: a pre-match reading of
 * exactly 0 or 1 is a settled price that leaked backwards past the server's
 * clock filter, and it would print as the strongest claim on the card.
 */
function isUsable(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 && value < 1;
}
