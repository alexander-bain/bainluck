/**
 * UX-P045 — the single home for "when did this finished game finish", widened by
 * UX-P049 to "when did/does this Discover card's thing happen".
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

/**
 * UX-P049 — the same question for a TOURNAMENT card, which never asked it.
 *
 * `components/discover/TournamentCard.tsx` rendered a title, a venue and a
 * leader probability and **no date, in any branch**. `commence_time` was on the
 * wire the whole time and read by nothing. Measured on production 2026-08-10
 * 15:40 PT, when tournaments were 8 of the 20 cards on the default landing page:
 * a tournament starting in 3 days, one that teed off 2 days ago, and one whose
 * timestamp is in 2028 all rendered identically. This is #1677's finding one
 * card type over — there, 15 of 15 settled event cards said only "Final".
 *
 * WHY THIS IS NOT SIMPLY `formatFinishedGameLabel`. That function answers "when
 * did this END" and deliberately returns "" for a future instant (the gotcha #14
 * impossible-future-final guard). A tournament card is mostly NOT finished, so
 * the future is the common case and suppressing it would render nothing on
 * exactly the cards that most need a date.
 *
 * THE TRAP, AND IT IS THE REASON FOR THE WINDOW. Not every tournament card is a
 * tournament. Season-long futures markets ride this card type too — "Golfers To
 * Win A PGA Tour Major In 2026" carried `commence_time: 2026-06-22`, seven weeks
 * stale and never a start date at all. Printing "Started Mon, Jun 22" there
 * would state something false in order to fix a card that was merely silent, so
 * a timestamp more than {@link TOURNAMENT_START_TRUST_DAYS} days past is treated
 * as not-a-start-date and suppressed. On the measured slate that is 5 of 8 cards
 * gaining a correct date and 3 correctly staying silent.
 *
 * Reads `commence_time` and states it. It does NOT derive a status — nothing
 * here concludes that a tournament is over, because the wire does not say so
 * (`start_date`, `end_date` and `schedule_status` were null on 8 of 8).
 */
export const TOURNAMENT_START_TRUST_DAYS = 7;

const MS_PER_DAY = 86_400_000;

export function formatTournamentWhenLabel(
  commenceTime: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!commenceTime) return "";
  const start = new Date(commenceTime);
  if (Number.isNaN(start.getTime())) return "";

  const deltaMs = start.getTime() - now;
  if (-deltaMs > TOURNAMENT_START_TRUST_DAYS * MS_PER_DAY) return "";

  const upcoming = deltaMs >= 0;
  const verb = upcoming ? "Starts" : "Started";
  const nowDate = new Date(now);

  if (sameCalendarDay(start, nowDate)) return `${verb} today`;

  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (sameCalendarDay(start, tomorrow)) return "Starts tomorrow";

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (sameCalendarDay(start, yesterday)) return "Started yesterday";

  const dateStr = start.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    // A card whose timestamp lands in another year is exactly the case a reader
    // most needs the year for — "Starts Fri, Jan 14" would read as months away
    // when it is seventeen.
    ...(start.getFullYear() !== nowDate.getFullYear() ? { year: "numeric" as const } : {}),
  });
  return `${verb} ${dateStr}`;
}
