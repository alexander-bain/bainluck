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
  test("the live golf field from #4259 lands on 25%", () => {
    // McIlroy 11.9% is the leader of the eight-player field in the issue.
    // 0.119 * 1.15 = 0.137 → first rung that fits is 0.25.
    expect(ceilingForMax(0.119)).toBe(0.25);
  });

  test("Alex's own men's-board numbers still land where #2451 said", () => {
    expect(ceilingForMax(0.345)).toBe(0.5); // the #2451 worked example
    expect(ceilingForMax(0.445)).toBe(0.75); // the #3032 cliff this rung was added for
  });

  test("every answer is one of the five rungs, across the whole domain", () => {
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
