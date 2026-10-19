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
import { sportVocab } from "@/lib/marketMapUtils";
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
  odds: SportsbookProjectionFields | null | undefined,
  sportKey: string | null | undefined,
): ProjectedScorePair | null {
  return odds &&
    odds.projected_home_score != null &&
    odds.projected_away_score != null &&
    Number.isFinite(odds.projected_home_score) &&
    Number.isFinite(odds.projected_away_score) &&
    odds.projected_home_score >= 0 &&
    odds.projected_away_score >= 0 &&
    sportsbookProjectionDrawable(sportKey ?? undefined) &&
    projectedFinalFormat(sportKey) !== null
    ? { home: odds.projected_home_score, away: odds.projected_away_score }
    : null;
}

/** The two keys this file reads. `Event.current_odds` and the feed's leaner
 *  `current_odds` both satisfy it; the feed's are optional because `/api/feed`
 *  does not serve them yet (the card stays silent until it does). */
export interface SportsbookProjectionFields {
  projected_home_score?: number | null;
  projected_away_score?: number | null;
}

/**
 * #2920 / #9483 — WHICH SPORTS' SPORTSBOOK PAIR IS A FINAL SCORE, AND IN WHAT.
 *
 * The pair is solved from a spread point and a total, so it is a scoreline only
 * where both are quoted in the unit the scoreboard counts and the spread moves
 * with the matchup. Admitted on real fixtures (production search payloads,
 * 2026-10-19):
 *
 *   americanfootball_*  points  NFL 14780563 −7.3 / 51.9 → 29.6 – 22.3
 *   basketball_*        points  NBA 15195969 −5.5 / 234.8 → 120.2 – 114.7
 *   soccer_*            goals   EPL 15315510 0.0 / 2.5 → 1.2 – 1.2 — the
 *                               markets settle on 90 minutes, so the label says so
 *
 * Everything else answers null, and that is a statement, not a gap to fill:
 *
 *   baseball_*    the run line is pinned at ±1.5 (#8617 — Mets @ Rangers 5.0 – 3.5)
 *   icehockey_*   the puck line is pinned the same way: NHL 15333056 and 15332424
 *                 both −1.5 → "4 – 3" and "4 – 3" whatever the price; AHL
 *                 15327140 served 1.5 / 1.5 → 0.0 – 1.5
 *   tennis_*      a games spread and total under a SETS scoreboard (Shanghai
 *                 15326853 → 11.2 – 11.3 over a 0 – 2 match)
 *   mma / boxing  a rounds total (#9006 — "Proj 6--2")
 *   golf, racing  a field, not two sides
 *   cricket, esports, rugby, Aussie rules, everything undeclared — no measured
 *                 fixture says the spread is a margin in a scoreboard unit
 *
 * The event page's in-game pair comes from the prediction-market ladders and
 * keeps its own gate (`hasDerivedSpread`); this table decides the SPORTSBOOK
 * pair, which is the only one a card can read.
 */
export interface ProjectedFinalFormat {
  unit: "points" | "goals";
  /** The visible label. Always begins "Projected final". */
  label: string;
}

const PROJECTED_FINAL_FORMATS: { prefix: string; format: ProjectedFinalFormat }[] = [
  { prefix: "americanfootball_", format: { unit: "points", label: "Projected final" } },
  { prefix: "basketball_", format: { unit: "points", label: "Projected final" } },
  { prefix: "soccer_", format: { unit: "goals", label: "Projected final (90 min)" } },
];

export function projectedFinalFormat(
  sportKey: string | null | undefined,
): ProjectedFinalFormat | null {
  const key = (sportKey ?? "").toLowerCase();
  if (!key) return null;
  return PROJECTED_FINAL_FORMATS.find((row) => key.startsWith(row.prefix))?.format ?? null;
}

/** The label the event page prints over whichever pair it holds. */
export function projectedFinalLabel(sportKey: string | null | undefined): string {
  return projectedFinalFormat(sportKey)?.label ?? "Projected final";
}

/**
 * The sportsbook pair as a CARD prints it: rounded per side exactly as the event
 * page rounds it, and refused where the page refuses it before kickoff — a half
 * at zero, or a level scoreline in a sport that cannot end level (#8156). The
 * page's live-only gates (#4885, #5697) have nothing to test on a pre-game card.
 */
export function cardProjectedFinal(
  odds: SportsbookProjectionFields | null | undefined,
  sportKey: string | null | undefined,
): ProjectedScorePair | null {
  const pair = sportsbookProjectedPair(odds, sportKey);
  if (!pair || pair.home <= 0 || pair.away <= 0) return null;
  const home = Math.round(pair.home);
  const away = Math.round(pair.away);
  if (home === away && !sportVocab(sportKey ?? undefined).canEndInATie) return null;
  return { home, away };
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
 *
 * Before kickoff, a sport whose sportsbook spread IS a margin but whose format
 * this file refuses (hockey's pinned puck line) answers null, not the ladders:
 * the forecast is withheld, never swapped for another source while the card
 * one tap back prints nothing. Baseball's run line is not a margin at all, so
 * it keeps its ladder fallback (#8617).
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
    if (
      sportsbookProjectionDrawable(opts.sportKey ?? undefined) &&
      projectedFinalFormat(opts.sportKey) === null
    ) {
      return null;
    }
  }
  return opts.ladderPair ?? null;
}
