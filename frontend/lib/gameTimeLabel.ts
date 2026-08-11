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
 * UX-P050 — THAT WINDOW WATCHED ONLY ONE SIDE. The trap above is real and the
 * guard against it was backward-only, so the identical lie walked in through the
 * future: "Golfers To Win A PGA Tour Major In 2027" carries `commence_time:
 * 2028-01-14`, which is not a start date either, and the card printed **"Starts
 * Fri, Jan 14, 2028"**. Suppressing a false past date while printing a false
 * future one is the same defect, and only the past half had a bound. Hence
 * {@link TOURNAMENT_START_TRUST_FUTURE_DAYS}: golf schedules are published at
 * most about a year ahead, so a commence_time beyond that is not a start.
 *
 * Reads `commence_time` and states it. It does NOT derive a status — nothing
 * here concludes that a tournament is over, because the wire does not say so
 * (`start_date`, `end_date` and `schedule_status` were null on 8 of 8).
 */
export const TOURNAMENT_START_TRUST_DAYS = 7;

/**
 * How far ahead a `commence_time` can be and still be believed as a start date.
 *
 * Tour schedules are announced roughly a season ahead, so a year is generous for
 * a real tournament and still excludes the season-long futures markets, whose
 * timestamps sit years out. On the measured slate this suppresses exactly one
 * card (+521d) and leaves the two genuine upcoming tournaments (+19d, +9d)
 * untouched — a both-direction guard per gotcha #43.
 */
export const TOURNAMENT_START_TRUST_FUTURE_DAYS = 365;

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
  if (deltaMs > TOURNAMENT_START_TRUST_FUTURE_DAYS * MS_PER_DAY) return "";

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

/**
 * THE formatting authority for "Resolves <date>" on a Discover card.
 *
 * UX-P050 — "Resolves Dec 31, 2026", or "" when the wire cannot honestly say it.
 *
 * THE DISCRIMINATOR #1700 CONCLUDED DID NOT EXIST. That queue found season-long
 * futures markets riding the tournament card and could not tell them apart from
 * real tournaments, because `start_date`, `end_date` and `schedule_status` were
 * null on 8 of 8 cards — so it chose silence over a guess. Correct then, and
 * incomplete: `resolution_date` was present on 8 of 8 the whole time and the card
 * read it in no branch at all. A market that resolves in July 2030 is not a
 * tournament that starts this week, and it can now say so.
 *
 * The year is ALWAYS printed. These are multi-year questions — "Resolves Jan 14"
 * is exactly the string a reader would misread as five months away when it is
 * seventeen — and it matches the shape Alex ratified.
 *
 * A resolution date in the PAST returns "". The card must not print "Resolves
 * <a date that has gone>", and it deliberately does NOT infer settlement from it
 * either: `resolution_date` is the SCHEDULED resolution, not an observed one
 * (`reference_futures_markets_no_transition_timestamp`), so concluding "this is
 * over" from a passed date would be the same class of guess #1700 refused.
 *
 * ── UX-P053 (#1717): WHY IT IS NO LONGER CALLED "Tournament" ──
 *
 * It was never tournament-specific; it was merely written for the card that
 * needed it first. One day later the SAME question — "when does this resolve?" —
 * was being answered two opposite ways on one screen. `resolvesLabel` (the
 * futures/comparison cards) returned "" beyond 7 days, so 49 of 60 futures cards
 * on the production landing page printed NOTHING while the tournament card
 * beside them printed a date. Measured 2026-08-11T01:10Z.
 *
 * Alex's ruling this cycle was not merely "extend it" but "use the IDENTICAL
 * formatter — one formatting authority, so the next drift is unrepresentable
 * rather than refiled." Hence the rename: a `Tournament` in the name is an
 * invitation for the next card type to write its own, which is exactly how this
 * lane arrived at eight instances of the #1620 shape.
 *
 * `__tests__/lib/resolvesLabelAuthority.test.ts` enforces it: a construction of
 * this string anywhere under `components/`, `lib/` or `app/` fails the suite.
 *
 * ── UX-P054 (#1719): THE EXEMPTION LIST IS NOW EMPTY ──
 *
 * UX-P053 shipped the guard with two sites recorded as named debt rather than
 * restyled unmeasured (the UX-P045 rule), and with a scan that did not reach
 * `app/`. Both are closed. `components/FeedCard.tsx` — the Sports tab, where 29
 * of 41 dated futures cards were printing a month-day with no year, so a 2031
 * championship read as this January — now calls `resolvesLabel`. And
 * `app/futures/[id]/page.tsx`, the blind spot the guard named in its own
 * docstring, now calls this function directly.
 *
 * So the assertion strengthened from "no NEW copies" to "no copies": exactly one
 * file in the frontend may build this string, which is what Alex's ruling asked
 * for and what was not yet true when the ruling was banked.
 */
