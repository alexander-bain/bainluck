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
/** `2026-12-31` — a CALENDAR DATE, carrying no time and no zone. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

export function formatResolvesLabel(
  resolutionDate: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!resolutionDate) return "";
  const end = new Date(resolutionDate);
  if (Number.isNaN(end.getTime())) return "";
  if (end.getTime() <= now) return "";

  // ── C270 P1: a date-only value is a calendar date, not an instant ──
  //
  // `new Date("2026-12-31")` parses as UTC MIDNIGHT, and `toLocaleDateString`
  // then renders that instant in the browser's zone. West of UTC it lands on
  // the day BEFORE, so a tournament declaring 2026-12-31 printed "Resolves
  // Dec 30, 2026" to every user in the Americas, and 2028-02-29 printed
  // "Feb 28, 2028". The declared day is the only thing this label exists to
  // say, and it was the thing being lost.
  //
  // Invisible to CI because CI runs UTC, where the shift is exactly zero —
  // gotcha #44 in a new hat. The logic was never wrong under the one
  // environment anybody checked it in.
  //
  // Golf is a live producer of this shape, not a hypothetical: `routes/golf.py`
  // deliberately writes DataGolf's semantic `end_date` string into
  // `resolution_date`, and the feed passes it through unchanged.
  //
  // Timestamps keep local formatting — those really are instants, and "when
  // does this resolve, my time" is the right question to answer for them.
  const zone = DATE_ONLY.test(resolutionDate) ? { timeZone: "UTC" as const } : {};

  return `Resolves ${end.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    ...zone,
  })}`;
}

/**
 * UX-P267 (#2549) — THE PREMISE THIS MODULE WAS BUILT ON HAS EXPIRED.
 *
 * `formatTournamentWhenLabel` above says, in its own docstring: "It does NOT
 * derive a status — nothing here concludes that a tournament is over, because
 * the wire does not say so (`start_date`, `end_date` and `schedule_status` were
 * null on 8 of 8)." That measurement (#1700) is why the entire design is a pair
 * of TRUST WINDOWS around `commence_time` — a market timestamp being asked to
 * impersonate a schedule, with staleness as the only available tell.
 *
 * The wire says so now. Measured on production 2026-09-02 03:1x PT, `GET
 * /api/golf` over the whole live slate:
 *
 *   omega_european_masters            start_date 2026-09-03  commence 2026-08-31  DIFF -3d
 *   biltmore_championship_asheville   start_date 2026-09-17  commence 2026-09-17  same day
 *   ..._pga_tour_major_in_2027        start_date null        commence 2028-01-14
 *   ..._pga_tour_major_before_2027    start_date null        commence 2026-07-19
 *
 * `start_date` is present on 2 of 4, and on the one where it disagrees the card
 * was printing **"Started Mon, Aug 31"** for a tournament whose own payload
 * carried `start_date: 2026-09-03`, `schedule_status: "upcoming"` and a backend
 * `headline: "Tomorrow"`. Every fact needed to say the true thing was on the
 * card; the reader got the false one. That is #2549's surviving half (its "0%"
 * half resolved separately), still live on the default landing page.
 *
 * WHY THE TRUST WINDOWS COULD NEVER HAVE CAUGHT IT. They bound a timestamp for
 * being too STALE or too FAR OUT. `commence_time` here is a per-market Kalshi
 * open time — the seven markets in this tournament's group carry seven different
 * values spanning 5.5 minutes — so it is always RECENT, which is precisely the
 * region both windows admit. The one class of wrong start date the design cannot
 * see is the one it produces.
 *
 * So the windows are not widened or retuned; they keep guarding the fallback,
 * unchanged, for the two cards that still have no `start_date`. The schedule is
 * simply believed ahead of the market timestamp when the schedule is there.
 */

/**
 * The leading calendar day of an ISO value — `2026-09-03T00:00:00+00:00` -> 3
 * September 2026. Deliberately a STRING parse and not a `Date`: see below.
 */
const ISO_DECLARED_DAY = /^(\d{4})-(\d{2})-(\d{2})/;

/**
 * "Starts Thu, Sep 3" from a scheduled start, or "" when there is not one.
 *
 * ── WHY THIS IS ZONE-INDEPENDENT BY CONSTRUCTION, AND WHY THAT MATTERED ──
 *
 * `start_date` arrives as `2026-09-03T00:00:00+00:00`: a semantic CALENDAR DATE
 * serialised as a UTC-midnight instant. That is exactly the shape `format-
 * ResolvesLabel` documents under C270 P1 — `new Date(...)` then a local
 * `toLocaleDateString` renders the day BEFORE for every reader west of UTC, so
 * the obvious "just read start_date" would have printed "Starts Wed, Sep 2" in
 * Pacific time and swapped a wrong date for a differently wrong one. The
 * `DATE_ONLY` guard that catches it there does NOT match this value: it is a
 * full timestamp, not a bare `YYYY-MM-DD`.
 *
 * Rather than add a second zone special-case, the declared day is lifted out of
 * the string as three integers and never round-tripped through a local `Date` at
 * all. Formatting is pinned to UTC over a UTC-midnight instant built from those
 * integers, so there is no ambient-timezone path through this function to be
 * wrong in. This is not merely a fix that measures correct — it is one that has
 * no failing case to measure.
 *
 * That construction is also the only honest option under this harness: jest
 * pins `process.env.TZ = 'UTC'` for the whole suite (`jest.config.js`, and it
 * must live there — a test file's realm is built before `setupFiles`), so local
 * IS UTC inside every test and an assertion about the local-vs-UTC difference
 * would be green on the fix and green on the bug alike. The guard therefore
 * pins the CONSTRUCTION (the parse never consults a zone) rather than claiming a
 * zone-sensitivity it cannot exercise here.
 *
 * NO TRUST WINDOW, deliberately. The windows on `formatTournamentWhenLabel`
 * exist because a market timestamp is not a start date and staleness is the only
 * tell. `start_date` IS the schedule asserting a start; a tournament that began
 * nine days ago has honestly "Started Sun, Aug 23", and suppressing that would
 * re-introduce the silence #1700 set out to remove.
 *
 * The relative words compare the declared day against the READER's local
 * calendar day, which is the frame the reader is standing in: at 8pm Pacific on
 * Sep 2 a Sep 3 tournament starts "tomorrow", not "today", even though UTC has
 * already turned over. A calendar date carries no time of day, so a start on
 * today's date reads "Starts today" — the past/present distinction within the
 * day is not derivable from the wire and is not guessed.
 */
