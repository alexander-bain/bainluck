/**
 * THE SETTLED HERO'S PRE-GAME MARK — the same number the game's card printed (#8315).
 *
 * ═══ THE DEFECT ═══
 *
 * Measured 2026-09-24 00:00Z, production, Nationals @ Tigers (final). The
 * Discover card said "Washington Nationals won as a 39% underdog"; tapping it,
 * `/events/15317535` said "Nationals WON · Upset · 40% pregame". One question,
 * two numbers, one tap apart.
 *
 * The card follows Alex's ladder — Kalshi → Polymarket → sportsbooks — which
 * the server resolves once and serves as `prematch_odds` (`lib/prematchReading.ts`).
 * The hero read `opening_odds`, the sportsbook median, because until #8315 the
 * event endpoint served nothing else. On this game the rungs differ by a point;
 * where the venue and the books disagree more, the gap is larger and can turn
 * "Upset" on or off.
 *
 * ═══ THE RULE ═══
 *
 * `prematch_odds` when the payload carries it, through `prematchReading` so the
 * pair is rounded exactly as the card rounds it. `opening_odds` only when it is
 * absent — a cached pre-#8315 payload, or a status the server does not resolve
 * it for — and then labelled as the sportsbook median it is, as the card does.
 * Once `prematch_odds` is served it IS the answer: a withheld side does not fall
 * through to the books, because that would print a different rung from the card.
 *
 * ═══ THE DRAW-PRICED AWAY SIDE (#6238 / #6614) ═══
 *
 * The page's existing rule survives the switch. On a draw-priced sport an away
 * figure that is just `1 − home` is the draw folded into the away team, so when
 * the AWAY side won and the served pair is a complement, the mark is withheld —
 * the same `awayIsTheComplement` question the opening path already asks (the
 * caller passes the opening away already withheld by it). A three-way venue
 * reading that carries its draw falls short of 1 and is kept.
 */

import type { FeedEventData } from "@/lib/types";
import { awayIsTheComplement } from "@/lib/drawPricedWinner";
import { BOOKS_LABEL, BOOKS_SOURCE, prematchReading } from "@/lib/prematchReading";

export interface SettledPregameMark {
  /** The winner's pre-match probability, 0-1. Decides "Upset". */
  probability: number;
  /**
   * The whole percent to print, rounded as a pair with the loser's (UX-P114) —
   * the card's number. `null` on the opening fallback, where no serializer
   * rounded it and the hero rounds the probability itself.
   */
  percent: number | null;
  /** The rung, for `data-prematch-source`. */
  source: string;
  /** "sportsbooks" on the books rung; `null` for a prediction market. */
  label: string | null;
}

export function settledPregameMark(args: {
  winnerSide: "home" | "away" | null | undefined;
  prematchOdds: FeedEventData["prematch_odds"] | undefined;
  openingHomeProb: number | null;
  /** Already withheld by `awayIsTheComplement` on the page. */
  openingAwayProb: number | null;
  sport: string | null | undefined;
}): SettledPregameMark | null {
  const { winnerSide, prematchOdds, openingHomeProb, openingAwayProb, sport } = args;
  if (!winnerSide) return null;

  const served = prematchOdds
    ? prematchReading({ prematch_odds: prematchOdds, opening_odds: undefined })
    : null;
  if (served) {
    if (
      winnerSide === "away" &&
      awayIsTheComplement(served.awayProbability, served.homeProbability, sport)
    ) {
      return null;
    }
    return {
      probability: winnerSide === "home" ? served.homeProbability : served.awayProbability,
      percent: winnerSide === "home" ? served.homePercent : served.awayPercent,
      source: served.source,
      label: served.label,
    };
  }

  // The pre-#8315 path, gate unchanged: both legs present (see the #6614 note
  // on the page for why the gate is not loosened).
  if (openingHomeProb === null || openingAwayProb === null) return null;
  return {
    probability: winnerSide === "home" ? openingHomeProb : openingAwayProb,
    percent: null,
    source: BOOKS_SOURCE,
    label: BOOKS_LABEL,
  };
}
