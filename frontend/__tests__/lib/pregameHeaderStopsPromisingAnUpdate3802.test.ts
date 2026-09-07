// #3802 — the poll ring stops promising "next update in 109 seconds" over a
// match 34 hours away.
//
// The defect, photographed on production at 390px on BOTH Tuesday US Open
// quarter-finals (/events/15306160 Sabalenka–Noskova and /events/15306225
// Tiafoe–Michelsen): the header ran a 109-second countdown beside "Starts in
// 1d 10h". The gate was `!isFinished && !streamConnected`, which has no notion
// of when the match actually is, so every scheduled event on the poll carried
// the ring — and as the third element in a `justify-between` row it wrapped the
// header into three ragged lines on a phone.
//
// The anchors here are OFFSET FIRST from a fixed `now` (gotcha #44): no branch
// on the wall clock, so this file reads the same at every hour of the day.

import {
  shouldShowRefreshCountdown,
  REFRESH_COUNTDOWN_WINDOW_MS,
} from "../../lib/eventKeyStats";

const NOW = new Date("2026-09-07T05:21:00.000Z");
const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;

/** A commence_time `ms` from NOW (negative = already started). */
function at(ms: number): string {
  return new Date(NOW.getTime() + ms).toISOString();
}

const BASE = {
  isFinished: false,
  streamConnected: false,
  isLive: false,
  isSuspended: false,
  now: NOW,
};

describe("#3802 shouldShowRefreshCountdown", () => {
  describe("THE DEFECT: a far-out pregame match gets no poll ring", () => {
    it("hides it on a quarter-final 34 hours away — the exact production case", () => {
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: at(34 * HOUR) }),
      ).toBe(false);
    });

    it("hides it 1d 10h out, which is what the hero said while the ring ran", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          commenceTime: at(34 * HOUR + 10 * MINUTE),
        }),
      ).toBe(false);
    });

    it("hides it just outside the window", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          commenceTime: at(REFRESH_COUNTDOWN_WINDOW_MS + MINUTE),
        }),
      ).toBe(false);
    });
  });

  describe("THE CONTROL: everything the ring was written for still shows it", () => {
    it("shows it on a live event", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          isLive: true,
          commenceTime: at(-2 * HOUR),
        }),
      ).toBe(true);
    });

    it("shows it on a suspended event — past its start, no result reported", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          isSuspended: true,
          commenceTime: at(-5 * HOUR),
        }),
      ).toBe(true);
    });

    it("shows it inside the window, ten minutes before the start", () => {
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: at(10 * MINUTE) }),
      ).toBe(true);
    });

    it("shows it exactly at the window edge — the boundary is inclusive", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          commenceTime: at(REFRESH_COUNTDOWN_WINDOW_MS),
        }),
      ).toBe(true);
    });

    it("shows it on a scheduled event already past its start time", () => {
      // Not yet flagged live or suspended, but the start is behind us: an
      // update genuinely could land any second. `<= window` covers negatives.
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: at(-30 * MINUTE) }),
      ).toBe(true);
    });
  });

  describe("the two pre-existing gates are untouched", () => {
    it("hides it on a finished event, however close the start was", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          isFinished: true,
          commenceTime: at(10 * MINUTE),
        }),
      ).toBe(false);
    });

    it("hides it on a pushed (streaming) event — the age stamp replaces it", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          streamConnected: true,
          isLive: true,
          commenceTime: at(-HOUR),
        }),
      ).toBe(false);
    });

    it("a finished event beats a live flag", () => {
      expect(
        shouldShowRefreshCountdown({
          ...BASE,
          isFinished: true,
          isLive: true,
          commenceTime: at(-HOUR),
        }),
      ).toBe(false);
    });
  });

  describe("an event we cannot place in time never gets a confident clock", () => {
    it("hides it when commence_time is missing", () => {
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: null }),
      ).toBe(false);
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: undefined }),
      ).toBe(false);
    });

    it("hides it when commence_time is unparseable", () => {
      expect(
        shouldShowRefreshCountdown({ ...BASE, commenceTime: "not a date" }),
      ).toBe(false);
    });

    it("BUT a live event with no start time still shows it", () => {
      // Liveness is established independently of the timestamp, so a missing
      // commence_time must not suppress the ring on a match in progress.
      expect(
        shouldShowRefreshCountdown({ ...BASE, isLive: true, commenceTime: null }),
      ).toBe(true);
    });
  });

  describe("the window agrees with the one already shipped as 'starting soon'", () => {
    it("is 3 hours, matching sportCategories.ts's hoursUntil <= 3", () => {
      expect(REFRESH_COUNTDOWN_WINDOW_MS).toBe(3 * 60 * 60 * 1000);
    });
  });
});
