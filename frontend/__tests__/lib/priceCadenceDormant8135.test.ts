/**
 * #8135 — AN OPEN BOARD THAT HAS STOPPED PRINTING NUMBERS DOES NOT PROMISE ONE.
 *
 * THE DEFECT, photographed on production 2026-09-23 at 390px. `/futures/59520336`
 * resolves 30 September and its status is `open`, so `isResolved` was false and
 * the card printed **"Prices update every 1–2 hours"** — directly above a chart
 * whose own caption read **"Last number 29 days ago"**. The gate was
 * `historyData.sparse ? priceCadenceNote(isResolved) : null`: how MUCH history
 * there is, and whether the question is decided. Neither asks whether any of that
 * history is recent, and that is the fact this promise is about.
 *
 * ── THE RULE IS THE PROMISE'S OWN BOUND, NOT `seriesFreshness`'s ──
 *
 * `seriesFreshness` marks a series `stale` at four times its OWN observed median
 * gap, and it fires on this specimen too. It is still the wrong instrument here:
 * it asks whether a line is behind its own cadence, while this string asserts a
 * SPECIFIC cadence of 1–2 hours. On a board whose median gap is a week the
 * cadence rule keeps the promise alive for a month. Two rules that agree on the
 * case that found them are separated by mechanism, not by the case — so the
 * board-level test below is pinned against a series the cadence rule would call
 * healthy.
 */

import {
  CADENCE_DORMANT_AFTER_MS,
  CADENCE_PROMISE_CEILING_MS,
  isCadenceDormant,
  priceCadenceNote,
} from "@/lib/priceCadenceCopy";
import { newestInstant, seriesFreshness } from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** 2026-09-23 14:20Z — when the defect was photographed. */
const NOW = Date.UTC(2026, 8, 23, 14, 20, 0);
/** The specimen's newest observation: 2026-08-25 01:19:15Z, 29 days back. */
const SPECIMEN_NEWEST = Date.UTC(2026, 7, 25, 1, 19, 15);

describe("#8135 — the promise, withdrawn", () => {
  it("says NOTHING on the specimen, rather than promising an hourly update", () => {
    expect(isCadenceDormant(SPECIMEN_NEWEST, NOW)).toBe(true);
    expect(priceCadenceNote(false, { dormant: true })).toBeNull();
    expect(priceCadenceNote(false, { dormant: true, long: true })).toBeNull();
  });

  it("does not replace it with a sentence explaining the silence", () => {
    // Notice 34. The card already carries "Last number 29 days ago" four lines
    // down; a second line qualifying the first is diagnostic prose. `null` is the
    // whole answer, and this asserts it rather than a string that merely differs.
    expect(priceCadenceNote(false, { dormant: true })).toBe(null);
  });

  it("CONTROL — a board that IS printing numbers keeps the promise, unchanged", () => {
    expect(isCadenceDormant(NOW - 90 * 60 * 1000, NOW)).toBe(false);
    expect(priceCadenceNote(false, { dormant: false })).toMatch(
      /Prices update every 1–2 hours/,
    );
    // ...and the default is the old behaviour, so no existing caller moved.
    expect(priceCadenceNote(false)).toBe(priceCadenceNote(false, { dormant: false }));
    expect(priceCadenceNote(false, { long: true })).toMatch(/for this market$/);
  });

  it("lets SETTLED outrank dormant — a decided board still says Final", () => {
    // Every settled board goes dormant eventually. If dormant won, "Final —
    // prices no longer update" would disappear from every old settled market and
    // #1803's ship would be silently undone.
    const settled = priceCadenceNote(true, { dormant: true });
    expect(settled).toMatch(/final/i);
    expect(settled).toBe(priceCadenceNote(true));
    expect(priceCadenceNote(true, { dormant: true, long: true })).toBe(settled);
  });

  it("puts the boundary at a full day, on the far side of equality", () => {
    // Catches `>` -> `>=` and any drift in the constant.
    expect(isCadenceDormant(NOW - CADENCE_DORMANT_AFTER_MS, NOW)).toBe(false);
    expect(isCadenceDormant(NOW - CADENCE_DORMANT_AFTER_MS - 1, NOW)).toBe(true);
    expect(CADENCE_PROMISE_CEILING_MS).toBe(2 * HOUR);
    expect(CADENCE_DORMANT_AFTER_MS).toBe(DAY);
  });

  it("claims nothing about a board it cannot date, in either direction", () => {
    // Absent is not dormant: the empty and sparse branches already own that case,
    // and an undatable payload supports no claim about freshness OR staleness.
    expect(isCadenceDormant(null, NOW)).toBe(false);
    expect(isCadenceDormant(undefined, NOW)).toBe(false);
    expect(isCadenceDormant(NaN, NOW)).toBe(false);
    // Venue clock skew puts a stamp slightly ahead of us. Not dormant.
    expect(isCadenceDormant(NOW + HOUR, NOW)).toBe(false);
  });

  it("is a DIFFERENT rule from seriesFreshness, on a series that separates them", () => {
    // A board polled weekly, last seen three days ago. Its own cadence says it is
    // perfectly healthy; the 1–2 hour promise is false about it anyway. If this
    // ever goes red because the two agree, the gate has been re-pointed at the
    // cadence machine and the docstring above is no longer true.
    const weekly = [0, 1, 2, 3, 4].map((i) => NOW - 3 * DAY - i * 7 * DAY);
    const freshness = seriesFreshness(weekly, NOW);
    expect(freshness.state).not.toBe("stale");
    expect(isCadenceDormant(newestInstant(weekly), NOW)).toBe(true);
  });
});

describe("#8135 — newestInstant, the board's last number", () => {
  it("takes the maximum, whatever order the payload arrives in", () => {
    const iso = (ms: number) => new Date(ms).toISOString();
    expect(newestInstant([iso(NOW - DAY), iso(NOW - HOUR), iso(NOW - 3 * DAY)])).toBe(
      NOW - HOUR,
    );
  });

  it("reads the same things `seriesFreshness` does, and skips the same junk", () => {
    // One parser, so what counts as a date cannot drift between the two callers.
    expect(newestInstant([NOW - HOUR, "not a date", null, undefined])).toBe(
      NOW - HOUR,
    );
    expect(newestInstant(["not a date", null])).toBeNull();
    expect(newestInstant([])).toBeNull();
    expect(newestInstant(null)).toBeNull();
  });

  it("agrees with seriesFreshness's own age on the same series", () => {
    const points = [NOW - 5 * HOUR, NOW - 3 * HOUR, NOW - 2 * HOUR, NOW - HOUR];
    const newest = newestInstant(points);
    expect(newest).not.toBeNull();
    expect(NOW - (newest as number)).toBe(seriesFreshness(points, NOW).ageMs);
  });
});
