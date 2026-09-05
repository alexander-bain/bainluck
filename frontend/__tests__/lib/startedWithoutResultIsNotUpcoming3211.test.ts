/**
 * A MATCH THAT SHOULD HAVE BEEN PLAYED IS NOT "UPCOMING" — #3211, lane1/134.
 *
 * ═══ WHAT THIS GRADES ═══
 *
 * `lib/eventState.ts` opens by explaining that every surface used to read event
 * status with its own inline `=== "closed"` chain, that each of those chains
 * buckets an unrecognised state into the upcoming branch by falling through,
 * and that the upcoming branch renders a START TIME — "a quieter lie than
 * 'Final', not a smaller one".
 *
 * #3211 is that sentence's third instance and the largest. On production
 * 2026-09-05, **171 US Open matches** (99 ATP, 72 WTA) still said `scheduled`
 * days after their own kickoff: stamped midnight UTC by a Kalshi ticker rather
 * than by a reported start (gotcha #14), and never settled, because tennis has
 * no ESPN anchor at all (#2700). The backend's rails dropped them on both
 * sides, so nothing rendered them and the lie was invisible. Once the rails
 * admit them — `test_the_two_rails_are_jointly_exhaustive_3211.py` — the
 * frontend is what decides whether the reader is told the truth about them.
 *
 * Two claims, and they are separable:
 *
 *   1. such a row buckets with `live`, not with `upcoming` — the three buckets
 *      answer "has this happened yet?" and the honest answer is "it started, it
 *      has not finished", exactly as for `suspended`;
 *   2. the section heading reads the bucket rather than asserting "Live Now"
 *      over a match nobody is watching.
 *
 * The CARD's half — that it prints "No result reported" instead of a stale
 * start time — is rendered markup and lives in
 * `__tests__/components/startedWithoutResultCard3211.test.tsx`.
 *
 * ═══ EVERY ARM PINS ITS OWN CLOCK ═══
 *
 * These predicates take a time, so gotcha #44 applies with full force: an arm
 * that reads the real clock is an arm whose meaning changes overnight. Every
 * assertion below offsets from `KICKOFF`, and the boundary arms are stated from
 * BOTH sides — a test that only checks "two days later" would pass over any
 * floor at all, including no floor.
 */

import {
  UPCOMING_GRACE_MS,
  eventSectionKey,
  hasNoReportedResult,
  isSuspendedStatus,
  liveSectionTitle,
  startedWithoutResult,
} from "@/lib/eventState";

const KICKOFF = "2026-09-02T00:00:00Z";
const KICKOFF_MS = new Date(KICKOFF).getTime();

const JUST_INSIDE = KICKOFF_MS + UPCOMING_GRACE_MS - 60_000;
const JUST_OUTSIDE = KICKOFF_MS + UPCOMING_GRACE_MS + 60_000;
const DAYS_LATER = KICKOFF_MS + 3 * 24 * 60 * 60 * 1000;

describe("#3211 · startedWithoutResult", () => {
  test("the boundary is the grace, from both sides", () => {
    expect(startedWithoutResult("scheduled", KICKOFF, JUST_INSIDE)).toBe(false);
    expect(startedWithoutResult("scheduled", KICKOFF, JUST_OUTSIDE)).toBe(true);
  });

  test("a fixture that has not kicked off is untouched", () => {
    expect(startedWithoutResult("scheduled", KICKOFF, KICKOFF_MS - 60_000)).toBe(
      false,
    );
  });

  test("it is about the `scheduled` word, not about elapsed time", () => {
    // The control that stops the predicate becoming "anything old". A live
    // five-setter, a Final and a suspended match are all hours past kickoff and
    // none of them is a fixture nobody reported.
    for (const status of ["live", "completed", "closed", "suspended"]) {
      expect(startedWithoutResult(status, KICKOFF, DAYS_LATER)).toBe(false);
    }
  });

  test("an unplaceable row is left alone", () => {
    expect(startedWithoutResult("scheduled", null, DAYS_LATER)).toBe(false);
    expect(startedWithoutResult("scheduled", "", DAYS_LATER)).toBe(false);
    expect(startedWithoutResult("scheduled", "not a date", DAYS_LATER)).toBe(false);
  });
});