export function formatResolvesLabel(
  resolutionDate: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!resolutionDate) return "";
  const end = new Date(resolutionDate);
  if (Number.isNaN(end.getTime())) return "";
  if (end.getTime() <= now) return "";

  return `Resolves ${end.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  })}`;
}

/**
 * The single timing line a Discover tournament card prints — start date when the
 * wire supports one, otherwise the resolution date.
 *
 * FALLBACK, NOT A SECOND LINE. A card with a good start date does not also get a
 * resolution line: "Starts Thu, Aug 13" already answers the reader's question and
 * "Resolves Aug 30" beside it is noise on the biggest slot of the landing page.
 * The resolution line exists for the cards that today say NOTHING.
 *
 * Composed here rather than in the card so the two rules cannot drift apart — the
 * #1620 shape this lane has now found six times, and the reason `formatTournament-
 * WhenLabel` and this function share a module instead of a component.
 */
export function formatTournamentTimingLabel(
  commenceTime: string | null | undefined,
  resolutionDate: string | null | undefined,
  now: number = Date.now(),
): string {
  return (
    formatTournamentWhenLabel(commenceTime, now) ||
    formatResolvesLabel(resolutionDate, now)
  );
}

/**
 * UX-P051 (#1710) — the LIVE clock, which is the same question a fourth time and
 * the first one where the wire actively lies.
 *
 * `Event.espn.period` is ESPN's `status.type.detail`. For a game ESPN still
 * considers SCHEDULED it is not a period at all — it is a full sentence:
 * `"Mon, August 10th at 8:00 PM EDT"`, shipped alongside `game_clock: "0.0"`.
 * Our own `status` flips to `live` on `commence_time`, so every game passes
 * through a window where we say LIVE and ESPN still says scheduled — which is
 * exactly the minutes people open the app to watch it start.
 *
 * FOUR renderers read that field and each guarded it differently, so one payload
 * painted four different wrong strings. Production specimen, event 15192197
 * (Toronto Tempo @ Atlanta Dream, 2026-08-10 ~17:00 PT, `status: "live"`, 0–0):
 *
 *   - `components/discover/EventCard.tsx`  "Mon, August 10th at 8:00 PM EDT"
 *   - `app/events/[id]/page.tsx`           "Mon, August 10th at 8:00 PM EDT · 0.0"
 *   - `components/EventCard.tsx`           "Mon, August 10th at 8:00 PM EDT 0.0"
 *   - `components/FeedCard.tsx`            "0.0"
 *
 * The first is the default landing page; the second is the event detail page.
 *
 * THE ANSWER ALREADY EXISTED SOMEWHERE ELSE, AGAIN. `FeedCard` alone knew the
 * string could be junk — via a bare `period.length <= 10` heuristic, module-
 * private, on the one surface that guessed. Seventh instance of the #1620 shape
 * on this lane. And that heuristic failed in the OTHER direction too: it silently
 * dropped legitimate long labels ("1st Quarter" 11, "End of 1st Half" 15, "End of
 * Regulation" 17), leaving those games with a bare clock and no period.
 *
 * WHAT THIS DOES NOT DO. It unifies the TRUST DECISION — which of ESPN's two
 * clock fields may be believed — and nothing else. It does not unify the four
 * surfaces' wording or separators; each caller keeps composing its own line, so
 * adopting this module is not an unmeasured restyle of three surfaces to fix a
 * defect on a fourth (the UX-P045 rule). And it derives no new fact (ruling 003):
 * every card here already claims LIVE in its own badge, so suppressing a false
 * clock removes a claim rather than adding one.
 */

