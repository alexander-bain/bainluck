/**
 * #4081 — a declared deadline stops reading a day early west of UTC.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/futures/114175` ("Who will be UFC Heavyweight champion at the end of 2026?"),
 * production 2026-09-17 ~18:10Z at 390px (native/207's LOOK): the chip under the
 * hero read **"Resolves Dec 30, 2026"** over four cards on the same screen titled
 * "… Title Holder on **Dec 31**, 2026?". The wire says
 * `resolution_date: 2026-12-31T00:00:00+00:00`.
 *
 * C270 P1 already fixed this for a BARE `YYYY-MM-DD` — golf's semantic
 * `end_date` — and every futures market sends a full timestamp instead, so the
 * guard never matched the population that reports the bug. 2,887 of 34,780 open
 * markets with a resolution date carry exactly `00:00:00` UTC (native/206,
 * production, 2026-09-17).
 *
 * ═══ WHY THIS FILE ASSERTS OPTIONS RATHER THAN A RENDERED DAY ═══
 *
 * 🔴 `jest.config.js` pins `process.env.TZ = 'UTC'` for the whole suite, and it
 * must (a test file's realm is built before `setupFiles`). Under UTC the defect
 * and the fix render the SAME string, so an assertion like
 * `expect(label).toBe("Resolves Dec 31, 2026")` is green on both and proves
 * nothing about the thing that broke. This is the same reason
 * `formatTournamentWhenLabel`'s guard pins its CONSTRUCTION.
 *
 * So the two arms here are:
 *
 *   1. the DISCRIMINATOR, directly — which strings are declared days, and,
 *      just as load-bearing, which are instants that must keep local conversion;
 *   2. the CHOICE the label makes with it — `toLocaleDateString` is spied on and
 *      the options it receives are read. `{ timeZone: "UTC" }` for a declared
 *      day, no `timeZone` key for an instant. That is the exact line the defect
 *      got wrong, and it is visible under a UTC-pinned harness.
 *
 * A rendered-string arm is kept for the specimen anyway, as a legibility check
 * on the whole label — never as the proof of the zone.
 *
 *   TZ=UTC npx jest --testPathPatterns=declaredDeadlineKeepsItsDay4081
 */

import {
  formatResolvesLabel,
  isDeclaredCalendarDay,
} from "@/lib/gameTimeLabel";

/** Comfortably before every specimen below, so nothing is filtered as past. */
const NOW = Date.parse("2026-09-17T18:00:00Z");

describe("isDeclaredCalendarDay", () => {
  it.each([
    ["2026-12-31", "a bare calendar date — golf's `end_date`, C270 P1's population"],
    ["2026-12-31T00:00:00+00:00", "THE specimen: every futures market's shape"],
    ["2026-12-31T00:00:00Z", "the same instant spelled with a Z"],
    ["2026-12-31T00:00:00.000Z", "an all-zero fraction is still midnight"],
    ["2028-02-29T00:00:00+00:00", "a leap day, which the local shift also moved"],
  ])("%s is a declared day (%s)", (value) => {
    expect(isDeclaredCalendarDay(value)).toBe(true);
  });

  it.each([
    ["2026-12-31T00:00:00.5Z", "half a second past midnight is an instant"],
    ["2026-12-31T00:00:00+05:00", "midnight in ANOTHER zone is not UTC midnight"],
    ["2026-12-31T23:59:00+00:00", "a real close time — 23 of 112 entertainment rows"],
    ["2026-12-31T15:00:00+00:00", "ditto, 24 of 112"],
    ["", "empty"],
    ["not a date", "garbage"],
  ])("%s is NOT a declared day (%s)", (value) => {
    expect(isDeclaredCalendarDay(value)).toBe(false);
  });

  it("answers false for null and undefined rather than throwing", () => {
    expect(isDeclaredCalendarDay(null)).toBe(false);
    expect(isDeclaredCalendarDay(undefined)).toBe(false);
  });
});

describe("formatResolvesLabel pins the zone for a declared day and only for one", () => {
  const real = Date.prototype.toLocaleDateString;
  let seen: Intl.DateTimeFormatOptions[] = [];

  beforeEach(() => {
    seen = [];
    // eslint-disable-next-line no-extend-native
    Date.prototype.toLocaleDateString = function (
      this: Date,
      locales?: unknown,
      options?: Intl.DateTimeFormatOptions,
    ) {
      seen.push(options ?? {});
      return real.call(this, locales as string | string[] | undefined, options);
    } as typeof Date.prototype.toLocaleDateString;
  });

  afterEach(() => {
    // eslint-disable-next-line no-extend-native
    Date.prototype.toLocaleDateString = real;
  });

  it("formats a UTC-midnight timestamp in UTC — the #4081 repair", () => {
    formatResolvesLabel("2026-12-31T00:00:00+00:00", NOW);
    expect(seen).toHaveLength(1);
    expect(seen[0].timeZone).toBe("UTC");
  });

  it("still formats a bare calendar date in UTC — C270 P1, unchanged", () => {
    formatResolvesLabel("2026-12-31", NOW);
    expect(seen[0].timeZone).toBe("UTC");
  });

  it("CONTROL — a real instant keeps LOCAL formatting", () => {
    formatResolvesLabel("2026-12-31T23:59:00+00:00", NOW);
    expect(seen).toHaveLength(1);
    expect(seen[0].timeZone).toBeUndefined();
  });

  it("CONTROL — midnight in another zone is an instant, not a declared day", () => {
    formatResolvesLabel("2026-12-31T00:00:00+05:00", NOW);
    expect(seen[0].timeZone).toBeUndefined();
  });

  it("every call still asks for month, day AND year (#1717)", () => {
    formatResolvesLabel("2026-12-31T00:00:00+00:00", NOW);
    expect(seen[0]).toMatchObject({ month: "short", day: "numeric", year: "numeric" });
  });
});

describe("the whole label, as a reader reads it", () => {
  it("names the declared day of the #4081 specimen", () => {
    expect(formatResolvesLabel("2026-12-31T00:00:00+00:00", NOW)).toBe(
      "Resolves Dec 31, 2026",
    );
  });

  it("says nothing about a deadline that has passed", () => {
    expect(formatResolvesLabel("2026-01-01T00:00:00+00:00", NOW)).toBe("");
  });

  it("says nothing when there is no deadline", () => {
    expect(formatResolvesLabel(null, NOW)).toBe("");
    expect(formatResolvesLabel("not a date", NOW)).toBe("");
  });
});
