/**
 * #7491 — a chart gap caption rounds the hole DOWN.
 *
 * Seen on production (`/futures/59165099`, 2026-09-20 12:45Z, v4810 `704cdc47`):
 * the Probability Trend card read **"No numbers for 3 days in this stretch"**
 * over a hole of **3 days 23 hours** — `2026-09-12T04:00:00Z` →
 * `2026-09-16T03:00:00Z`, computed from the 77 points the timeline actually
 * served. The caption understated our own gap by 23 hours.
 *
 * ═══ WHY THIS IS A TRUTH BUG AND NOT TIDINESS ═══
 *
 * Rounding direction is not a style choice; it is a claim, and which way is
 * "conservative" depends on what is being claimed:
 *
 *   - `seriesWindowLabel` names a window we are CLAIMING to cover. Rounding up
 *     would let a 29.6-day series be headed "30d" — an overstatement, and the
 *     one #3710 exists to stop. It floors, and must keep flooring.
 *   - `formatGapSpan` sizes a hole we are CONFESSING. Rounding down makes our
 *     coverage look better than it is — the same flattery, pointing the other
 *     way.
 *
 * Same rule, opposite direction, because the two sentences make opposite claims.
 * The predecessor floored at BOTH, and its own docstring gave the reason as "so
 * a hole is never flattered into a smaller one" — which is exactly what flooring
 * a hole does. The code contradicted its own stated intent, and the unit test
 * pinned the contradiction under a title that stated the intent correctly.
 *
 * ═══ WHAT THIS GUARD HOLDS ═══
 *
 * THE SHIP — the production specimen, and the general rule behind it.
 * THE CONTROL — `seriesWindowLabel` still FLOORS. This is the load-bearing arm:
 *   it is the assertion that would have caught a fix that "fixed the rounding"
 *   globally and silently re-opened #3710. It is asserted in the same file as
 *   the ship, on purpose, so the two directions can never drift apart unnoticed.
 * THE CALL SITES — the sentence a reader actually sees, through `seriesFreshness`,
 *   not just the formatter in isolation.
 * NO INFLATION — an exact multiple must not gain a unit to rounding dust, which
 *   is the way a ceiling fix typically goes wrong.
 */

import {
  GAP_FLOOR_MS,
  formatGapSpan,
  seriesFreshness,
  seriesWindowLabel,
} from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const MINUTE = 60 * 1000;

/** The hole the issue photographed, to the millisecond. */
const SPECIMEN_GAP_MS =
  Date.parse("2026-09-16T03:00:00Z") - Date.parse("2026-09-12T04:00:00Z");

describe("#7491 THE SHIP — a confessed hole rounds up", () => {
  it("the production specimen: a 3d23h hole is not called '3 days'", () => {
    // Guard the premise before the conclusion: if this is not 3d23h the
    // specimen has been mistranscribed and the assertion below proves nothing.
    expect(SPECIMEN_GAP_MS).toBe(3 * DAY + 23 * HOUR);

    expect(formatGapSpan(SPECIMEN_GAP_MS)).toBe("4 days");
    expect(formatGapSpan(SPECIMEN_GAP_MS)).not.toBe("3 days");
  });

  it("a part-day hole never loses its remainder", () => {
    expect(formatGapSpan(9.9 * DAY)).toBe("10 days");
    expect(formatGapSpan(2 * DAY + 1 * MINUTE)).toBe("3 days");
    expect(formatGapSpan(47.9 * HOUR)).toBe("48 hours");
    expect(formatGapSpan(90 * MINUTE)).toBe("2 hours");
    expect(formatGapSpan(30 * 1000)).toBe("1 min");
  });

  it("every hole of at least a day reads as at least as long as it is", () => {
    // The property behind the examples: the printed number, read back as its
    // own unit, is never SHORTER than the hole. A floor fails this at every
    // non-integral input; the old code failed it at 3d23h, 9.9d and 47.9h.
    for (const hours of [24, 25, 30, 47, 47.9, 48, 49, 71.5, 95, 96, 240, 345.6]) {
      const printed = formatGapSpan(hours * HOUR);
      const [n, unit] = printed.split(" ");
      const printedMs = unit.startsWith("day")
        ? Number(n) * DAY
        : unit.startsWith("hour")
          ? Number(n) * HOUR
          : Number(n) * MINUTE;
      expect(printedMs).toBeGreaterThanOrEqual(hours * HOUR);
    }
  });
});

