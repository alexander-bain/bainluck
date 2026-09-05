/**
 * Keeping a set line pointed at the right player (live/063, #2746).
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
 * an inverted result is the one failure this whole feature has to avoid:
 * `espn_tennis_anchor.orient_sides` refuses to guess an orientation upstream,
 * and refusing it there only for it to be re-introduced two layers later would
 * be a wasted refusal.
 *
 * So the line names the two entities its columns belong to, and this module is
 * the only thing that reads those names. Everything here is pure.
 */

/**
 * One tennis match's games, as `tournament_slate._linescore_field` states them.
 *
 * `sets` is `[home_games, away_games]` per set, IN PLAY ORDER, and it is the
 * whole of what ESPN's scoreboard publishes for a match still being played —
 * there is no per-set winner flag and no tiebreak detail on this rail, so
 * neither is modelled here. A field nothing can fill is a promise the renderer
 * would keep checking for.
 *
 * `home_games` / `away_games` are the totals across those sets, which is the
 * unit a game-total market quotes.
 */
export interface SlateLinescore {
  sets: [number, number][];
  home_games: number | null;
  away_games: number | null;
  home_entity_key: string;
  away_entity_key: string;
  source?: string;
}

/** Every set, home first — `"6-4, 2-1"`. Empty for a line with no sets. */
export function formatLinescore(linescore: SlateLinescore | null): string {
  if (!linescore) return "";
  return (linescore.sets ?? []).map(([home, away]) => `${home}-${away}`).join(", ");
}

/**
 * The line with its columns pointed at `homeEntityKey` / `awayEntityKey`.
 *
 * Returns the line unchanged when it already points that way, a fully flipped
 * copy when it points the other way, and `null` in every other case —
 * including the case where the line states no entity keys at all.
 *
 * REFUSING IS THE SAFE DIRECTION AND IT IS DELIBERATE. An unorientable line we
 * drop is a row that says nothing about the score, which is exactly what the
 * row said before this shipped. An unorientable line we draw anyway is a
 * `6-4, 2-1` attributed to the player who is losing, on a live card, with
 * nothing anywhere on the page to contradict it. The first is a gap; the second
 * is the product lying, and the backend already made this same choice upstream
 * for the same reason.
 */
export function orientLinescore(
  linescore: SlateLinescore | null | undefined,
  homeEntityKey: string | null | undefined,
  awayEntityKey: string | null | undefined,
): SlateLinescore | null {
  if (!linescore) return null;

  const lineHome = linescore.home_entity_key;
  const lineAway = linescore.away_entity_key;
  // No anchor is not "already correct" — it is "cannot be checked".
  if (!lineHome || !lineAway || !homeEntityKey || !awayEntityKey) return null;

  if (lineHome === homeEntityKey && lineAway === awayEntityKey) return linescore;
  if (lineHome !== awayEntityKey || lineAway !== homeEntityKey) return null;

  return {
    ...linescore,
    sets: (linescore.sets ?? []).map(([home, away]) => [away, home]),
    home_games: linescore.away_games,
    away_games: linescore.home_games,
    home_entity_key: lineAway,
    away_entity_key: lineHome,
  };
}