export function formatDeclaredStartLabel(
  startDate: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!startDate) return "";
  const parts = ISO_DECLARED_DAY.exec(startDate.trim());
  if (!parts) return "";

  const year = Number(parts[1]);
  const month = Number(parts[2]);
  const day = Number(parts[3]);

  const declared = Date.UTC(year, month - 1, day);
  const probe = new Date(declared);
  // `Date.UTC` silently rolls a non-calendar date over (2026-02-31 -> Mar 3).
  // Printing a day the wire did not declare is the defect this function exists
  // to remove, so an impossible date says nothing and lets the fallback run.
  if (
    probe.getUTCFullYear() !== year ||
    probe.getUTCMonth() !== month - 1 ||
    probe.getUTCDate() !== day
  ) {
    return "";
  }

  const nowDate = new Date(now);
  const readerToday = Date.UTC(
    nowDate.getFullYear(),
    nowDate.getMonth(),
    nowDate.getDate(),
  );
  const deltaDays = Math.round((declared - readerToday) / MS_PER_DAY);

  if (deltaDays === 0) return "Starts today";
  if (deltaDays === 1) return "Starts tomorrow";
  if (deltaDays === -1) return "Started yesterday";

  const dateStr = probe.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    // Same reasoning as the fallback: a card whose start lands in another year is
    // exactly the case a reader most needs the year for.
    ...(year !== nowDate.getFullYear() ? { year: "numeric" as const } : {}),
    timeZone: "UTC",
  });
  return `${deltaDays > 0 ? "Starts" : "Started"} ${dateStr}`;
}

/**
 * The single timing line a Discover tournament card prints — the scheduled start
 * when the wire declares one, else the start date `commence_time` can be trusted
 * to imply, else the resolution date.
 *
 * FALLBACK, NOT A SECOND LINE. A card with a good start date does not also get a
 * resolution line: "Starts Thu, Aug 13" already answers the reader's question and
 * "Resolves Aug 30" beside it is noise on the biggest slot of the landing page.
 * The resolution line exists for the cards that today say NOTHING.
 *
 * Composed here rather than in the card so the rules cannot drift apart — the
 * #1620 shape this lane has now found six times, and the reason `formatTournament-
 * WhenLabel` and this function share a module instead of a component.
 *
 * `startDate` has NO DEFAULT, and that is load-bearing rather than pedantic. A
 * `startDate = null` default would keep all five existing call sites compiling
 * while letting the next one silently re-acquire #2549 with every test still
 * green. There is exactly one production call site, so requiring it costs
 * nothing; a guard asserts the parameter stays required.
 */
export function formatTournamentTimingLabel(
  startDate: string | null | undefined,
  commenceTime: string | null | undefined,
  resolutionDate: string | null | undefined,
  now: number = Date.now(),
): string {
  return (
    formatDeclaredStartLabel(startDate, now) ||
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
 *
 * 3. WHEN THE GAME IS OVER, THE CLOCK IS NOT A CLOCK — IT IS THE PERIOD AGAIN
 *    (live/055, #2815). Rule 2 is gated on {@link CLOCK_TOKEN_RE}, deliberately,
 *    so a bare "1" cannot match the "1" in "Bottom 1st" and delete a real field
 *    on a coincidence. That gate is why it could not see the settled case:
 *    production event 15293206 ships `period: "Final"` with `game_clock:
 *    "Final"` — the same word in both fields, neither of them clock-shaped — and
 *    the event page's chart footer printed **"Final Final 3 - 8"**.
 *
 *    An exact repeat needs no shape gate because it has no coincidence to guard
 *    against: two fields carrying the identical string can never be two facts.
 *    Compared case-insensitively and trimmed, and nothing wider than equality —
 *    a substring test over arbitrary strings would re-open exactly the false
 *    positive rule 2's gate exists to prevent.
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
  const repeatsPeriod =
    trimmedClock !== "" &&
    trimmedClock.toLowerCase() === trimmedPeriod.toLowerCase();
  return {
    period: trimmedPeriod,
    gameClock: alreadySpelledOut || repeatsPeriod ? "" : trimmedClock,
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