describe("#7491 NO INFLATION — an exact multiple keeps its number", () => {
  it("exact spans do not gain a unit to rounding dust", () => {
    // The characteristic way a ceiling fix goes wrong: chaining the ceiling off
    // a previous unit's float makes `4 days` print "5 days". Each unit here is
    // ceiled from the raw milliseconds, so exact multiples are fixed points.
    expect(formatGapSpan(4 * DAY)).toBe("4 days");
    expect(formatGapSpan(10 * DAY)).toBe("10 days");
    expect(formatGapSpan(48 * HOUR)).toBe("2 days");
    expect(formatGapSpan(1 * HOUR)).toBe("1 hour");
    expect(formatGapSpan(2 * HOUR)).toBe("2 hours");
    expect(formatGapSpan(59 * MINUTE)).toBe("59 min");
  });

  it("nothing, or nonsense, is still '0 min' and never a throw", () => {
    // This module is a render path: a throw here is a blank page.
    expect(formatGapSpan(0)).toBe("0 min");
    expect(formatGapSpan(-5)).toBe("0 min");
    expect(formatGapSpan(NaN)).toBe("0 min");
    expect(formatGapSpan(Infinity)).toBe("0 min");
  });

  it("a hole is never suffixed 'ago' — it did not happen relative to now", () => {
    expect(formatGapSpan(345.6 * HOUR)).not.toMatch(/ago/);
  });
});

describe("#7491 THE CONTROL — a claimed WINDOW still floors (#3710)", () => {
  /**
   * The arm that makes the ship safe. `seriesWindowLabel` heads a column with
   * the window it covers; rounding IT up is the overstatement #3710 was filed
   * for. A fix that flipped the rounding in one shared place would pass every
   * assertion above and silently re-open that issue.
   */
  const spanning = (ms: number) => [[0, ms]];

  it("a 29.6-day window is still headed '29d', never '30d'", () => {
    expect(seriesWindowLabel(spanning(29.6 * DAY))).toBe("29d");
    expect(seriesWindowLabel(spanning(29.6 * DAY))).not.toBe("30d");
  });

  it("the window label floors at every unit, opposite to the gap formatter", () => {
    expect(seriesWindowLabel(spanning(47.9 * HOUR))).toBe("47h");
    expect(seriesWindowLabel(spanning(59.9 * MINUTE))).toBe("59m");
    // The two functions are asked the same question and must disagree, each in
    // its own conservative direction. This is the whole of #7491 in one line.
    expect(seriesWindowLabel(spanning(9.9 * DAY))).toBe("9d");
    expect(formatGapSpan(9.9 * DAY)).toBe("10 days");
  });

  it("an undatable column is still unlabellable, not zero", () => {
    expect(seriesWindowLabel([[], null, undefined])).toBeNull();
  });
});

describe("#7491 THE CALL SITE — the sentence a reader is shown", () => {
  /**
   * The formatter is only half the ship: the caption is built inside
   * `seriesFreshness`, and a test of the formatter alone cannot see a call site
   * that was never rewired. This renders the real note from a real series.
   */
  it("the chart's gap note states the rounded-up hole", () => {
    // An hourly series with the specimen's hole punched into the middle of it.
    const start = Date.parse("2026-09-08T00:00:00Z");
    const before = Array.from({ length: 24 }, (_, i) => start + i * HOUR);
    const holeStart = before[before.length - 1];
    const after = Array.from(
      { length: 24 },
      (_, i) => holeStart + SPECIMEN_GAP_MS + i * HOUR,
    );
    const now = after[after.length - 1] + HOUR;

    const f = seriesFreshness([...before, ...after], now);

    expect(f.largestGapMs).toBe(SPECIMEN_GAP_MS);
    expect(f.state).toBe("gapped");
    expect(f.note).toBe("No numbers for 4 days in this stretch");
    expect(f.note).not.toContain("3 days");
  });

  it("a hole just over the floor is described, not swallowed", () => {
    // Confirms the ceiling did not make the note fire earlier or later than the
    // floor it is gated on — the gap threshold is unchanged by this ship.
    const start = Date.parse("2026-09-08T00:00:00Z");
    const cadence = 10 * 60 * 1000;
    const before = Array.from({ length: 12 }, (_, i) => start + i * cadence);
    const holeStart = before[before.length - 1];
    const gap = GAP_FLOOR_MS + MINUTE;
    const after = Array.from({ length: 12 }, (_, i) => holeStart + gap + i * cadence);

    const f = seriesFreshness([...before, ...after], after[after.length - 1] + cadence);

    expect(f.largestGapMs).toBe(gap);
    expect(f.note).toBe("No numbers for 3 hours in this stretch");
  });
});