/**
 * The one shape that cannot occur in an in-game label: a clock time with a
 * meridiem, introduced by "at". Real details are "Bottom 1st", "Q3 4:22",
 * "4:22 - 3rd Quarter", "Halftime", "End of 3rd", "Rain Delay", "Final/OT" —
 * none of which can contain "at 8:00 PM".
 *
 * Deliberately narrow. Suppression is the sharp edge on this lane, and the cost
 * of a false negative here is the status quo while the cost of a false positive
 * is hiding a real period.
 */
const PREGAME_START_SENTENCE_RE = /\bat\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)\b/i;

/**
 * True when ESPN's detail string describes a game that has not started.
 *
 * Two branches, and they are NOT equally evidenced — say so rather than let a
 * future reader assume both were measured:
 *   1. the start-sentence shape above, which is the live production specimen;
 *   2. the bare word "Scheduled", ESPN's own state name. No specimen was
 *      observed, but it is the same pre-game state and a card that has already
 *      painted a LIVE badge can never truthfully follow it with "Scheduled", so
 *      it cannot make anything worse in either direction.
 */
export function isPregameStatusDetail(period: string | null | undefined): boolean {
  if (!period) return false;
  const trimmed = period.trim();
  if (!trimmed) return false;
  if (/^scheduled$/i.test(trimmed)) return true;
  return PREGAME_START_SENTENCE_RE.test(trimmed);
}

/** The believable half of ESPN's live clock. Empty string means "say nothing". */
export interface TrustedLiveClock {
  period: string;
  gameClock: string;
}

/**
 * A clock-shaped token — "10:00", "4:22", "0.0". Used only to decide whether the
 * clock is already spelled inside the period, so it is deliberately strict: a
 * loose test would let a bare "1" match the "1" in "Bottom 1st" and delete a real
 * field on a coincidence.
 */
const CLOCK_TOKEN_RE = /^\d{1,2}[:.]\d{1,2}$/;

/**
 * Which of ESPN's clock fields a card may paint.
 *
 * TWO RULES, BOTH MEASURED ON THE SAME EVENT 20 MINUTES APART — 15192197 flipped
 * from one to the other mid-cycle, which is also the proof that every game passes
 * through the first state.
 *
 * 1. WHEN THE PERIOD SAYS PRE-GAME, THE CLOCK IS NOT A CLOCK EITHER. Both fields
 *    come from the same ESPN status payload, so a `period` of "Mon, August 10th
 *    at 8:00 PM EDT" ships `game_clock: "0.0"` — a default, not a countdown.
 *    Dropping only the period is what left the Sports tab rendering a bare "0.0".
 *
 * 2. THE PERIOD OFTEN ALREADY CONTAINS THE CLOCK. Once the same game tipped off
 *    it reported `period: "10:00 - 1st Quarter"` with `game_clock: "10:00"` —
 *    ESPN's basketball detail embeds the clock. Two surfaces have been printing
 *    "10:00 - 1st Quarter · 10:00" the whole time; a third only escaped it
 *    because its character-count heuristic threw the period away instead. Joining
 *    them unconditionally would have spread the duplicate rather than fixed it.
 */
export function trustedLiveClock(
  period: string | null | undefined,
  gameClock: string | null | undefined,
): TrustedLiveClock {
  if (isPregameStatusDetail(period)) return { period: "", gameClock: "" };
  const trimmedPeriod = (period || "").trim();
  const trimmedClock = (gameClock || "").trim();
  const alreadySpelledOut =
    trimmedClock !== "" &&
    CLOCK_TOKEN_RE.test(trimmedClock) &&
    trimmedPeriod.includes(trimmedClock);
  return {
    period: trimmedPeriod,
    gameClock: alreadySpelledOut ? "" : trimmedClock,
  };
}

/**
 * The trusted parts joined. Returns "" when there is nothing honest to show,
 * which is a render instruction: the caller falls back to its own existing word
 * ("LIVE" / "Live" / its highlight label).
 *
 * The separator is the caller's, not this module's — the four surfaces space,
 * dot-separate and single-field their labels differently, and unifying that would
 * be an unmeasured restyle of three surfaces to fix a defect on a fourth
 * (the UX-P045 rule). Only the trust decision is shared.
 */
export function formatLiveClockLabel(
  period: string | null | undefined,
  gameClock: string | null | undefined,
  separator: string = " ",
): string {
  const trusted = trustedLiveClock(period, gameClock);
  return [trusted.period, trusted.gameClock].filter(Boolean).join(separator);
}
