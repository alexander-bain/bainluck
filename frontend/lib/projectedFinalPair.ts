/**
 * #9034 — ONE PROJECTED FINAL PER GAME, CHOSEN IN ONE PLACE.
 *
 * Production 2026-09-27 03:25Z, 390px, Dolphins @ Chiefs (`/events/14781701`,
 * pre-game): the search card read `Proj 18-29` and the event page one tap later
 * read `Projected final: 17 – 28`. The card rounded the sportsbooks' pair on
 * `current_odds` (17.5 / 28.7, 21 sportsbooks); the hero rounded
 * `/history`'s `pm_spread_data.projected_final` (17.2 / 27.6, Kalshi ladders).
 * The page's own pre-game margin tile read `KC by 11.2+` — the sportsbook
 * spread, the card's source. The blend is the product: one number per question.
 *
 * THE CARD CANNOT READ `/history`, SO THE PAGE READS WHAT THE CARD READS. List
 * payloads carry `current_odds` and no ladders, so the only pair every surface
 * can agree on before kickoff is the sportsbook one — which is also the
 * heaviest source in the blend. The card prints its projection only before
 * kickoff (`!isLive`), so that is exactly the window this file takes over; once
 * the game is live the card prints no projection and the page keeps the
 * ladders' in-game pair, unchanged.
 *
 * Both halves read `sportsbookProjectedPair`, so the sport and sign gates the
 * card has always had (#9006, #8617) decide for the page too. A sport whose
 * spread is not a margin (baseball's run line) answers null here and the page
 * falls back to the ladders, as before — the card prints nothing there.
 */

import type { Event } from "@/lib/types";
import { sportsbookProjectionDrawable } from "@/lib/scoreDifferentialHeading";

export interface ProjectedScorePair {
  home: number;
  away: number;
}

/**
 * The sportsbooks' projected pair off `current_odds`, or null when it is not a
 * scoreline for this sport.
 *
 * #9006 — "Proj 6--2" on a UFC card. The pair is solved from a spread point and
 * a total, so it is a score only where the sport's spread is a margin: this
 * asks `sportsbookProjectionDrawable`, the question the Sportsbooks table and
 * the Score Differential gate already ask (#8617), and a fight answers no. The
 * sign test is for every sport: no scoreboard reads below zero, so a negative
 * half means the inputs were not a points line.
 */
export function sportsbookProjectedPair(
  odds: Event["current_odds"] | null | undefined,
  sportKey: string | null | undefined,
): ProjectedScorePair | null {
  return odds &&
    odds.projected_home_score != null &&
    odds.projected_away_score != null &&
    odds.projected_home_score >= 0 &&
    odds.projected_away_score >= 0 &&
    sportsbookProjectionDrawable(sportKey ?? undefined)
    ? { home: odds.projected_home_score, away: odds.projected_away_score }
    : null;
}

/**
 * The raw (unrounded) pair the event page's `Projected final` line starts
 * from. Before kickoff: the card's sportsbook pair when there is one, so the
 * two print the same scoreline. Live, or with no drawable sportsbook pair: the
 * ladders' `pm_spread_data.projected_final`. The page's own gates (ties,
 * reachability, suspension, a live game with no score) still apply after this.
 *
 * `isLive` must be the card's own predicate — `status === "live"` and the start
 * time passed — because that is the one that decides whether the card prints
 * its projection.
 */
export function eventPageProjectedPair(opts: {
  odds: Event["current_odds"] | null | undefined;
  sportKey: string | null | undefined;
  isLive: boolean;
  ladderPair: { home_score: number; away_score: number } | null | undefined;
}): { home_score: number; away_score: number } | null {
  if (!opts.isLive) {
    const sportsbook = sportsbookProjectedPair(opts.odds, opts.sportKey);
    if (sportsbook) {
      return { home_score: sportsbook.home, away_score: sportsbook.away };
    }
  }
  return opts.ladderPair ?? null;
}
