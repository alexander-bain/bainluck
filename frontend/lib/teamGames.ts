/**
 * Pure helpers for team-page game cards (L2-158).
 *
 * These encode the "state honesty" rules from the team-page dogfood round:
 *  - a game is LIVE only if the backend says live AND it has actually started
 *    (a future commence_time must never render a LIVE chip — gotcha #14: the
 *    backend status writer can flip 'live' hours before first pitch);
 *  - settled games arrive as EITHER 'completed' OR 'closed';
 *  - doubleheaders (two games vs the same opponent on the same calendar day)
 *    render as distinct G1/G2 cards.
 *
 * Kept SSR-safe and side-effect-free so they can be unit-tested and used in
 * both the client component and any future server render.
 */
import type { TeamGameBrief } from "./api";

type LiveInput = Pick<TeamGameBrief, "status" | "commence_time">;

/** A game is LIVE only when status says live AND commence_time is in the past. */
export function isGameLive(game: LiveInput, now: number = Date.now()): boolean {
  if (game.status !== "live") return false;
  if (!game.commence_time) return false;
  const started = new Date(game.commence_time).getTime();
  if (Number.isNaN(started)) return false;
  return started <= now;
}

/** Settled games can be either 'completed' or 'closed' — treat both as final. */
export function isGameSettled(game: Pick<TeamGameBrief, "status">): boolean {
  return game.status === "completed" || game.status === "closed";
}

/** Local calendar-day key (YYYY-M-D) used to group doubleheaders. */
function dayKey(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/**
 * Assign 1-based game numbers to doubleheaders. Only games that share an
 * opponent AND calendar day with at least one sibling get a number; solo games
 * are omitted from the map (so the caller renders no G-chip for them).
 * Ordering within a day is by commence_time ascending.
 */
export function assignGameNumbers(games: TeamGameBrief[]): Record<number, number> {
  const groups = new Map<string, TeamGameBrief[]>();
  for (const g of games) {
    const dk = dayKey(g.commence_time);
    if (!dk) continue;
    const key = `${(g.opponent || "").toLowerCase()}|${dk}`;
    const arr = groups.get(key) ?? [];
    arr.push(g);
    groups.set(key, arr);
  }

  const out: Record<number, number> = {};
  for (const arr of groups.values()) {
    if (arr.length < 2) continue;
    const sorted = [...arr].sort(
      (a, b) =>
        new Date(a.commence_time || 0).getTime() -
        new Date(b.commence_time || 0).getTime(),
    );
    sorted.forEach((g, i) => {
      out[g.id] = i + 1;
    });
  }
  return out;
}

/**
 * Team-relative result for a settled game. Returns null when scores are absent.
 * `is_home` selects which side is "us".
 */
export function teamResult(
  game: Pick<TeamGameBrief, "home_score" | "away_score" | "is_home">,
): { char: "W" | "L" | "T"; teamScore: number; oppScore: number } | null {
  const { home_score, away_score, is_home } = game;
  if (home_score === null || away_score === null) return null;
  const teamScore = is_home ? home_score : away_score;
  const oppScore = is_home ? away_score : home_score;
  const char = teamScore > oppScore ? "W" : teamScore < oppScore ? "L" : "T";
  return { char, teamScore, oppScore };
}
