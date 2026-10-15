/**
 * #10547 — the two teams' line colours on the event page, decided as a pair.
 * Moved here from `ProjectedFinalPointsChart` (#9483) so the win-probability
 * chart's paired team lines and the NFL game-story cards take the same pair as
 * the projected-points chart: one game never renders its teams in two
 * palettes.
 */

import { colorDistance } from "./probabilityBarPair";
import { hexToRgb, teamTextColor } from "./teamColors";

/**
 * #10547 — two team lines this close read as one line. Redmean distance, the
 * same instrument `probabilityBarPair` uses, but not its threshold: a bar half
 * is a block and 80 separates blocks, while these are 3px strokes that cross
 * each other. Bills `#00338D` / Patriots `#002244` measure 131, two NFL navies
 * that were one line at 390px on /events/14781135; navy against black is 136
 * and two reds 128. Royal blue against dark green (164) stays as supplied.
 */
export const MIN_LINE_PAIR_DISTANCE = 150;

/** What a team with no readable colour already gets here: the two text tokens (globals.css). */
const AWAY_FALLBACK = "#6B7280"; // --text-secondary
const HOME_FALLBACK = "#111827"; // --text-primary

/**
 * Where a too-close side goes: existing tokens a team name can be printed in
 * (every one clears `teamTextColor`'s 3:1 floor; a test asserts it). Not the
 * bar ladder's `#9CA3AF`, which is too faint to be text.
 */
export const LINE_RESCUE_COLORS = [
  AWAY_FALLBACK,
  "#4F46E5", // the bar ladder's indigo
  "#EF4444", // --accent-danger
  "#8B5CF6", // --accent-futures
  HOME_FALLBACK,
] as const;

function lineDistance(a: string, b: string): number {
  const [pa, pb] = [a, b].map((hex) => (hexToRgb(hex) ?? "0 0 0").split(" ").map(Number));
  return colorDistance([pa[0], pa[1], pa[2]], [pb[0], pb[1], pb[2]]);
}

function withHash(hex: string): string {
  const raw = hex.trim();
  return raw.startsWith("#") ? raw : `#${raw}`;
}

/**
 * #10547 — the two teams' colours, decided as a pair. The team name, its solid
 * projection and its dashed score all take the one colour returned here, so the
 * names above the plot stay the key to the lines.
 *
 * A readable supplied colour is kept unless the pair is too close. Then a real
 * colour is kept over a fallback and, between two real ones, the away side is
 * kept (arbitrary, but fixed, so one game never renders two ways). The other
 * side takes the rescue colour farthest from the kept one.
 */
export function projectedTeamStrokes(
  homeColor?: string | null,
  awayColor?: string | null,
): { home: string; away: string } {
  const homeReal = teamTextColor(homeColor);
  const awayReal = teamTextColor(awayColor);
  const home = homeReal ? withHash(homeReal) : HOME_FALLBACK;
  const away = awayReal ? withHash(awayReal) : AWAY_FALLBACK;
  if (lineDistance(home, away) >= MIN_LINE_PAIR_DISTANCE) return { home, away };
  const keepHome = !!homeReal && !awayReal;
  const kept = keepHome ? home : away;
  let best: string = LINE_RESCUE_COLORS[0];
  for (const c of LINE_RESCUE_COLORS) {
    if (lineDistance(c, kept) > lineDistance(best, kept)) best = c;
  }
  return keepHome ? { home, away: best } : { home: best, away };
}

