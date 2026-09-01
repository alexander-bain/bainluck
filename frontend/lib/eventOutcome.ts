/**
 * WHO WON, AND BY WHAT — FOR AN EVENT IN ANY SPORT (#2443).
 *
 * ═══ THE DEFECT ═══
 *
 * Alex, reading `/events/15293846` on 2026-08-31: the page renders the `FINAL`
 * badge and the two players and **nowhere states the winner or the score**,
 * while the tournament page one click away shows the same match as
 * `7-6, 7-6, 6-0`. His words: the single most obviously broken thing on it.
 *
 * The cause is one line of the hero. Its settled treatment derived the winner
 * from `home_score > away_score`, so a settled event whose result is not a pair
 * of integers — a tennis match, and every other sport scored in its own units —
 * fell through to a bare "Final". The event row genuinely has
 * `home_score = null, away_score = null`; there is no number to print.
 *
 * ═══ WHY THIS IS NOT A TENNIS FIX ═══
 *
 * Alex's standing constraint on this issue set is that the work must accrue to
 * all future tournaments, so the repair is not "read tennis scores". It is that
 * **naming the outcome is a job with more than one authority**, and the hero
 * should ask them in order rather than know about one of them:
 *
 *   1. the event's own final score, which is how every score-based sport
 *      settles and which keeps its current behaviour exactly; then
 *   2. the container the event belongs to, which for a registered tournament
 *      in ANY sport already carries a decided result — winner, score line and
 *      how it ended — through `/api/tournaments/by-event/{id}`.
 *
 * A third authority (a settled match-winner market, a provider result feed)
 * appends to the ladder without touching the hero.
 *
 * ═══ THE DATA WAS ALREADY THERE ═══
 *
 * `EventTournamentResponse.result` is served today and nothing read it: the
 * event page's only consumer of that payload is `TournamentExtensions`, which
 * renders advancement and props and skips the result, and the field was not
 * even declared on the TypeScript interface. So this ships no new endpoint and
 * no new query — it reads a field production has been returning all along,
 * through the SAME SWR key the extensions section already uses, which is why
 * the hero costs no extra request.
 */

import {
  resultScoreLine,
  type ScoreLineKind,
  type TournamentResult,
} from "./tournamentResults";

/**
 * Which sport keys can possibly sit in a tournament container.
 *
 * A prefix test and not the server's exact list: the client must not carry a
 * second copy of `REGISTERED_TOURNAMENTS` that goes stale the day a second
 * tournament is registered. Over-asking is one cheap `null` answer;
 * under-asking is a section that silently stops appearing.
 *
 * Lives here rather than in `TournamentExtensions` because the hero and the
 * extensions must gate IDENTICALLY. Two copies of this regex is two chances to
 * fire one request and not the other, which shows up as a hero that says
 * "Final" above a section that knows the score.
 */
export const TOURNAMENT_SPORT_KEY = /^tennis_(atp|wta)_/;

export function isTournamentSportKey(sportKey?: string | null): boolean {
  return !!sportKey && TOURNAMENT_SPORT_KEY.test(sportKey);
}

/**
 * The one SWR key both consumers use, so the second one is a cache hit.
 *
 * Exported as a function rather than written out at each call site for the
 * same reason the regex is shared: a key that differs by a character is a
 * duplicate request that still works, and therefore never gets noticed.
 */
export function eventTournamentKey(eventId: number): [string, number] {
  return ["event-tournament", eventId];
}

/** Which authority named the winner — reported so a guard can assert the rung. */
export type OutcomeAuthority = "score" | "tournament";

export interface SettledOutcome {
  /** The name the hero prints, already shortened the way that source shortens. */
  winnerName: string;
  /**
   * Which side of the event won, or `null` when the naming authority does not
   * line up with either team. Drives the "were N% pregame" mark, which must
   * stay silent rather than guess a side.
   */
  winnerSide: "home" | "away" | null;
  /**
   * The result in the sport's own units — `7-6, 7-6, 6-0`, `walkover`.
   *
   * `null` when the numbers are already on screen: a basketball hero prints
   * 112 and 108 under the two teams, and repeating "112-108" in the middle is
   * the duplication L2-112 removed from this same hero.
   */
  resultLine: string | null;
  /** The full sentence for a tooltip and a screen reader. */
  resultExplanation: string | null;
  /** `score` | `retired` | `walkover` | `absent`, so styling never matches on English. */
  resultKind: ScoreLineKind | null;
  authority: OutcomeAuthority;
}

