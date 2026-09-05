/**
 * live/034 S2c — guards for the last-10-min sparkline.
 *
 * The ruling says last-10-min and says **no smoothing**. Both are properties a
 * sparkline can violate while still looking perfectly plausible on screen, so
 * they are tested on the pure functions rather than through the SVG:
 *
 * * a window that silently draws everything turns a "has it moved just now"
 *   glance into a whole-match summary;
 * * an auto-scaled y-axis turns a one-point wobble into a mountain — the exact
 *   false story this control must not tell;
 * * smoothing invents probabilities no source ever quoted, which on a ten-minute
 *   window is most of what you would be looking at.
 */

import { renderToStaticMarkup } from "react-dom/server";

import LiveSparkline, {
  MIN_SPAN,
  polylinePoints,
  sparklineDomain,
  windowPoints,
  type SparkPoint,
} from "@/components/event/LiveSparkline";

const NOW = Date.parse("2026-09-01T18:00:00Z");

function at(minutesAgo: number, value: number): SparkPoint {
  return {
    timestamp: new Date(NOW - minutesAgo * 60_000).toISOString(),
    value,
  };
}

describe("windowPoints — the window really is ten minutes", () => {
  test("keeps points inside the window and drops the rest", () => {
    const kept = windowPoints([at(30, 0.4), at(5, 0.5), at(1, 0.6)], 10, NOW);
    expect(kept.map((p) => p.value)).toEqual([0.5, 0.6]);
  });

  test("returns oldest first regardless of input order", () => {
    // Served series are chronological, but a pushed point is APPENDED, and an
    // out-of-order vertex would draw a line that doubles back on itself.
    const kept = windowPoints([at(1, 0.6), at(9, 0.4), at(5, 0.5)], 10, NOW);
    expect(kept.map((p) => p.value)).toEqual([0.4, 0.5, 0.6]);
  });

  test("an unparseable timestamp is dropped, not placed arbitrarily", () => {
    const kept = windowPoints(
      [{ timestamp: "not-a-date", value: 0.5 }, at(1, 0.6)],
      10,
      NOW,
    );
    expect(kept).toHaveLength(1);
  });

  test("a non-finite value is dropped", () => {
    const kept = windowPoints([{ timestamp: at(1, 0).timestamp, value: NaN }], 10, NOW);
    expect(kept).toHaveLength(0);
  });

  test("a whole-match series is clipped, not summarised", () => {
    const threeHours = Array.from({ length: 180 }, (_, i) => at(180 - i, 0.5));
    expect(windowPoints(threeHours, 10, NOW).length).toBeLessThanOrEqual(11);
  });
});

