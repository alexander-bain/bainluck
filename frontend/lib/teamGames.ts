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
import { hasNoReportedResult } from "./eventState";

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

/**
 * The clock ran out and nothing that watches the match said it ended (live/048).
 *
 * 🔴 IT IS IN THE RECENTS LIST NOW, AND THAT IS WHY THIS EXISTS (live/056). The
 * team page's recent rail used to select only `completed`/`closed`, and the
 * other rail is live/scheduled floored at `now - 2h` — a match is suspended
 * precisely because hours have passed, so it appeared on NEITHER of its two
 * teams' pages. Making it visible is the ship; this predicate is what stops the
 * fix from re-introducing the lie live/048 removed, because a suspended row
 * arrives carrying a PARTIAL score and every other consumer of that rail treats
 * a score as a result.
 *
 * Delegates rather than re-testing the literal: `lib/eventState` is the one
 * place that knows the vocabulary, and a second `=== "suspended"` here is
 * exactly the per-surface chain CERT-786 blocked on.
 *
 * 🔴 AND #3211, THE SAME PARAGRAPH ONE STATUS LATER. `routes/teams.py`'s recent
 * rail now also returns a row that still says `scheduled` more than two hours
 * past its own kickoff — the third state to fall between that page's two rails
 * and appear on neither. It reaches this predicate rather than a new one for
 * the reason `lib/eventState.hasNoReportedResult` gives: a reader is being told
 * either a start time or that no result was reported, and the right answer is
 * the same for both states.
 *
 * Such a row carries NO score at all, where a suspended one carries a partial
 * — so it lands on the score-less arm of the handling live/056 already built,
 * and there is nothing further for `RecentGameCard` to learn.
 */
export function isGameSuspended(
  game: Pick<TeamGameBrief, "status" | "commence_time">,
  now: number = Date.now(),
): boolean {
  return hasNoReportedResult(game.status, game.commence_time, now);
}

/** Local calendar-day key (YYYY-M-D) used to group doubleheaders. */
function dayKey(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/**
 * Leagues where two games against the same opponent on one calendar day is a
 * real thing that happens. Today that is baseball and nothing else.
 *
 * An ALLOWLIST, deliberately, not a "not NFL" denylist: a denylist silently
 * re-breaks for every league added later, and the failure mode is a lie told
 * confidently (see below). Matched case-insensitively against the `league`
 * route segment.
 */
const DOUBLEHEADER_LEAGUES = new Set(["mlb"]);

/**
 * Assign 1-based game numbers to doubleheaders. Only games that share an
 * opponent AND calendar day with at least one sibling get a number; solo games
 * are omitted from the map (so the caller renders no G-chip for them).
 * Ordering within a day is by commence_time ascending.
 *
 * **`league` is required, and outside {@link DOUBLEHEADER_LEAGUES} the answer is
 * always `{}` (#2866).** Ungated, this function was the last step that turned a
 * DATA defect into a plausible product feature: the Bears page carried
 * `@ Tennessee Titans G1` and `@ Tennessee Titans G2`, same day, same 24–15
 * result — five cards for three real games — because 47 of 50 NFL preseason
 * rows exist twice and this grouped them into a "doubleheader". NFL teams do
 * not play twice in a day, so the chips were not describing the schedule, they
 * were explaining away a duplicate.
 *
 * **This does not fix the duplicate and must not be read as fixing it.** The
 * pair still renders twice; it just no longer arrives dressed as deliberate.
 * The data half is `matching-symptom` under D35 and belongs to #2693.
 */
export function assignGameNumbers(
  games: TeamGameBrief[],
  league: string,
): Record<number, number> {
  if (!DOUBLEHEADER_LEAGUES.has((league || "").toLowerCase())) return {};

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
 *
 * 🔴 A SCORE IS NOT A RESULT, AND `status` IS REQUIRED SO A CALLER CANNOT
 * FORGET THAT (live/056). Two numbers are enough to compute a W/L and they are
 * not enough to CLAIM one: a suspended match carries the last score play
 * reached, and 1-2 in a match nobody said had ended is a snapshot, not a loss.
 * Grading it prints the false Final live/048 was built to remove, one component
 * to the left of where that fix landed.
 *
 * The refusal is HERE rather than at the card because this is the function that
 * mints the verdict. Guarding at the render leaves the next surface to
 * rediscover the rule, which is the shape of CERT-786's four-surface finding;
 * guarding at the source makes `status` a required argument, so a new caller is
 * a compile error rather than a quiet wrong answer.
 */
export function teamResult(
  game: Pick<TeamGameBrief, "home_score" | "away_score" | "is_home" | "status">,
): { char: "W" | "L" | "T"; teamScore: number; oppScore: number } | null {
  const { home_score, away_score, is_home } = game;
  if (!isGameSettled(game)) return null;
  if (home_score === null || away_score === null) return null;
  const teamScore = is_home ? home_score : away_score;
  const oppScore = is_home ? away_score : home_score;
  const char = teamScore > oppScore ? "W" : teamScore < oppScore ? "L" : "T";
  return { char, teamScore, oppScore };
}

/**
 * The team-relative last score of a suspended match, or null when it is partial.
 *
 * Half a score under a "last score" label is the partial-line trap CERT-752
 * graded 1.0/0.0 — so one side missing prints the badge alone, exactly as
 * `suspendedSummary` does for the shared card.
 */
export function teamLastScore(
  game: Pick<TeamGameBrief, "home_score" | "away_score" | "is_home">,
): { teamScore: number; oppScore: number } | null {
  const { home_score, away_score, is_home } = game;
  if (home_score == null || away_score == null) return null;
  return {
    teamScore: is_home ? home_score : away_score,
    oppScore: is_home ? away_score : home_score,
  };
}
