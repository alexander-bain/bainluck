/**
 * UX-P045 — the single home for "when did this finished game finish".
 *
 * THE DRIFT THIS REPLACES. Three surfaces independently answered this question,
 * and the one that mattered most answered it worst:
 *
 *   - `components/FeedCard.tsx`  — a module-private `formatFinishedDate`,
 *     documented "Format a finished game's date for staleness context".
 *     Correct, and unreachable: never exported.
 *   - `components/EventCard.tsx` — its own inline `finishedDateStr`, a compact
 *     month/day with no relative-day wording.
 *   - `components/discover/EventCard.tsx` — nothing at all. Every settled game
 *     collapsed to the bare string "Final", so a game that ended 20 minutes ago
 *     and one that ended 19 hours ago rendered identically. Discover is the
 *     DEFAULT LANDING PAGE; measured 2026-08-10 07:04 PT, 15 of 15 event cards
 *     were finished games and 14 of them were over 12 hours old.
 *
 * This module does NOT unify the two existing visual formats — that would be an
 * unmeasured restyle of two surfaces to fix a defect on a third. It unifies the
 * part that is genuinely one rule (the impossible-state guard and the
 * calendar-day classification) and offers each surface its existing style.
 *
 * PURE: no I/O, no ambient clock. `now` is always injectable so tests never race
 * a date boundary (gotcha #44).
 */

/** How the finished-game label reads. Both styles share the guard below. */
export type FinishedLabelStyle =
  /** "Today 1:10 PM" / "Yesterday 1:10 PM" / "Sat, Aug 9" — FeedCard + Discover. */
  | "relative"
  /** "Aug 9" (with year when it differs) — the compact EventCard chip. */
  | "compact";

/**
 * L2-112 Item 2 / gotcha #14 — a FINAL game can never be in the future.
 *
 * `commence_time` sometimes holds a Kalshi close/resolution timestamp rather than
 * a game start, which really can be a future instant on an already-settled event.
 * Rendering that date beside a "Final" badge states an impossible thing, so every
 * caller drops the date entirely rather than printing it.
 *
 * This guard previously existed as two separate copies of the same comment and
 * the same comparison. It now has one home; a fourth surface cannot forget it.
 */
export function isImpossibleFutureFinal(
  commenceTime: string | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!commenceTime) return false;
  const t = new Date(commenceTime).getTime();
  if (Number.isNaN(t)) return false;
  return t > now;
}

/** True when two instants fall on the same local calendar day. */
function sameCalendarDay(a: Date, b: Date): boolean {
  return (
    a.getDate() === b.getDate() &&
    a.getMonth() === b.getMonth() &&
    a.getFullYear() === b.getFullYear()
  );
}

/**
 * The label a settled game shows so the reader can tell WHEN it finished.
 *
 * Returns "" — meaning "render no date" — for a missing/unparseable time and for
 * the impossible future-dated final. "" is a deliberate render instruction, not a
 * failure: the caller shows its "Final" badge with nothing beside it.
 */
export function formatFinishedGameLabel(
  commenceTime: string | null | undefined,
  now: number = Date.now(),
  style: FinishedLabelStyle = "relative",
): string {
  if (!commenceTime) return "";
  const game = new Date(commenceTime);
  if (Number.isNaN(game.getTime())) return "";
  if (isImpossibleFutureFinal(commenceTime, now)) return "";

  const nowDate = new Date(now);

  if (style === "compact") {
    // Preserved byte-for-byte from components/EventCard.tsx so adopting this
    // module is not a restyle of that surface.
    return game.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: game.getFullYear() !== nowDate.getFullYear() ? "numeric" : undefined,
    });
  }

  // Preserved from components/FeedCard.tsx's `formatFinishedDate`, including its
  // default-locale (`[]`) formatting.
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  const timeStr = game.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (sameCalendarDay(game, nowDate)) return `Today ${timeStr}`;
  if (sameCalendarDay(game, yesterday)) return `Yesterday ${timeStr}`;

  return game.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}
