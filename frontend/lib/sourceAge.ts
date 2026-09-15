/**
 * HOW OLD IS THE NUMBER BESIDE THIS SOURCE'S NAME (#4970, D132).
 *
 * ═══ WHY THIS IS A MODULE AND NOT A SECOND COPY ═══
 *
 * `BookmakerTable` has printed "2m ago" in its Status column for as long as the
 * sportsbook disclosure has existed, and its `formatRelativeTime` was a private
 * function in that file. #4970 needs the same sentence on a second surface —
 * `/events/{id}/models`, where the per-SOURCE numbers sit side by side with no
 * age at all. This repo already has four separate hand-rolled age formatters
 * (`stalenessLabel`, `matchDetail`'s copy, `playoffGrid.formatAge`,
 * `FreshnessDot.compactAge`), each with its own rounding and its own words, and
 * a fifth would be how a reader learns that "40m ago" on one card and "40 min
 * ago" on another are two different facts. So this is a MOVE of the one
 * formatter that already ships this vocabulary, not a copy of it.
 *
 * The vocabulary is deliberately the SHORT one ("3m ago", "2h ago"), because
 * the surfaces that spend it are dense — a table row and a right-aligned column
 * under a percentage — and because it is what the live hero already says beside
 * the blend ("live · 3m ago"). A reader moving from the hero to the sources
 * page should not have to learn a second set of words for the same fact.
 *
 * ═══ ABSENT IS NOT ZERO ═══
 *
 * 🔴 `formatSourceAge` returns `null` for a missing stamp and the caller decides
 * what to draw. The trap this closes is the one latency/339 refused to hand ux
 * on the card half: a source we have never observed must not read as one we
 * observed a moment ago. The old private copy took `string` and, given an
 * unparseable stamp, walked every comparison against `NaN` (all false) and fell
 * out of the bottom as the literal `"NaN d ago"`. Both absences now return
 * `null`, and `BookmakerTable`'s existing `"-"` is preserved at its call site.
 *
 * ═══ `nowMs` IS AN ARGUMENT ═══
 *
 * Gotcha #44: a test anchor must not branch on the clock. Passing `now` in means
 * a guard can pin "97 minutes reads as 1h ago" at a fixed instant instead of
 * constructing a stamp relative to whenever the suite happens to run.
 */

// The one precise-stamp formatter on this platform — see `formatSourceStamp`.
// `lib/liquidity` imports nothing, so this cannot close a cycle.
import { preciseObservedAt } from "@/lib/liquidity";

/**
 * The age past which a source's number is treated as no longer updating.
 *
 * Lifted verbatim from `BookmakerTable`, which has used 30 minutes to decide
 * both the row's muted treatment and — load-bearing — which sportsbooks are
 * averaged. It is stated here so the second surface cannot drift to a different
 * idea of "stale" than the first one.
 */
export const SOURCE_STALE_AFTER_MS = 30 * 60 * 1000;

