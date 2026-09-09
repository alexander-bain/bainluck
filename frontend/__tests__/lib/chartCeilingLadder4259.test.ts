/**
 * #4259 — THE SHARED #2451 CEILING LADDER.
 *
 * The ladder was Alex's ruling on the tournament ContenderChart ("Fix the scale, do
 * not smooth the line") and lived inside `contenderChart.ts`, so the other field
 * chart — FuturesChart, drawing the golf hub — never got it and reproduced the same
 * defect. These pin the rungs themselves, and `contenderChartScale.test.tsx` pins
 * that `chartCeiling` still behaves identically on top of them.
 */
import { CEILING_HEADROOM, CEILING_STEPS, ceilingForMax } from "../../lib/chartCeiling";
import { chartCeiling } from "../../lib/contenderChart";

describe("ceilingForMax — the rungs", () => {
  test("the live golf field from #4259 lands on the #4374 rung", () => {
    // McIlroy 11.9% is the leader of the eight-player field in the issue.
    // 0.119 * 1.15 = 0.137 → the first rung that fits WAS 0.25 (the field drew at
    // 47.6% of the plot). #4374 added 0.15 between them, so it now fits at 79.3%.
    expect(ceilingForMax(0.119)).toBe(0.15);
  });

  test("Alex's own men's-board numbers still land where #2451 said", () => {
    expect(ceilingForMax(0.345)).toBe(0.5); // the #2451 worked example
    expect(ceilingForMax(0.445)).toBe(0.75); // the #3032 cliff this rung was added for
  });

  /**
   * ═══ #4374: THE LADDER'S WIDEST GAP WAS A CLIFF ═══
   *
   * `0.1 → 0.25` was 2.5×, so a leader just over the 10 rung landed near the FLOOR
   * of the 25 rung: 8.69% drew at 86.9% of the plot and 8.70% at 34.8%, a 0.01pp
   * move halving every line. Same shape as #3032, one rung lower down.
   */
  test("a leader just over the 10 rung gets an axis, not a third of one", () => {
    expect(ceilingForMax(0.087)).toBe(0.15);
    expect(0.087 / ceilingForMax(0.087)).toBeGreaterThan(0.5); // was 0.348 on the 25 rung
    // The live golf field the issue was filed on: 48.9% of the plot → 81.5%.
    expect(ceilingForMax(0.1222)).toBe(0.15);
    expect(0.1222 / ceilingForMax(0.1222)).toBeCloseTo(0.815, 3);
  });

  /** The new step's two edges, so a later re-tune cannot quietly reopen the gap. */
  test("holds the 15 step from 8.70% to 13.04%", () => {
    expect(ceilingForMax(0.086)).toBe(0.1); // the last value the 10 step holds
    expect(ceilingForMax(0.087)).toBe(0.15);
    expect(ceilingForMax(0.13)).toBe(0.15); // the last value the 15 step holds
    expect(ceilingForMax(0.131)).toBe(0.25);
  });

  /**
   * The general clause behind both #3032 and #4374, as an invariant rather than a
   * worked example: a gap wider than 2× puts the leader below half the plot at the
   * bottom of the taller rung, which is the #2451 defect the ladder exists to fix.
   * Dropping either added rung reopens a 2.5× / 2.67× gap and fails here.
   */
  test("no two adjacent rungs are more than 2x apart", () => {
    for (let i = 1; i < CEILING_STEPS.length; i++) {
      const ratio = CEILING_STEPS[i] / CEILING_STEPS[i - 1];
      expect(ratio).toBeLessThanOrEqual(2 + 1e-9);
    }
  });

  test("every answer is one of the rungs, across the whole domain", () => {
    for (let p = 0; p <= 1.0001; p += 0.005) {
      expect(CEILING_STEPS).toContain(ceilingForMax(p) as (typeof CEILING_STEPS)[number]);
    }
  });

  test("the rung is never below the leader — a line can never be drawn off the plot", () => {
    // `Math.min(…, 1)` because the accumulator overshoots to 1.0000000000000007 and a
    // probability cannot exceed 1; the guard is about the ladder, not about float drift.
    for (let i = 1; i <= 1000; i++) {
      const p = Math.min(i / 1000, 1);
      expect(ceilingForMax(p)).toBeGreaterThanOrEqual(p);
    }
  });

  test("headroom: the leader is never welded to the frame until the axis is full", () => {
    for (let p = 0.001; p <= 0.87; p += 0.001) {
      expect(ceilingForMax(p)).toBeGreaterThanOrEqual(p * CEILING_HEADROOM - 1e-9);
    }
  });

  test("a high field keeps the plain 0–100% axis (the two-sided case is untouched)", () => {
    // 0.87 * 1.15 = 1.0005 → nothing below 1 fits, so the axis stays flat.
    expect(ceilingForMax(0.87)).toBe(1);
    expect(ceilingForMax(0.95)).toBe(1);
    expect(ceilingForMax(1)).toBe(1);
  });

  test("degenerate inputs fall back to the full axis rather than dividing by zero", () => {
    expect(ceilingForMax(0)).toBe(1);
    expect(ceilingForMax(-0.2)).toBe(1);
    expect(ceilingForMax(NaN)).toBe(1);
    expect(ceilingForMax(Infinity)).toBe(1);
  });

  test("monotonic: a bigger field never gets a smaller axis", () => {
    // Swept over real fields only. p == 0 is the degenerate "nothing drawn" case and
    // deliberately returns the FULL axis, not the lowest rung — an empty chart must
    // not imply a 10% world — so it is not part of the monotonic run.
    let prev = 0;
    for (let i = 1; i <= 500; i++) {
      const c = ceilingForMax(Math.min(i / 500, 1));
      expect(c).toBeGreaterThanOrEqual(prev);
      prev = c;
    }
  });
});

describe("the two charts cannot drift onto different ladders", () => {
  // The whole reason the ladder moved into its own module. If someone re-inlines a
  // ladder in either chart, these disagree.
  const series = (p: number) =>
    [
      {
        id: "x",
        name: "X",
        probability: p,
        points: [
          { at: "2026-09-01", probability: p },
          { at: "2026-09-02", probability: p },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any;

  test.each([0.02, 0.119, 0.24, 0.345, 0.445, 0.6, 0.9])(
    "chartCeiling and ceilingForMax agree at %p",
    (p) => {
      expect(chartCeiling(series(p), "ALL")).toBe(ceilingForMax(p));
    },
  );
});
