/**
 * #6381 — THE POLL RING STOPS PROMISING AN UPDATE OVER A FIXTURE THAT IS OVER.
 *
 * ═══ WHAT A READER SAW (production, 390px, live/265 + live/266) ═══
 *
 * `/events/15310639` — Liverpool FC v Fulham FC, EPL, **3.6 days** past its own
 * kickoff — drew a running `Next update: 105` dial under a `No result reported`
 * hero, while one screen below its own markets read `Draw 0-0  Won`.
 * `/events/15304840` — Sabalenka v Townsend, US Open — did the same **9.6 days**
 * after the match. 426 such events in 30 days.
 *
 * ═══ THE MISSING HALF OF #3802's WINDOW ═══
 *
 * #3802 bounded the ring BEFORE a match (`REFRESH_COUNTDOWN_WINDOW_MS`, 3h out).
 * Nothing bounded it after. `isSuspended` at the call site
 * (`app/events/[id]/page.tsx`) is `hasNoReportedResult(status, commence_time)`,
 * and neither of its disjuncts has an upper bound: `startedWithoutResult` fires
 * from `UPCOMING_GRACE_MS` past kickoff *onwards, forever*, and
 * `isSuspendedStatus` reads the literal status with no clock at all. So the row
 * reached `if (isLive || isSuspended) return true` three days, three weeks or
 * three years late, and the ring is a `setInterval`.
 *
 * ═══ 🔴 WHY #5459's GUARD CANNOT COVER THIS ═══
 *
 * `liveClaimUnbacked` is checked first and exists to stop exactly this promise,
 * but it keys on `blendAgeMs` — the age of OUR NUMBER, not the staleness of the
 * match. A dead fixture whose markets are still being polled has a perfectly
 * fresh blend (#6263's `15307887` was quoted `BTTS Yes 99%` in its own capture),
 * so it is never unbacked and the ring survives. The population where the
 * countdown is most wrong is the one that guard is structurally blind to, which
 * is why the bound is a second, independent branch rather than a tuning change.
 *
 * ═══ WHAT THIS DELIBERATELY DOES NOT DO ═══
 *
 * It does not touch `hasNoReportedResult`. That predicate answers "print a start
 * time or print *No result reported*?", it is #3211's rail membership question,
 * and teaching it a clock un-rescues 171 US Open matches into the both-rails
 * hole — `event_completion.py:436` / `event_rails.py:374` say so at length. The
 * hero's *sentence* over a graded result is the other half of #6381 and needs a
 * served `venue_settled` signal (notice 46 pair, still open): a page that says
 * `No result reported` over a graded `Won` is still lying whether or not a ring
 * spins beside it. This ship removes the ring, which is one bound in one pure
 * function and is shared with #6263 and #6316's render half.
 *
 * Anchors are OFFSET FIRST from a fixed `now` (gotcha #44) — no branch on the
 * wall clock, so this file reads the same at every hour of the day.
 */

import {
  shouldShowRefreshCountdown,
  REFRESH_COUNTDOWN_MAX_AGE_MS,
} from "@/lib/eventKeyStats";

const NOW = new Date("2026-09-15T14:30:00.000Z");
const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** A commence_time `ms` from NOW (negative = already started). */
function at(ms: number): string {
  return new Date(NOW.getTime() + ms).toISOString();
}

const SUSPENDED = {
  isFinished: false,
  streamConnected: false,
  isLive: false,
  isSuspended: true,
  now: NOW,
};

describe("#6381 · a fixture days past its kickoff promises no update", () => {
  describe("THE DEFECT: the two production specimens", () => {
    it("hides the ring on Liverpool–Fulham, 3.6 days past kickoff", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-3.6 * DAY) }),
      ).toBe(false);
    });

    it("hides the ring on Sabalenka–Townsend, 9.6 days past kickoff", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-9.6 * DAY) }),
      ).toBe(false);
    });

    it("hides it on a literal `suspended` row a day old — #6263's population", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-1 * DAY) }),
      ).toBe(false);
    });
  });

  describe("THE BOUND ITSELF", () => {
    it("still promises at the last moment inside reach", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          commenceTime: at(-REFRESH_COUNTDOWN_MAX_AGE_MS),
        }),
      ).toBe(true);
    });

    it("stops one minute past it", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          commenceTime: at(-REFRESH_COUNTDOWN_MAX_AGE_MS - MINUTE),
        }),
      ).toBe(false);
    });
  });

  describe("BOTH DIRECTIONS (gotcha #43): what must keep its ring", () => {
    // The bound is only worth having if the case the ring was written for is
    // untouched. Every one of these returned `true` before the change.
    it("a match that has just kicked off and has no result yet", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-10 * MINUTE) }),
      ).toBe(true);
    });

    it("a match 3 hours past its start — inside every sport's duration", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-3 * HOUR) }),
      ).toBe(true);
    });

    it("an 8-hour golf round, the longest SPORT_MAX_DURATIONS entry", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(-8 * HOUR) }),
      ).toBe(true);
    });

    it("🔴 a LIVE event is never bounded — a Test match delivers for days", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          isLive: true,
          isSuspended: false,
          commenceTime: at(-4 * DAY),
        }),
      ).toBe(true);
    });

    it("a pregame match inside #3802's window keeps its ring", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          isSuspended: false,
          commenceTime: at(1 * HOUR),
        }),
      ).toBe(true);
    });

    it("a suspended row whose start is still AHEAD is left to the pregame case", () => {
      // A row can call itself `suspended` before its own kickoff. That is not
      // the dead-fixture population and the bound must not reach it.
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: at(2 * HOUR) }),
      ).toBe(true);
    });
  });

  describe("the branches above the bound still win", () => {
    it("a finished event gets nothing, bound or no bound", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          isFinished: true,
          commenceTime: at(-1 * HOUR),
        }),
      ).toBe(false);
    });

    it("#5459's withdrawn live claim still short-circuits inside reach", () => {
      expect(
        shouldShowRefreshCountdown({
          ...SUSPENDED,
          isLive: true,
          liveClaimUnbacked: true,
          commenceTime: at(-1 * HOUR),
        }),
      ).toBe(false);
    });
  });

  describe("an unreadable start time", () => {
    it("no commence_time is not a licence to promise an update", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: null }),
      ).toBe(false);
    });

    it("an unparseable commence_time is treated the same way", () => {
      expect(
        shouldShowRefreshCountdown({ ...SUSPENDED, commenceTime: "not a date" }),
      ).toBe(false);
    });
  });
});
