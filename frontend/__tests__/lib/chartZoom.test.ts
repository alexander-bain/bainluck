// L2-164: FuturesChart low-prob zoom chip math — fixed 0–100% is the default;
// zoom snaps to a rounded bound, and the chip is only eligible for low-prob,
// non-mini series. Both directions covered.
import { computeZoomBound, canZoomSeries, resolveYAxisMax } from "../../lib/chartZoom";

describe("computeZoomBound", () => {
  test("rounds up to a clean 5% step with headroom", () => {
    expect(computeZoomBound(0.18)).toBeCloseTo(0.2, 5); // 0.198 -> 0.20
    expect(computeZoomBound(0.04)).toBeCloseTo(0.05, 5); // tiny -> floor 0.05
    expect(computeZoomBound(0.21)).toBeCloseTo(0.25, 5); // 0.231 -> 0.25
  });

  test("never exceeds 1 and never drops below a 5% floor", () => {
    expect(computeZoomBound(0.95)).toBeLessThanOrEqual(1);
    expect(computeZoomBound(0)).toBeCloseTo(0.05, 5);
  });
});

describe("canZoomSeries", () => {
  test("eligible only when allowed, non-mini, and low-prob", () => {
    expect(canZoomSeries(0.12, true, false)).toBe(true);
  });
  test("never eligible when not allowed, in mini mode, or high-prob", () => {
    expect(canZoomSeries(0.12, false, false)).toBe(false); // opt-out default
    expect(canZoomSeries(0.12, true, true)).toBe(false); // sparkline
    expect(canZoomSeries(0.6, true, false)).toBe(false); // plenty of range already
    expect(canZoomSeries(0, true, false)).toBe(false); // no data
  });
});

describe("resolveYAxisMax", () => {
  const base = { dataMax: 0.18, fixedYAxis: true, allowZoom: true, mini: false };

  test("unzoomed → fixed 0–100% (max = 1)", () => {
    expect(resolveYAxisMax({ ...base, zoomed: false })).toBe(1);
  });

  test("zoomed → rounded bound from series max", () => {
    expect(resolveYAxisMax({ ...base, zoomed: true })).toBeCloseTo(0.2, 5);
  });

  test("zoom is ignored when the series isn't eligible (stays fixed)", () => {
    // High-prob series: zoom requested but not eligible → fixed 1.
    expect(resolveYAxisMax({ ...base, dataMax: 0.7, zoomed: true })).toBe(1);
    // Mini (sparkline): never zooms.
    expect(resolveYAxisMax({ ...base, mini: true, zoomed: true })).toBe(1);
  });

  test("auto-scale opt-out still works when fixedYAxis is false and not zoomed", () => {
    expect(resolveYAxisMax({ ...base, fixedYAxis: false, allowZoom: false, zoomed: false })).toBeCloseTo(
      0.198,
      5,
    );
  });
});