/**
 * The same question for a price that is only POLLED ONCE AN HOUR (#5843).
 *
 * 🔴 Not a second opinion about staleness — the FIRST one, for a population the
 * 30 minutes above was never measured on. `SOURCE_STALE_AFTER_MS` is lifted from
 * `BookmakerTable`, whose sportsbook rows restamp in minutes; applying it to a
 * futures ladder asks a card to be fresher than the pipeline can make it.
 *
 * The backend already answers this, on THIS FIELD, at the render boundary:
 * `utils/tournament_register.py` carries `STALE_PRICE_HOURS = 6.0` and raises
 * `LIVE_PRICE_STALE` against a block's `price_observed_at` past it, and
 * `tasks/futures_price_refresh.py`'s `STALE_AFTER_HOURS = 6` cites that constant
 * by name so "the producer and the renderer use one definition of stale rather
 * than two". This is the web renderer joining that agreement rather than minting
 * a third number — so the value is the backend's, not a threshold I tuned.
 *
 * ### Why 30 minutes was the wrong end of the cadence
 *
 * Futures prices are written by `poll-polymarket-hourly` (:15), `poll-kalshi`
 * (:45, every 2h) and `refresh-stale-futures-prices-hourly` (:50). The cadence
 * is hourly at best, so a 30-minute threshold is HALF of it: the feed is polled
 * together and therefore crosses together, and the mark comes on for the back
 * half of every hour and then empties.
 *
 * 🔴 SO EVERY COUNT HERE CARRIES THE MINUTE IT WAS TAKEN. This population is not
 * a level, it is a sawtooth, and a single read can be made to say almost
 * anything — #5843's own three reads were 7, then 32, then 9, over one hour.
 * Measured on the Discover page's OWN request (`/api/feed?limit=20&
 * event_pct=0.15`, the three pages a scroll to the end fetches, 60 items / 48
 * datable), 2026-09-13 10:53Z, just after the :45 and :50 polls landed:
 *
 * | threshold | cards that would draw |
 * |---|---|
 * | 30m (before) | **18 of 48** |
 * | this rule | **7 of 48** |
 *
 * And at the PEAK, twelve minutes earlier, on the cache built 10:41Z: **30 of
 * 30** datable, clustered at 50.2–50.4m, against **5** under this rule. Those
 * thirty were not wrong and not an outage — they were fifty minutes old and
 * about to refresh.
 *
 * The survivors are the ones worth a reader's eye: a PGA ladder at 12h, two
 * Kalshi futures at 30h, the House market at 123 DAYS, and the live card below.
 * That last comparison is the defect in one line — at 30 of 30, a market nobody
 * has repriced since May is wearing the same grey mark as a market that is
 * fine. The age stopped being surprising, and an age has value exactly when it
 * is surprising.
 */
export const FUTURES_STALE_AFTER_MS = 6 * 60 * 60 * 1000;

/** Milliseconds since `iso` was written, or `null` when there is no readable stamp. */
export function sourceAgeMs(
  iso: string | null | undefined,
  nowMs: number = Date.now(),
): number | null {
  if (typeof iso !== "string") return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, nowMs - t);
}

/**
 * THE LADDER ITSELF, reached from an age a caller already holds (#5761).
 *
 * `formatSourceAge` below takes a stamp and dates it against a clock. A ticking
 * badge does not have that shape: `LiveAgeStamp` holds its own age in seconds,
 * ticked once a second from the stamped write time, and dating the same stamp a
 * second time there would put two clocks on one number. So the rungs live here
 * and both entry points climb them.
 *
 * Written as seconds because that is what the ticking caller has, and because
 * flooring to seconds first cannot move a rung: `sourceAgeMs` clamps at zero, so
 * `floor(floor(ms/1000)/60) === floor(ms/60000)` for every value either caller
 * can produce.
 *
 * There is no seconds rung. A caller that wants one ("live · 8s ago") owns that
 * branch itself, because it is the only caller for whom a number under a minute
 * is worth a word — everywhere else "just now" is the honest reading.
 */
