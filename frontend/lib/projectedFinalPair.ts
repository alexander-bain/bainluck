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
 * heaviest source in the blend. Before kickoff the card prints the sportsbook
 * pair and so does the page. Live, both read the producer's marked in-play pair
 * (`admittedLiveProjection`, #2920); without one the card prints nothing and
 * the page keeps the ladders' in-game pair.
 *
 * Both halves read `sportsbookProjectedPair`, so the sport and sign gates the
 * card has always had (#9006, #8617) decide for the page too. A sport whose
 * spread is not a margin (baseball's run line) answers null here and the page
 * falls back to the ladders, as before — the card prints nothing there.
 */

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
  /** #2920 — the producer's in-play pair (D3). Not served yet, so not declared
   *  on a payload type; `admittedLiveProjection` checks every field. */
  live_projection?: unknown;
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
 * #2920 / #9483 — A LIVE GAME'S PROJECTED FINAL: ONE IN-PLAY PAIR, MARKED AS ONE.
 *
 * A live card and the event page one tap away must print the same forecast or
 * none. Before play that is the sportsbook pair above. Live, the bare
 * `current_odds.projected_*` keys cannot be trusted to be live: on
 * `/api/events/{id}` and search they come through the stale filter, which
 * falls back to EVERY book when none has quoted since the start
 * (`filter_stale_bookmaker_snapshots`), so a pregame pair can ride a live game
 * with nothing to say so. The list routes' own pair (`card_projected_pair`)
 * does test that, but the page cannot tell which pair it was handed, and its
 * `captured_at` is not the confirmation time the test reads.
 *
 * So a live surface reads ONLY `current_odds.live_projection`: the producer's
 * in-play pair, served on the detail, search, feed and league routes alike and
 * only when every contributing row was confirmed at or after the start
 * (release-root dependency D3, 2026-10-20). Until it is served this answers
 * null everywhere: the cards stay silent and the page keeps its ladder pair.
 * Every field is checked here because none is declared by a payload type yet.
 *
 * What it admits, each refused rather than guessed:
 *
 *   - KIND `in_play`, measured from `commence_time`, and the evidence agrees:
 *     the earliest confirmation is not before the start. A pregame reading is
 *     never relabelled as a live one.
 *   - The start it was measured from is not before the start THIS ROW carries:
 *     an object measured from an earlier start (cached, or the start moved
 *     later) could pass pregame quotes off as in play.
 *   - The latest capture must be present, and is compared with nothing: a
 *     quote first captured before the start and reconfirmed after it is an
 *     honest in-play reading, so it may precede the boundary and the earliest
 *     confirmation. The only ordering gates use confirmation time.
 *   - SOURCE / BASIS: the sportsbooks' spread-and-total pair, the only one the
 *     rounding path below solves.
 *   - UNIT and PERIOD the scoreboard counts in: points over the full game for
 *     football and basketball; goals over 90 minutes for soccer, whose lines
 *     settle on regulation (the producer withholds it once extra time starts).
 *   - The sport table, sign gate and level-score refusal of `cardProjectedFinal`.
 *
 * Hockey, baseball, tennis, fights and every undeclared sport answer null, as
 * they do before play. No freshness timeout is chosen here: currentness is the
 * producer's evidence, and lifecycle is the caller's existing predicate.
 */
export const LIVE_PROJECTION_KIND_IN_PLAY = "in_play";

export interface LiveProjection {
  projected_home_score: number;
  projected_away_score: number;
  kind: typeof LIVE_PROJECTION_KIND_IN_PLAY;
  boundary: "commence_time";
  boundary_at: string;
  earliest_confirmed_at: string;
  latest_captured_at: string;
  source: "sportsbooks";
  basis: "consensus_spread_total";
  bookmaker_count: number;
  unit: ProjectedFinalFormat["unit"];
  period: "full_game" | "regulation";
}

/** The period each admitted unit's sportsbook lines settle on. */
export function projectedFinalPeriod(
  sportKey: string | null | undefined,
): LiveProjection["period"] | null {
  const format = projectedFinalFormat(sportKey);
  if (!format) return null;
  return format.unit === "goals" ? "regulation" : "full_game";
}

function liveInstant(value: unknown): number | null {
  if (typeof value !== "string" || value === "") return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/**
 * The raw in-play pair `current_odds.live_projection` carries, or null when
 * any part of it fails. Raw, so the event page can apply its own gates to it
 * exactly as it does to the ladder pair; a card goes through
 * `liveCardProjectedFinal`.
 */
export function admittedLiveProjection(
  odds: SportsbookProjectionFields | null | undefined,
  sportKey: string | null | undefined,
  commenceTime: string | null | undefined,
): ProjectedScorePair | null {
  const p = odds?.live_projection as Partial<LiveProjection> | null | undefined;
  if (!p || typeof p !== "object") return null;
  if (p.kind !== LIVE_PROJECTION_KIND_IN_PLAY) return null;
  if (p.boundary !== "commence_time") return null;
  if (p.source !== "sportsbooks") return null;
  if (p.basis !== "consensus_spread_total") return null;

  const format = projectedFinalFormat(sportKey);
  if (!format || p.unit !== format.unit) return null;
  if (p.period !== projectedFinalPeriod(sportKey)) return null;

  if (typeof p.bookmaker_count !== "number" || !Number.isInteger(p.bookmaker_count) || p.bookmaker_count < 1) {
    return null;
  }
  const boundary = liveInstant(p.boundary_at);
  const earliest = liveInstant(p.earliest_confirmed_at);
  const latest = liveInstant(p.latest_captured_at);
  const rowStart = liveInstant(commenceTime);
  if (boundary === null || earliest === null || latest === null || rowStart === null) return null;
  if (boundary < rowStart) return null;
  if (earliest < boundary) return null;

  return sportsbookProjectedPair(
    { projected_home_score: p.projected_home_score, projected_away_score: p.projected_away_score },
    sportKey,
  );
}

/**
 * The in-play pair as a LIVE CARD prints it, or null. On top of
 * `admittedLiveProjection` and the card rounding, the gates the event page
 * applies once a game is underway (#5697, #4885): an actual score pair must be
 * on the card to read the forecast against, and each rounded half must be
 * reachable from it — goals and points are never taken back.
 *
 * The caller passes its own live predicate's answer by calling this only for a
 * live, not-suspended card; this file does not read the clock.
 */
export function liveCardProjectedFinal(
  odds: SportsbookProjectionFields | null | undefined,
  sportKey: string | null | undefined,
  commenceTime: string | null | undefined,
  actual: { home: number | null | undefined; away: number | null | undefined },
): ProjectedScorePair | null {
  const { home, away } = actual;
  if (typeof home !== "number" || !Number.isFinite(home) || home < 0) return null;
  if (typeof away !== "number" || !Number.isFinite(away) || away < 0) return null;
  const raw = admittedLiveProjection(odds, sportKey, commenceTime);
  if (!raw) return null;
  const pair = cardProjectedFinal(
    { projected_home_score: raw.home, projected_away_score: raw.away },
    sportKey,
  );
  if (!pair || pair.home < home || pair.away < away) return null;
  return pair;
}

/**
 * The raw (unrounded) pair the event page's `Projected final` line starts
 * from. Before kickoff: the card's sportsbook pair when there is one, so the
 * two print the same scoreline. Live: the in-play pair the live card reads
 * (`admittedLiveProjection`) when it is admitted; when the producer served one
 * and it is refused, nothing — withheld, never swapped for the ladders while
 * the card one tap back reads the same object and prints nothing. Live with no
 * in-play pair served, or with no drawable sportsbook pair: the ladders'
 * `pm_spread_data.projected_final`, as before; the card prints nothing then,
 * so the two never print two different finals. The page's own gates (ties,
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
  odds: SportsbookProjectionFields | null | undefined;
  sportKey: string | null | undefined;
  /** The row's `commence_time`, which the in-play pair must be measured from. */
  commenceTime: string | null | undefined;
  isLive: boolean;
  ladderPair: { home_score: number; away_score: number } | null | undefined;
}): { home_score: number; away_score: number } | null {
  if (opts.isLive) {
    const live = admittedLiveProjection(opts.odds, opts.sportKey, opts.commenceTime);
    if (live) return { home_score: live.home, away_score: live.away };
    if (opts.odds?.live_projection != null) return null;
  } else {
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
