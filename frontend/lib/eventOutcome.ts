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

import { formatLinescore } from "./marketMapUtils";
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
  /**
   * The per-period line the event itself carries, in home/away order
   * (`Event.linescore`, live/073).
   *
   * On a tennis match `homeScore`/`awayScore` are SETS, so rung 1's rule that
   * the numbers are already on screen holds for the count and not for the
   * result: `0` and `3` under the two players do not say `6-3, 6-4, 6-1`.
   */
  linescore?: { sets: [number, number][] } | null;
}

/**
 * `"6-3, 1-4"` — the games under a hero that is printing SETS, WHILE IT IS
 * STILL BEING PLAYED. `""` whenever the hero must not print one (#3330).
 *
 * The live counterpart of `resolveEventOutcome`'s `resultLine`, and it lives
 * beside it because the two answer one question in two tenses and the page
 * must never be able to ask them differently.
 *
 * ── WHY THE HERO NEEDS IT ────────────────────────────────────────────────────
 *
 * Alex, `/events/15304419` at 5-5 in the first set: the hero printed `0` and
 * `0`. Zero sets each is TRUE, and it is the least informative true statement
 * available — indistinguishable from a match that has not started, on a page
 * whose Games map four sections down was already drawing 11 played games.
 * `/events/15304420` is the sharper exhibit: `1 – 0` in sets while that player
 * was losing the second set 1-4, so the two big numbers were not merely thin,
 * they pointed the wrong way about where the match was going.
 *
 * ── ORDER IS HOME-FIRST, AND IT IS GUARANTEED UPSTREAM, NOT ASSUMED HERE ─────
 *
 * `sets` is stated in OUR home/away order: `authority_games_line` orients
 * ESPN's competitors onto our two names through `orient_sides` and REFUSES
 * (`SCORE_ORIENTATION_UNRESOLVED`) rather than guess, so a stored line cannot
 * be back-to-front. The event hero renders home left and away right
 * unconditionally, so the line is printed unreversed and reads straight across
 * the two columns.
 *
 * This is deliberately NOT `lib/linescore.ts`'s `orientLinescore`. That helper
 * exists because the tournament SLATE re-orders its sides (`matchListFromSlate`
 * sorts favourite-first, `matchListFromBracket` joins order-insensitively), so
 * a slate row has to re-point the line by entity key. This payload carries no
 * entity keys — `routes/events.py` serves the bare line — so that helper would
 * refuse every row and the hero would print nothing at all. Two surfaces, two
 * different guarantees; using the slate's helper here would be a refusal
 * dressed as safety.
 *
 * ── WHY IT REFUSES A FINISHED MATCH ──────────────────────────────────────────
 *
 * Not because a finished match has no line, but because it already has one:
 * `resolveEventOutcome` prints it WINNER-first under the winner's name. A live
 * match has no winner, so home-first is the only order its columns can be read
 * in — and returning a line here too would print the same games twice, in two
 * different orders, on one hero.
 */
export function liveHeroGamesLine(input: {
  isFinished: boolean;
  /** The hero shows scores only once the match is under way. */
  isLive: boolean;
  hasStarted: boolean;
  linescore?: { sets: [number, number][] } | null;
}): string {
  if (input.isFinished) return "";
  if (!input.isLive && !input.hasStarted) return "";
  return formatLinescore(input.linescore?.sets);
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
    // live/073: the line, WHERE THE TWO NUMBERS ON SCREEN ARE NOT THE RESULT.
    //
    // Rung 1 has always returned `resultLine: null` on the rule that a
    // basketball hero already prints 112 and 108 and repeating them is
    // duplication. A tennis hero prints `0` and `3` — the SETS — and
    // `6-3, 6-4, 6-1` is not those numbers again, it is the answer to the
    // question they raise. So the line is printed exactly when we hold one,
    // and every sport that does not stays byte-for-byte as it was.
    //
    // Winner's games first, matching the tournament page's line and
    // `espn_tennis.format_score`, and the winner comes from the SET score
    // rather than from the games: the loser can finish with more games.
    const sets = input.linescore?.sets;
    const line =
      sets && sets.length > 0
        ? formatLinescore(sets, { reversed: winnerSide === "away" })
        : null;
    return {
      winnerName: team.split(" ").pop() || team,
      winnerSide,
      resultLine: line,
      resultExplanation: line ? `${line}, winner's games first.` : null,
      resultKind: line ? "score" : null,
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