export function formatAgeFromSeconds(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const hours = Math.floor(seconds / (60 * 60));
  const days = Math.floor(seconds / (60 * 60 * 24));

  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

/**
 * "just now" / "3m ago" / "2h ago" / "yesterday" / "5d ago", or `null` when the
 * stamp is absent or unreadable.
 *
 * The thresholds and the wording are `BookmakerTable`'s, unchanged — this
 * function is what that column now calls.
 */
export function formatSourceAge(
  iso: string | null | undefined,
  nowMs: number = Date.now(),
): string | null {
  const ms = sourceAgeMs(iso, nowMs);
  if (ms === null) return null;

  return formatAgeFromSeconds(Math.floor(ms / 1000));
}

/**
 * Has this source stopped updating?
 *
 * `false` for an absent stamp, and that is the conservative answer rather than
 * the convenient one: an unstamped source is one we cannot date, and marking it
 * stale would be a claim we cannot support. The caller draws no age for it at
 * all, which is the honest treatment (see the module header).
 *
 * `staleAfterMs` is the cadence that SHOULD have replaced this price, and it
 * defaults to the sportsbook/live bound so every caller written before #5843 is
 * unchanged. A caller rendering hourly-polled futures passes
 * `FUTURES_STALE_AFTER_MS`; the two named constants are the only values any
 * caller passes, because a raw number here is how a fourth definition of stale
 * gets into the repo (see that constant's header).
 */
export function sourceIsStale(
  iso: string | null | undefined,
  nowMs: number = Date.now(),
  staleAfterMs: number = SOURCE_STALE_AFTER_MS,
): boolean {
  const ms = sourceAgeMs(iso, nowMs);
  return ms !== null && ms > staleAfterMs;
}

/**
 * The OLDEST of several stamps, or `null` when none of them is readable.
 *
 * Added by #4970's card half, and exported from here rather than written twice
 * because two callers needed it in the same change — `otherMarketGroups`
 * merging duplicate wire rows into one outcome, and `SpecialEventMarkets`
 * summarising a card's rows into one mark. A second copy is how the two come to
 * disagree about which end of a range they take, which is the whole subject of
 * this module's header.
 *
 * OLDEST rather than newest for the reason CERT-411 round 2 gave the tournament
 * cards: a group is as old as its oldest member, because taking the newest lets
 * one current contributor vouch for a set that is mostly stale.
 *
 * Unreadable and absent stamps are SKIPPED, not treated as very old — an
 * undatable price is not evidence of anything, and letting it win would poison
 * a group that has perfectly good stamps in it.
 */
export function oldestSourceStamp(
  stamps: readonly (string | null | undefined)[],
): string | null {
  let best: string | null = null;
  for (const s of stamps) {
    if (typeof s !== "string") continue;
    const t = Date.parse(s);
    if (Number.isNaN(t)) continue;
    // Compared as PARSED TIME, never as text: `2026-09-11T20:00:00-04:00` is
    // later than `2026-09-11T23:00:00+00:00` and sorts earlier as a string.
    if (best === null || t < Date.parse(best)) best = s;
  }
  return best;
}

/**
 * The absolute stamp, for a `title` tooltip.
 *
 * Notice 34 puts the method note in the tooltip and never in the page body, so
 * the visible string stays the short relative age and the exact time lives
 * here. `null` propagates for the same reason as above.
 *
 * ═══ ONE PRECISE-STAMP FORMATTER ON THIS PLATFORM (#6343) ═══
 *
 * 🔴 This used to hand-roll `toLocaleString("en-US", { month, day, … })` and so
 * printed "Sep 12, 3:51 AM" while `lib/liquidity.preciseObservedAt` — written
 * to Alex's 2026-08-29 "precisely when" ruling — printed "12 Sep, 3:51 AM" for
 * the same instant. Two precise stamps, two field orders, on the same web page:
 * a card's age mark and the illiquidity mark beside it disagreed about how to
 * spell a date. That is the exact failure `lib/sourceAge`'s own header warns
 * about for RELATIVE ages ("a fifth is how a reader learns that two spellings
 * are two different facts"), and it had quietly grown in the absolute ones.
 *
 * So this DELEGATES rather than formats. `preciseObservedAt` is the one
 * precise-stamp formatter web has, and `ios/…/Utilities/SourceAge.swift`
 * resolves the same way on the phone — its `preciseStamp` calls
 * `Liquidity.preciseObservedAt` rather than copying it, and its header names
 * this field-order split as the divergence to close. Closing it here is the web
 * half of #6343; the phone half shipped in PR #6366.
 *
 * Two consequences worth stating, because both are improvements and neither is
 * incidental:
 *
 *  - the field order moves to day-first everywhere web prints an absolute
 *    stamp, which is the sportsbook table and `/events/{id}/models` as well as
 *    the card mark — one vocabulary, not a special case for the card;
 *  - the LOCALE stays pinned and the TIMEZONE stays the reader's. This function
 *    used to hardcode `"en-US"` and so does `preciseObservedAt`, deliberately:
 *    it assembles the stamp from `en-US` parts so the month name and the
 *    meridiem are stable for every reader of an English-only site, and asking
 *    for the reader's own locale is what put the field order wrong in the first
 *    place (see that function's own note). What is the reader's own — and is
 *    the whole point of a precise stamp — is the TIME ZONE: no `timeZone`
 *    option is passed, so the clock they can check is their own.
 */
export function formatSourceStamp(
  iso: string | null | undefined,
): string | null {
  // `typeof` first, not `preciseObservedAt`'s falsy guard: the two agree on
  // every value either can receive, and this keeps the null contract above
  // readable at the call site rather than one file away.
  if (typeof iso !== "string") return null;
  return preciseObservedAt(iso);
}