describe("#3211 · hasNoReportedResult is the DISPLAY question", () => {
  test("it covers both states a card must not print a start time for", () => {
    expect(hasNoReportedResult("suspended", KICKOFF, JUST_INSIDE)).toBe(true);
    expect(hasNoReportedResult("scheduled", KICKOFF, JUST_OUTSIDE)).toBe(true);
  });

  test("it leaves the healthy states alone", () => {
    expect(hasNoReportedResult("scheduled", KICKOFF, JUST_INSIDE)).toBe(false);
    expect(hasNoReportedResult("live", KICKOFF, DAYS_LATER)).toBe(false);
    expect(hasNoReportedResult("completed", KICKOFF, DAYS_LATER)).toBe(false);
    expect(hasNoReportedResult("closed", KICKOFF, DAYS_LATER)).toBe(false);
  });

  test("`isSuspendedStatus` stays NARROW and is not quietly widened", () => {
    // Two predicates, two jobs. Anything reasoning about the ladder's own
    // vocabulary (rather than about pixels) still needs the literal test, and
    // collapsing them would make `suspended` unnameable.
    expect(isSuspendedStatus("scheduled")).toBe(false);
    expect(isSuspendedStatus("suspended")).toBe(true);
  });
});

describe("#3211 · the section bucket", () => {
  test("a past-kickoff scheduled row is LIVE-bucketed, never upcoming", () => {
    expect(eventSectionKey("scheduled", KICKOFF, JUST_OUTSIDE)).toBe("live");
  });

  test("and is still upcoming inside the grace", () => {
    expect(eventSectionKey("scheduled", KICKOFF, JUST_INSIDE)).toBe("upcoming");
  });

  test("it is never filed as FINISHED — that would be a result it does not have", () => {
    expect(eventSectionKey("scheduled", KICKOFF, DAYS_LATER)).not.toBe("finished");
  });

  test("the pre-#3211 arms are unchanged", () => {
    expect(eventSectionKey("live", KICKOFF, DAYS_LATER)).toBe("live");
    expect(eventSectionKey("suspended", KICKOFF, DAYS_LATER)).toBe("live");
    expect(eventSectionKey("completed", KICKOFF, DAYS_LATER)).toBe("finished");
    expect(eventSectionKey("closed", KICKOFF, DAYS_LATER)).toBe("finished");
    expect(eventSectionKey("postponed", KICKOFF, DAYS_LATER)).toBe("upcoming");
  });

  test("⚠️ THE OMITTED-TIME ARM: a caller that passes no time gets the old answer", () => {
    // Pinned deliberately, because it is a live edge rather than an oversight.
    // The feed's candidate window is unchanged by #3211, so `lib/feedSections`
    // cannot yet receive one of these rows and is not forced to pass a time to
    // enable a branch nothing can reach. When that window is widened, THIS is
    // the assertion that has to change — and it failing is the reminder.
    expect(eventSectionKey("scheduled")).toBe("upcoming");
    expect(eventSectionKey("suspended")).toBe("live");
  });
});

describe("#3211 · the heading over the bucket", () => {
  test("it does not claim Live Now over a match nobody is watching", () => {
    const rows = [{ status: "scheduled", commence_time: KICKOFF }];
    const anyUnreported = rows.some((r) =>
      hasNoReportedResult(r.status, r.commence_time, JUST_OUTSIDE),
    );
    expect(liveSectionTitle(anyUnreported)).toBe("Live & Paused");
  });

  test("a genuinely live bucket still says Live Now", () => {
    const rows = [{ status: "live", commence_time: KICKOFF }];
    const anyUnreported = rows.some((r) =>
      hasNoReportedResult(r.status, r.commence_time, DAYS_LATER),
    );
    expect(liveSectionTitle(anyUnreported)).toBe("Live Now");
  });
});