/**
 * Names compared the way a reader would, not the way a database would.
 *
 * Diacritics are stripped because the two sides of this comparison come from
 * different providers — the event row's `home_team` is the Odds API's spelling
 * and the result's `display_name` is ESPN's — and "Carlos Alcaraz" vs "Carlos
 * Alcaráz" is not a disagreement about who played.
 */
function normalizeName(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/**
 * The surname a PERSON is known by — `Carballes Baena`, not `Baena`.
 *
 * Deliberately different from the `split(" ").pop()` the hero applies to a
 * TEAM, and the difference is not cosmetic in either direction: `.pop()` on a
 * two-part Spanish surname drops half of it, and `slice(1)` on "Los Angeles
 * Lakers" yields "Angeles Lakers". Each rule is right for its own kind of
 * competitor, so the resolver picks by authority rather than picking one and
 * living with the wrong half of the cases.
 */
function surnameOf(displayName: string): string {
  return displayName.split(" ").slice(1).join(" ") || displayName;
}

/** Does this result player refer to the event's home or away side? */
function sideOfPlayer(
  displayName: string,
  entityKey: string,
  homeTeam: string,
  awayTeam: string
): "home" | "away" | null {
  const player = normalizeName(displayName);
  const fromKey = normalizeName(entityKey);
  const home = normalizeName(homeTeam);
  const away = normalizeName(awayTeam);
  if (player === home || fromKey === home) return "home";
  if (player === away || fromKey === away) return "away";
  // A surname-only fall-back, for the provider that abbreviates a forename
  // ("M. Berrettini"). Only accepted when exactly ONE side matches, because a
  // sibling pair or two players sharing a surname is precisely the case where
  // a confident guess prints the wrong person's name in the biggest type on
  // the page.
  const surname = normalizeName(surnameOf(displayName));
  const homeHit = home.endsWith(` ${surname}`) || home === surname;
  const awayHit = away.endsWith(` ${surname}`) || away === surname;
  if (homeHit && !awayHit) return "home";
  if (awayHit && !homeHit) return "away";
  return null;
}

export interface EventOutcomeInput {
  /** Only a finished event has an outcome; a live one has a state. */
  isFinished: boolean;
  homeTeam: string;
  awayTeam: string;
  /** The best-known final scores, already reconciled against chart history. */
  homeScore: number | null;
  awayScore: number | null;
  /** The container's decided result, when the event sits in one. */
  tournamentResult?: TournamentResult | null;
}

/**
 * The settled outcome, or `null` when nothing authoritative names a winner.
 *
 * `null` is a real answer and the caller must keep its honest "Final" for it —
 * a drawn match, a result we have not ingested, and an event still being
 * graded all reach here, and none of them may be resolved by inference.
 */
export function resolveEventOutcome(
  input: EventOutcomeInput
): SettledOutcome | null {
  const { isFinished, homeTeam, awayTeam, homeScore, awayScore } = input;
  if (!isFinished) return null;

  // Rung 1 — the event's own numbers. Unchanged from the behaviour every
  // score-based sport has today, including the tie, which returns `null` so
  // the hero prints "Final · Tied" rather than crowning the home side.
  if (homeScore !== null && awayScore !== null && homeScore !== awayScore) {
    const winnerSide = homeScore > awayScore ? "home" : "away";
    const team = winnerSide === "home" ? homeTeam : awayTeam;
    return {
      winnerName: team.split(" ").pop() || team,
      winnerSide,
      resultLine: null,
      resultExplanation: null,
      resultKind: null,
      authority: "score",
    };
  }

  // Rung 2 — the container. Any registered tournament, any sport.
  const result = input.tournamentResult;
  if (result) {
    const winner =
      result.players.find((p) => p.is_winner) ??
      result.players.find((p) => p.entity_key === result.winner_entity_key);
    if (winner) {
      const line = resultScoreLine(result);
      return {
        winnerName: surnameOf(winner.display_name),
        winnerSide: sideOfPlayer(
          winner.display_name,
          winner.entity_key,
          homeTeam,
          awayTeam
        ),
        // An absent score is reported as absent, never as a blank: "the source
        // gave a winner and no sets" is a different thing from "we did not
        // look", and `resultScoreLine` already draws that line for the
        // tournament page. Reusing it is what keeps the two surfaces from
        // wording the same fact two ways.
        resultLine: line.text,
        resultExplanation: line.explanation,
        resultKind: line.kind,
        authority: "tournament",
      };
    }
  }

  return null;
}