describe("sparklineDomain — the axis floor (#3313)", () => {
  test("the shared literal is 0.2, the number the phone also pins", () => {
    // ONE CONTRACT: LiveSparklineChart.minimumSpan carries the same value and
    // LiveSparklineDomainTests pins it there. Changing one side reddens the other.
    expect(MIN_SPAN).toBe(0.2);
  });

  test("a narrow series is widened to MIN_SPAN and centred on its data", () => {
    const [min, max] = sparklineDomain([0.5, 0.51, 0.5]);
    expect(max - min).toBeCloseTo(MIN_SPAN, 6);
    expect((min + max) / 2).toBeCloseTo(0.505, 6);
  });

  test("a series WIDER than MIN_SPAN keeps its own range — the floor is a floor", () => {
    const [min, max] = sparklineDomain([0.2, 0.65, 0.4]);
    expect(min).toBeCloseTo(0.2, 6);
    expect(max).toBeCloseTo(0.65, 6);
  });

  test("a range JUST under the floor is still widened, and only to the floor", () => {
    // 19 points, the Cubs-Marlins swing — under 0.2, so it widens to exactly 0.2
    // and the line uses 95% of the box rather than 19% of a full-range one.
    const [min, max] = sparklineDomain([0.16, 0.35, 0.22]);
    expect(max - min).toBeCloseTo(MIN_SPAN, 6);
    expect(min).toBeCloseTo(0.155, 6);
    expect(max).toBeCloseTo(0.355, 6);
  });

  test("a near-certain market slides inside [0,1] instead of squashing", () => {
    // 96% with the window centred would want [0.86, 1.06]. Clipping it to
    // [0.86, 1.0] would silently judge this series against a 14-point span while
    // every other glyph on the page used 20 — the same move would look bigger here.
    const [min, max] = sparklineDomain([0.95, 0.96, 0.97]);
    expect(max).toBeCloseTo(1, 6);
    expect(min).toBeCloseTo(0.8, 6);
    expect(max - min).toBeCloseTo(MIN_SPAN, 6);
  });

  test("a near-hopeless market slides the other way, same span", () => {
    const [min, max] = sparklineDomain([0.03, 0.04, 0.02]);
    expect(min).toBeCloseTo(0, 6);
    expect(max).toBeCloseTo(0.2, 6);
  });

  test("values outside 0-1 are clamped before the range is taken", () => {
    const [min, max] = sparklineDomain([-0.5, 0.5, 1.5]);
    expect(min).toBeGreaterThanOrEqual(0);
    expect(max).toBeLessThanOrEqual(1);
  });

  test("an empty series asks for no opinion and gets the full axis", () => {
    expect(sparklineDomain([])).toEqual([0, 1]);
  });
});

