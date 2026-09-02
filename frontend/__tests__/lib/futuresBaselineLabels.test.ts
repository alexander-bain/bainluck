/**
 * UX-P233 — THREE BASELINES ON ONE SCREEN, NONE LABELLED (TOP-PRODUCT-DEFECTS item 11).
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * On `/futures/109441` ("which company ships a fully AI-generated scripted series
 * before 2027"), all at once, all about Amazon:
 *
 *     hero pill        ↓ 71.5 pts          (no window stated at all)
 *     chart caption    "Amazon up 13.5 pts from opening."
 *     table row        Open: 14%   -71.5%   27%
 *
 * Alex, verbatim: **"Very confusing."** He is right, and the pair is worse than
 * unlabelled — it is arithmetically incoherent unless you already know the two
 * numbers have different baselines. A hero saying "down 71.5" beside a caption
 * saying "up 13.5" reads as a contradiction, not as two windows.
 *
 * ═══ WHAT THE PAYLOAD ACTUALLY SAYS ═══
 *
 * The live `GET /api/futures/109441` body, re-measured 2026-08-31 18:51Z:
 *
 *     Amazon   probability 0.27   opening 0.135   change_24h -0.715
 *              last_updated 2026-08-28T20:50Z          ← 2.9 DAYS AGO
 *
 * Every one of the eight outcomes carries that same `last_updated`. So:
 *
 * 1. 🔴 **"24h" IS A CLAIM THE PAYLOAD DISPROVES.** A field named
 *    `probability_change_24h` on a row last written 2.9 days ago cannot be a
 *    24-hour change, and CAL-P159 (board item 12) proved why: all four writers
 *    store `new − previous`, a PER-WRITE delta, and it FREEZES when a row stops
 *    being written. -0.715 is the Aug-18 → Aug-28 step. Printing "in the last 24h"
 *    beside it would be writing a false claim into the UI — the gotcha #53 class
 *    this board has blocked on repeatedly. **So the honest label cannot say 24h**,
 *    and this file's assertions forbid the word.
 *
 * 2. **The "current" number has no baseline either**, and the item did not name it.
 *    `27%` is presented as now; it is 2.9 days old. That is a fourth unlabelled
 *    baseline on the same screen.
 *
 * 3. **The sign can disagree with the journey.** Disney's badge reads **+1.5** while
 *    Disney went from an opening 22% to 7% — a 15-point FALL. Both facts are true of
 *    different windows, and with neither window stated the badge simply looks wrong.
 *
 * ═══ THE DONE-BAR ═══
 *
 * Alex's: *a reader can say what window each number is baselined on, without
 * hovering anything.* These helpers are how each number says it. This is copy and
 * labelling only — **no number's VALUE changes here**, and the arithmetic fix for
 * `probability_change_24h` stays board item 12's, in the calibration lane.
 */

import {
  asOfLabel,
  movementWindowLabel,
  priceAgeDays,
} from "@/lib/futuresDetailDisplay";

import market109441 from "../fixtures/uxp230_futures_109441.json";

interface Outcome {
  name: string;
  probability: number | null;
  opening_probability?: number | null;
  probability_change_24h?: number | null;
  last_updated?: string | null;
}

const AI_SERIES = market109441.outcomes as Outcome[];
const AMAZON = AI_SERIES.find((o) => o.name === "Amazon") as Outcome;
const DISNEY = AI_SERIES.find((o) => o.name === "Disney") as Outcome;

/** The instant the fixture was banked, so "how stale" is a fixed question. */
const BANKED_AT = new Date("2026-08-31T17:20:00Z");

describe("the fixture still carries the defect it was banked for (harness validity)", () => {
  test("every outcome was last written 2026-08-28 — the whole market is stale", () => {
    expect(AI_SERIES).toHaveLength(8);
    for (const o of AI_SERIES) {
      expect(o.last_updated).toMatch(/^2026-08-28T20:50/);
    }
  });

  test("Amazon is the pair Alex saw: -71.5 '24h' beside +13.5 from opening", () => {
    expect(AMAZON.probability).toBeCloseTo(0.27, 5);
    expect(AMAZON.opening_probability).toBeCloseTo(0.135, 5);
    expect(AMAZON.probability_change_24h).toBeCloseTo(-0.715, 5);
    // The two windows really do point opposite ways.
    const fromOpen = (AMAZON.probability as number) - (AMAZON.opening_probability as number);
    expect(fromOpen).toBeGreaterThan(0);
    expect(AMAZON.probability_change_24h as number).toBeLessThan(0);
  });

  test("Disney's badge sign disagrees with Disney's journey", () => {
    // +1.5 on the badge; 22% -> 7% overall. Neither is wrong; the screen just
    // never said which window either belonged to.
    expect(DISNEY.probability_change_24h).toBeCloseTo(0.015, 5);
    expect(DISNEY.opening_probability).toBeCloseTo(0.22, 5);
    expect(DISNEY.probability).toBeCloseTo(0.07, 5);
  });
});

