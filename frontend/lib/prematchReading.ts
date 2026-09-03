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
 * ═══ WHY ONLY THE BOOKS RUNG IS LABELLED ═══
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
 */

import type { FeedEventData } from "@/lib/types";
import { servedDuelPercents } from "@/lib/servedDuelPercents";

/** The rung a reading came from. Payload source ids, not display text. */
export const BOOKS_SOURCE = "books";
const PREDICTION_MARKET_SOURCES = new Set(["kalshi", "polymarket"]);

export interface PrematchReading {
  /** Whole percents, away first — rounded ONCE as a pair (UX-P114). */
  awayPercent: number | null;
  homePercent: number | null;
  /** The raw probabilities, for `data-` attributes and screen-reader prose. */
  awayProbability: number;
  homeProbability: number;
  /** Which rung. */
  source: string;
  /**
   * The word the card prints beside the pair, or `null` when the reading needs
   * no caveat. Only ever set for a non-prediction-market rung.
   */
  label: string | null;
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
      label: sourceLabel(served.source),
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
    label: sourceLabel(BOOKS_SOURCE),
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

function sourceLabel(source: string): string | null {
  return isPredictionMarketSource(source) ? null : BOOKS_SOURCE;
}
