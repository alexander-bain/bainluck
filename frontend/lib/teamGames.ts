/**
 * Pure helpers for team-page game cards (L2-158).
 *
 * These encode the "state honesty" rules from the team-page dogfood round:
 *  - a game is LIVE only if the backend says live AND it has actually started
 *    (a future commence_time must never render a LIVE chip — gotcha #14: the
 *    backend status writer can flip 'live' hours before first pitch);
 *  - settled games arrive as EITHER 'completed' OR 'closed';
 *  - a G1/G2 chip is drawn only where the provider itself says "doubleheader,
 *    game N" — never inferred from two rows sharing an opponent and a day,
 *    because that is also exactly what a duplicate looks like (#2866).
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
 *
 * 🔴 `RecentGameCard` NO LONGER CALLS THIS, AND THAT IS THE FIX, NOT A REGRESSION
 * (#3791). Asking "is this one of the two states we know we do not know about"
 * is a denylist, and it let the card claim a bare `Final` for the third way —
 * a `closed` row whose scores never arrived. The card now asks {@link teamResult}
 * whether a result can be STATED, which is the same question fail-closed. This
 * predicate stays because it is still the right one for anything reasoning about
 * the rail's membership rather than about what a card may claim, and because it
 * is where a surface should reach for the shared vocabulary rather than writing
 * a fourth `=== "suspended"`.
 */
export function isGameSuspended(
  game: Pick<TeamGameBrief, "status" | "commence_time">,
  now: number = Date.now(),
): boolean {
  return hasNoReportedResult(game.status, game.commence_time, now);
}

/**
 * Assign 1-based game numbers to doubleheaders, **from the provider's own
 * doubleheader metadata and from nothing else** (#2866). A game gets a number
 * iff its row says `doubleheader === true` and carries a positive integer
 * `game_number`. Everything else is omitted from the map, so the caller renders
 * no G-chip. No payload serves those fields yet, so today the answer is always
 * `{}` — and that is the correct answer, not a placeholder.
 *
 * 🔴 THE SAME-DAY-OPPONENT INFERENCE IS GONE, AND ITS ABSENCE IS THE FIX. This
 * function used to group games by (opponent, calendar day) and number any pair
 * it found. That was the last step which turned a DATA defect into a plausible
 * product feature: the Bears page carried `@ Tennessee Titans G1` and
 * `@ Tennessee Titans G2`, same day, same 24–15 result — five cards for three
 * real games — because 47 of 50 NFL preseason rows exist twice.
 *
 * lane1/087 gated that inference to MLB, which stopped the NFL case. It could
 * not stop the class, because **the gate and the inference answer different
 * questions**: "can a doubleheader happen in this league" is not "did this
 * pair of rows happen twice". Inside MLB — where duplicates also occur, and
 * where a doubleheader is genuinely common — a twin and a real doubleheader are
 * *identical* under same-day pairing, so the chip could still explain a
 * duplicate away. It just did it on one league instead of all of them.
 *
 * So the league allowlist is gone too, and deliberately: with an authority
 * field the allowlist is no longer a safety rail, it is a second gate that can
 * only be WRONG. It would suppress a true NPB or KBO doubleheader the moment
 * the provider vouches for one, which is the same "silently re-breaks for the
 * next league" failure the allowlist was originally chosen to avoid. The
 * parameter is removed rather than ignored so that no caller can believe it
 * still means something.
 *
 * **This does not fix the duplicate and must not be read as fixing it.** A twin
 * pair still renders twice; it just cannot arrive dressed as deliberate. The
 * data half is `matching-symptom` under D35 and belongs to #2693.
 *
 * **What unblocks the chips:** `schedule_sentinel.py` already parses MLB Stats
 * API's `doubleHeader` and `gameNumber` into `TruthGame`. Carrying them onto
 * `Event` and emitting them from `_format_event_brief` is lane1's, and needs no
 * further frontend change — the chips resume by themselves.
 */
export function assignGameNumbers(
  games: TeamGameBrief[],
): Record<number, number> {
  const out: Record<number, number> = {};
  for (const g of games) {
    if (g.doubleheader !== true) continue;
    const n = g.game_number;
    // A number is required, and it must be a real 1-based ordinal. `0`, a
    // non-integer and a NaN are all "the authority did not actually say"; a
    // chip reading `G0` would be the same confident lie in a new font.
    if (typeof n !== "number" || !Number.isInteger(n) || n < 1) continue;
    out[g.id] = n;
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