describe("UX-P233: priceAgeDays measures the payload's own staleness", () => {
  test("Amazon reads 2.9 days stale at the moment the fixture was banked", () => {
    expect(priceAgeDays(AMAZON.last_updated, BANKED_AT)).toBeCloseTo(2.85, 1);
  });

  test("a missing or unparseable stamp is null, never zero", () => {
    // Zero would read as "fresh", which is absence dressed as a fact (gotcha #53).
    expect(priceAgeDays(null, BANKED_AT)).toBeNull();
    expect(priceAgeDays(undefined, BANKED_AT)).toBeNull();
    expect(priceAgeDays("not a date", BANKED_AT)).toBeNull();
  });

  test("a stamp in the future clamps to zero rather than going negative", () => {
    expect(priceAgeDays("2026-09-05T00:00:00Z", BANKED_AT)).toBe(0);
  });
});

describe("UX-P233: the movement pill states its window and never says 24h", () => {
  test("Amazon's pill is labelled as the last recorded move, with its date", () => {
    const label = movementWindowLabel(AMAZON.last_updated, BANKED_AT);
    expect(label).toBe("last move · Aug 28");
  });

  test("🔴 the label NEVER contains '24h' — the payload disproves that claim", () => {
    // The single most important assertion in this file. CAL-P159 proved the field
    // is a per-write delta that freezes; the row is 2.9 days old. Any label
    // asserting a 24-hour window is false on this very payload.
    for (const o of AI_SERIES) {
      const label = movementWindowLabel(o.last_updated, BANKED_AT);
      expect(label).not.toMatch(/24\s*h/i);
      expect(label).not.toMatch(/\bday\b/i);
      expect(label).not.toMatch(/\btoday\b/i);
    }
  });

  test("a fresh row still says 'last move' — the window is the WRITE, not the clock", () => {
    // Freshness changes whether we can date it usefully, not what the number IS.
    // A per-write delta on a row written ten minutes ago is still a per-write
    // delta, so the noun must not change with the clock.
    const fresh = movementWindowLabel("2026-08-31T16:00:00Z", BANKED_AT);
    expect(fresh).toContain("last move");
    expect(fresh).not.toMatch(/24\s*h/i);
  });

  test("no stamp ⇒ the window is named but not dated, never invented", () => {
    expect(movementWindowLabel(null, BANKED_AT)).toBe("last move");
    expect(movementWindowLabel("garbage", BANKED_AT)).toBe("last move");
  });
});

describe("UX-P233: the current number gets an as-of when it is not current", () => {
  test("a 2.9-day-old price says so instead of implying 'now'", () => {
    expect(asOfLabel(AMAZON.last_updated, BANKED_AT)).toBe("as of Aug 28");
  });

  test("a price written in the last 24h needs no as-of and gets none", () => {
    // Labelling a genuinely fresh number would be noise, not honesty.
    expect(asOfLabel("2026-08-31T09:00:00Z", BANKED_AT)).toBeNull();
    expect(asOfLabel("2026-08-30T23:00:00Z", BANKED_AT)).toBeNull();
  });

  test("the boundary is 24 hours and it is exercised from both sides", () => {
    // 23h59m before the reference: still fresh. 24h01m: stale.
    expect(asOfLabel("2026-08-30T17:21:00Z", BANKED_AT)).toBeNull();
    expect(asOfLabel("2026-08-30T17:19:00Z", BANKED_AT)).toBe("as of Aug 30");
  });

  test("no stamp ⇒ no as-of claim in either direction", () => {
    // We must not assert freshness we cannot prove, and must not assert staleness
    // we cannot prove either. Silence is the only honest answer.
    expect(asOfLabel(null, BANKED_AT)).toBeNull();
    expect(asOfLabel("garbage", BANKED_AT)).toBeNull();
  });
});

describe("UX-P233: the labels are stable regardless of where the GUARD runs", () => {
  /*
   * ⚠️ AMENDED BY UX-P260 (#2624). This block used to assert the opposite — that
   * the day was pinned to UTC "so a guard's answer never moves with the box". The
   * concern was real (a guard whose answer depends on where it runs is the trap
   * CERT-534 named), but it was paid for with a SHIPPED LABEL that was wrong for
   * every reader west of Greenwich: `/futures/1` printed "last move · Sep 2" at
   * 20:12 PT on Sep 1.
   *
   * The zone is now a parameter, which buys determinism without lying to the
   * reader — a guard names its zone, the app passes none and gets the reader's.
   * The assertions below are unchanged in VALUE and keep doing UX-P233's job of
   * pinning the label's wording and its refusal of "24h"; they simply no longer
   * claim that UTC is the right zone to show a person. The reader-facing rule is
   * asserted in `futuresLastMoveReaderZone.test.ts`.
   */
  test("an explicit zone makes the answer independent of the box", () => {
    // 2026-08-28T20:50Z is Aug 29 in Sydney and Aug 28 in Los Angeles. Naming the
    // zone is what makes this deterministic — not hiding the reader's zone.
    expect(movementWindowLabel("2026-08-28T20:50:07Z", BANKED_AT, "UTC")).toBe("last move · Aug 28");
    expect(asOfLabel("2026-08-28T20:50:07Z", BANKED_AT, "UTC")).toBe("as of Aug 28");
    expect(asOfLabel("2026-08-28T23:59:00Z", BANKED_AT, "UTC")).toBe("as of Aug 28");
    // The same instant, named for a reader who was in Sydney: the next day.
    expect(asOfLabel("2026-08-28T23:59:00Z", BANKED_AT, "Australia/Sydney")).toBe("as of Aug 29");
  });
});
