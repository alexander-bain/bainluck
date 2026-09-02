/**
 * UX-P260 (#2624) — THE "LAST MOVE" PILL AGREES WITH THE READER'S CLOCK.
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * `/futures/1` ("MLB World Series Winner"), shot at **20:12 PT on Sep 1**:
 *
 *     hero pill        31%   ↑ 0.2 pts   last move · Sep 2      ← TOMORROW
 *     chart x-axis     … Sep 1 5 PM                             ← the same instant
 *
 * The site dated a price move in the future, and contradicted itself 400px down
 * the same page. For any US reader that is EVERY move after 17:00 PT. On a
 * product whose pitch is an honest reading of what the world thinks right now, a
 * "last move" tomorrow reads as broken data, and it is checkable against the
 * reader's own phone in one glance.
 *
 * ═══ WHY THE OBVIOUS GUARD IS VACUOUS, AND THIS ONE IS NOT ═══
 *
 * 🔴 `jest.config.js` pins `process.env.TZ = 'UTC'` for the whole suite (#2462,
 * and it must live in the config because a realm is born before `setupFiles`).
 * So inside jest **local ≡ UTC**, and the tempting assertion —
 *
 *     expect(movementWindowLabel("2026-09-02T00:31:47Z", NOW)).toBe("last move · Sep 1")
 *
 * — is green on the FIXED code and green on BROKEN master, because both render
 * Sep 2 in a UTC realm. It asserts nothing. That is the "string common to both
 * arms" trap, and it is why the fix threads an explicit `timeZone` parameter
 * instead of merely deleting a constant: the parameter is what lets a guard name
 * a zone and stay deterministic wherever the box happens to live. Every arm below
 * that carries the claim passes an explicit zone.
 *
 * Red-first, verified against clean master (`86a15dcf`): master ignores the third
 * argument, so it answers "Sep 2" where the reader's zone says "Sep 1" — the four
 * claim arms fail on the RETURNED VALUE, printing the defect verbatim, not on a
 * missing import. Both symbols already exist on master, so there is nothing to
 * lazy-require.
 *
 * ═══ THE RULE BEING PINNED ═══
 *
 * **A calendar date is not an instant.** A tournament runs Sep 3–6 wherever you
 * stand, so date-only values MUST be UTC-pinned — that is what stops "2026-09-05"
 * sliding to Sep 4 in Los Angeles, and `gameTimeLabel.ts` has said so since C270:
 * *"Timestamps keep local formatting — those really are instants."* A price move
 * happened at one moment, so its day is the reader's day. This file asserts both
 * halves, because a future lane reading "#2624 removed a UTC pin" could easily
 * remove the seven that are correct.
 */

import {
  asOfLabel,
  movementWindowLabel,
  priceAgeDays,
} from "@/lib/futuresDetailDisplay";
import { formatResolvesLabel } from "@/lib/gameTimeLabel";

/**
 * Alex's instant, to the second: `futures_outcomes.last_updated` for the LA
 * Dodgers in market 1 at the moment of the shot. Sep **2** in UTC, Sep **1** for
 * the reader who was looking at it.
 */
const ALEX_INSTANT = "2026-09-02T00:31:47.000Z";

/** ~40 minutes after the shot, so the price reads as fresh (age < 1 day). */
const SHOT_AT = new Date("2026-09-02T00:52:00.000Z");

const LA = "America/Los_Angeles";
const SYDNEY = "Australia/Sydney";

