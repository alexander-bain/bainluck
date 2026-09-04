/**
 * Keeping a set line pointed at the right player (CERT-913).
 *
 * The backend states a linescore in `home`/`away` columns, oriented to the
 * `sides` list it built the row with. Every consumer downstream is free to
 * re-order those sides, and two of them do:
 *
 *   * `matchListFromSlate` sorts the favourite first, so any row where the
 *     underdog was served first is displayed reversed;
 *   * `matchListFromBracket` joins the slate row on an ORDER-INSENSITIVE pair
 *     key and then renders the draw's own top/bottom, so roughly half of all
 *     joins adopt the opposite order.
 *
 * A positional score carried across either of those is an inverted result, and
 * an inverted result is the one failure mode this whole feature is built to
 * avoid — `orient_sides` refuses to guess it upstream, and refusing it there
 * only for it to be re-introduced two layers later would be a wasted refusal.
 *
 * So the line names the two entities its columns belong to, and this module is
 * the only thing that reads those names. Everything here is pure.
 */

import type { TennisLinescore, TennisLinescoreSet } from "./types";

/**
 * One set as a reader writes it — `6-3`, `7-6(4)`, `6-?`.
 *
 * A TypeScript twin of `tennis_linescore.format_set`, and it exists for one
 * reason: a FLIPPED line's `line` string cannot be the backend's, because the
 * backend's is home-first for the backend's home. Re-deriving it here is the
 * only way the string and the columns beside it can keep saying the same
 * thing.
 *
 * The parenthesis names the LOSER's tiebreak points, so it needs a loser —
 * a tiebreak still in progress prints `6-6` and no bracket, because with no
 * winner flag either number could be the loser's and a bracket on the wrong
 * side of a 7-5 tiebreak reads as the opposite result. A cell we could not
 * read prints `?` rather than `0`: the set is on the board, and dropping it
 * would slide every later set one place left.
 *
 * `linescore.test.ts` pins this against a real backend-produced `line` so the
 * two implementations cannot drift in silence.
 */
export function formatSet(set: TennisLinescoreSet): string {
  const home = set.home === null ? "?" : set.home;
  const away = set.away === null ? "?" : set.away;
  const text = `${home}-${away}`;
  const loserPoints =
    set.won_by === "home"
      ? set.away_tiebreak
      : set.won_by === "away"
        ? set.home_tiebreak
        : null;
  return loserPoints === null || loserPoints === undefined
    ? text
    : `${text}(${loserPoints})`;
}

/** Every set, home first — `"6-2, 6-7(4), 6-5"`. */
export function formatLine(sets: TennisLinescoreSet[]): string {
  return sets.map(formatSet).join(", ");
}

function flipSet(set: TennisLinescoreSet): TennisLinescoreSet {
  return {
    home: set.away,
    away: set.home,
    home_tiebreak: set.away_tiebreak,
    away_tiebreak: set.home_tiebreak,
    won_by: set.won_by === "home" ? "away" : set.won_by === "away" ? "home" : null,
  };
}

/**
 * The line with its columns pointed at `homeEntityKey` / `awayEntityKey`.
 *
 * Returns the line unchanged when it already points that way, a fully flipped
 * copy when it points the other way, and `null` in every other case —
 * including the case where the line states no entity keys at all.
 *
 * REFUSING IS THE SAFE DIRECTION AND IT IS DELIBERATE. An unorientable line
 * that we drop is a row that says nothing about the score, which is what the
 * row said before this feature existed. An unorientable line that we draw
 * anyway is a 6-4 4-6 2-1 attributed to the player who is losing, on a live
 * card, with nothing anywhere to contradict it. The first is a gap; the second
 * is the product lying, and `authority_linescore` already made this same
 * choice upstream for the same reason.
 */
export function orientLinescore(
  linescore: TennisLinescore | null | undefined,
  homeEntityKey: string | null | undefined,
  awayEntityKey: string | null | undefined,
): TennisLinescore | null {
  if (!linescore) return null;

  const lineHome = linescore.home_entity_key;
  const lineAway = linescore.away_entity_key;
  // No anchor is not "already correct" — it is "cannot be checked".
  if (!lineHome || !lineAway || !homeEntityKey || !awayEntityKey) return null;

  if (lineHome === homeEntityKey && lineAway === awayEntityKey) return linescore;
  if (lineHome !== awayEntityKey || lineAway !== homeEntityKey) return null;

  const sets = (linescore.sets ?? []).map(flipSet);
  return {
    ...linescore,
    sets,
    sets_won: { home: linescore.sets_won.away, away: linescore.sets_won.home },
    games: { home: linescore.games.away, away: linescore.games.home },
    line: formatLine(sets),
    // The point score and the server are columns too — a flipped line that
    // kept them would print the wrong player serving, which is the same defect
    // in a smaller font. `null` on every ESPN line, so this is for the StatPal
    // one the match page draws.
    points: linescore.points
      ? { home: linescore.points.away, away: linescore.points.home }
      : linescore.points,
    serving:
      linescore.serving === "home"
        ? "away"
        : linescore.serving === "away"
          ? "home"
          : linescore.serving,
    home_entity_key: lineAway,
    away_entity_key: lineHome,
  };
}