describe("polylinePoints — no smoothing, no auto-scale", () => {
  test("one vertex per served point — nothing is resampled or averaged", () => {
    const pts = [at(9, 0.4), at(6, 0.5), at(3, 0.6), at(0, 0.55)];
    const line = polylinePoints(windowPoints(pts, 10, NOW), 100, 20);
    expect(line.split(" ")).toHaveLength(4);
  });

  test("a one-point wobble stays visually flat — no auto-scaled mountain", () => {
    // The original rule's concern, and it still holds: auto-scaling to the data
    // would put these three at the top and bottom of the box, a dramatic
    // mountain built from a 1% move. The MIN_SPAN floor is what prevents it.
    const line = polylinePoints(
      windowPoints([at(5, 0.5), at(4, 0.51), at(3, 0.5)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    // 0.01 of a 0.2 span is 5% of the 18px usable height, i.e. under a pixel —
    // flat next to a 1.5px stroke. Asserted as a band, not a decimal: the exact
    // value depends on the coordinates' 1dp rounding, and the claim is "flat".
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(1);
    ys.forEach((y) => expect(Math.abs(y - 10)).toBeLessThanOrEqual(1));
  });

  test("a real swing is RESOLVED, not flattened — #3313, the bug this fixes", () => {
    // The Cubs-Marlins game measured on production 2026-09-05: 19 points of
    // travel inside the ten-minute window, the most dramatic thing on its page.
    // Under the old full-0-100 axis this drew 19% of a 20-high box = 3.8, and at
    // the shipping 24px height 4.6px — indistinguishable from noise. It must now
    // use most of the box.
    const line = polylinePoints(
      windowPoints([at(9, 0.35), at(6, 0.16), at(3, 0.22)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    const travel = Math.max(...ys) - Math.min(...ys);
    // 0.19 of a 0.2 span across the 18px usable height: nearly the whole box.
    expect(travel).toBeGreaterThan(16);
    expect(travel).toBeLessThanOrEqual(18);
    // The control that makes the number mean something: the OLD rule's output.
    const underFullRangeAxis = 0.19 * 20;
    expect(travel).toBeGreaterThan(underFullRangeAxis * 4);
  });

  test("a reading on the edge of the domain keeps its stroke inside the box", () => {
    // With a span floor the extremes ARE the domain edges whenever the range beats
    // the floor, so this is the common case now, not a corner one. A y of exactly
    // 0 or exactly `height` would draw half the stroke outside the SVG.
    const line = polylinePoints(
      windowPoints([at(9, 0.2), at(6, 0.45), at(3, 0.7)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    ys.forEach((y) => {
      expect(y).toBeGreaterThanOrEqual(1);
      expect(y).toBeLessThanOrEqual(19);
    });
  });

  test("the axis floor is MIN_SPAN, so travel scales with the size of the move", () => {
    // A guard against a fix that merely swapped one fixed axis for another: two
    // moves an order of magnitude apart must not draw the same shape.
    const box = 20;
    const ysFor = (a: number, b: number) =>
      polylinePoints(windowPoints([at(9, a), at(6, (a + b) / 2), at(3, b)], 10, NOW), 100, box)
        .split(" ")
        .map((p) => Number(p.split(",")[1]));
    const small = ysFor(0.5, 0.52);
    const large = ysFor(0.5, 0.7);
    const travel = (ys: number[]) => Math.max(...ys) - Math.min(...ys);
    expect(travel(small)).toBeLessThan(3);
    expect(travel(large)).toBeCloseTo(box - 2 * 1, 0); // the usable height
    expect(travel(large)).toBeGreaterThan(travel(small) * 5);
  });

  test("a probability outside 0-1 is clamped into the box", () => {
    const line = polylinePoints(
      windowPoints([at(5, -0.2), at(4, 0.5), at(3, 1.4)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    ys.forEach((y) => {
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(20);
    });
  });

  test("identical timestamps spread out instead of stacking on x=0", () => {
    const same = at(5, 0.5);
    const line = polylinePoints([same, { ...same, value: 0.6 }, { ...same, value: 0.7 }], 90, 20);
    const xs = line.split(" ").map((p) => Number(p.split(",")[0]));
    expect(new Set(xs).size).toBe(3);
  });

  test("too few points draw nothing rather than a misleading stub", () => {
    expect(polylinePoints([at(5, 0.5), at(4, 0.6)], 100, 20)).toBe("");
    expect(polylinePoints([], 100, 20)).toBe("");
  });
});

describe("LiveSparkline — what actually renders", () => {
  // The component reads the real clock, so these anchors are offsets FROM it
  // rather than from a fixed instant (gotcha #44). A fixed anchor here passes
  // only on the day it was written and then silently renders an empty window.
  const live = (minutesAgo: number, value: number): SparkPoint => ({
    timestamp: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    value,
  });

  test("an empty series renders nothing at all", () => {
    // Not a flat line: that would imply a steady market we have no readings for.
    expect(renderToStaticMarkup(<LiveSparkline points={[]} />)).toBe("");
  });

  test("a stale-only series renders nothing", () => {
    const old = Array.from({ length: 10 }, (_, i) => live(60 + i, 0.5));
    expect(renderToStaticMarkup(<LiveSparkline points={old} />)).toBe("");
  });

  test("a live series draws a polyline", () => {
    const html = renderToStaticMarkup(
      <LiveSparkline points={[live(9, 0.4), live(6, 0.5), live(3, 0.6)]} />,
    );
    expect(html).toContain("<polyline");
    expect(html).toContain('data-testid="live-sparkline"');
  });

  test("it carries an accessible label, not a bare graphic", () => {
    const html = renderToStaticMarkup(
      <LiveSparkline points={[live(9, 0.4), live(6, 0.5), live(3, 0.6)]} />,
    );
    expect(html).toContain('role="img"');
    expect(html).toContain("aria-label");
  });

  test("only the last ten minutes are drawn out of a longer series", () => {
    // The control: the same call with a whole match of history must draw the
    // SAME small number of vertices, or the window is not doing anything.
    const html = renderToStaticMarkup(
      <LiveSparkline
        points={[
          ...Array.from({ length: 120 }, (_, i) => live(180 - i, 0.3)),
          live(9, 0.4),
          live(6, 0.5),
          live(3, 0.6),
        ]}
      />,
    );
    expect(html).toContain('data-point-count="3"');
  });
});