describe("UX-P260: a price move is dated in the reader's zone, not in UTC", () => {
  test("Alex's exact pill stops saying tomorrow", () => {
    // Master: "last move · Sep 2" — the defect, verbatim.
    expect(movementWindowLabel(ALEX_INSTANT, SHOT_AT, LA)).toBe(
      "last move · Sep 1",
    );
  });

  test("the second label on the same page moves with it", () => {
    // `asOfLabel` shares the formatter and appears above the All Outcomes table,
    // so the page had TWO labels a day ahead, not one. Aged past the 1-day
    // threshold so the label is emitted at all.
    const twoDaysLater = new Date("2026-09-04T01:00:00.000Z");
    expect(asOfLabel(ALEX_INSTANT, twoDaysLater, LA)).toBe("as of Sep 1");
  });

  test("it follows the reader FORWARD too — this is not a blanket minus-one-day", () => {
    // 2026-09-01T20:00Z is still Sep 1 in UTC but already Sep 2 in Sydney. A fix
    // that merely subtracted a day would answer "Sep 1" here and be wrong in the
    // other direction; the label has to track the zone, not lag it.
    const eveningUtc = "2026-09-01T20:00:00.000Z";
    const soonAfter = new Date("2026-09-01T21:00:00.000Z");
    expect(movementWindowLabel(eveningUtc, soonAfter, SYDNEY)).toBe(
      "last move · Sep 2",
    );
    // ...and the very same instant is still Sep 1 for a Los Angeles reader.
    expect(movementWindowLabel(eveningUtc, soonAfter, LA)).toBe(
      "last move · Sep 1",
    );
  });

  test("no reader is ever shown a move dated after their own today", () => {
    // The property the pill actually owes a user, stated once over several zones
    // rather than as a list of dates. `en-US` "Sep 1" sorts badly, so compare the
    // ISO day each zone reports for the instant against the day it reports for
    // "now" — the label may equal today, never exceed it.
    const zones = [LA, "America/New_York", "Europe/London", SYDNEY, "UTC"];
    const isoDayIn = (when: Date, timeZone: string) =>
      new Intl.DateTimeFormat("en-CA", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZone,
      }).format(when);

    for (const zone of zones) {
      const label = movementWindowLabel(ALEX_INSTANT, SHOT_AT, zone);
      const labelledDay = isoDayIn(new Date(ALEX_INSTANT), zone);
      const readersToday = isoDayIn(SHOT_AT, zone);
      expect(labelledDay <= readersToday).toBe(true);
      // And the label really is built from that day, not from some other one.
      const expectedDay = new Date(`${labelledDay}T12:00:00Z`).toLocaleDateString(
        "en-US",
        { month: "short", day: "numeric", timeZone: "UTC" },
      );
      expect(label).toBe(`last move · ${expectedDay}`);
    }
  });
});

/* ───────────────────────────────────────────────────────────────────────────
 * CONTROLS — every one of these is green on clean master AND on the fix. If any
 * of them moves, the change did more than re-zone a label.
 * ─────────────────────────────────────────────────────────────────────────── */

describe("UX-P260 controls: nothing but the zone changed", () => {
  test("an instant in the middle of the UTC day reads the same in both zones", () => {
    // 2026-08-28T18:00Z is Aug 28 in UTC and Aug 28 in Los Angeles. If the fix
    // had shifted every label rather than re-zoning it, this would move.
    const midday = "2026-08-28T18:00:00.000Z";
    const later = new Date("2026-08-28T19:00:00.000Z");
    expect(movementWindowLabel(midday, later, LA)).toBe("last move · Aug 28");
    expect(movementWindowLabel(midday, later, "UTC")).toBe("last move · Aug 28");
  });

  test("a payload with no stamp still gets no date, and no invented one", () => {
    expect(movementWindowLabel(null, SHOT_AT, LA)).toBe("last move");
    expect(movementWindowLabel(undefined, SHOT_AT, LA)).toBe("last move");
    expect(movementWindowLabel("garbage", SHOT_AT, LA)).toBe("last move");
    expect(asOfLabel(null, SHOT_AT, LA)).toBeNull();
    expect(asOfLabel("garbage", SHOT_AT, LA)).toBeNull();
  });

  test("the as-of threshold is untouched — a fresh price still earns no chip", () => {
    // Zone cannot be allowed to leak into the AGE arithmetic, which is epoch
    // milliseconds and never had a zone to get wrong.
    expect(asOfLabel(ALEX_INSTANT, SHOT_AT, LA)).toBeNull();
    expect(asOfLabel(ALEX_INSTANT, SHOT_AT, SYDNEY)).toBeNull();
    expect(priceAgeDays(ALEX_INSTANT, SHOT_AT)).toBeCloseTo(0.014, 2);
  });

  test("the pill still refuses the word 24h", () => {
    // UX-P233's binding: `probability_change_24h` is a per-write delta that
    // freezes, so no label may call it a 24-hour change. Re-zoning must not have
    // reopened that.
    expect(movementWindowLabel(ALEX_INSTANT, SHOT_AT, LA)).not.toMatch(/24h/);
    expect(asOfLabel(ALEX_INSTANT, new Date("2026-09-05T00:00:00Z"), LA)).not.toMatch(
      /24h/,
    );
  });
});

describe("UX-P260: the calendar-date pin survives — a date is not an instant", () => {
  test("a date-only resolution date is still read as UTC", () => {
    // The counter-case, and the reason it is in THIS file: #2624 removes a UTC
    // pin, and the next lane to read that could remove the seven that are right.
    // `2026-12-31` carries no time and no zone; parsed as UTC midnight it must
    // still print Dec 31 for a Los Angeles reader, not Dec 30.
    const label = formatResolvesLabel(
      "2026-12-31",
      new Date("2026-12-01T12:00:00Z").getTime(),
    );
    expect(label).toContain("Dec 31");
    expect(label).not.toContain("Dec 30");
  });
});
