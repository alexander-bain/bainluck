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
  polylinePoints,
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

describe("polylinePoints — no smoothing, no auto-scale", () => {
  test("one vertex per served point — nothing is resampled or averaged", () => {
    const pts = [at(9, 0.4), at(6, 0.5), at(3, 0.6), at(0, 0.55)];
    const line = polylinePoints(windowPoints(pts, 10, NOW), 100, 20);
    expect(line.split(" ")).toHaveLength(4);
  });

  test("the y-axis is the full 0-100% range, not the data's own range", () => {
    // Two readings one point apart. Auto-scaling would put them at the top and
    // bottom of the box — a dramatic mountain built from a 1% move.
    const line = polylinePoints(
      windowPoints([at(5, 0.5), at(4, 0.51), at(3, 0.5)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    // All three sit near mid-height (y=10 of 20) and span well under a pixel-ish
    // fraction of the box, because the scale is absolute.
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThan(1);
    ys.forEach((y) => expect(Math.abs(y - 10)).toBeLessThan(1));
  });

  test("0% and 100% land on the box edges", () => {
    const line = polylinePoints(
      windowPoints([at(5, 0), at(4, 0.5), at(3, 1)], 10, NOW),
      100,
      20,
    );
    const ys = line.split(" ").map((p) => Number(p.split(",")[1]));
    expect(ys[0]).toBeCloseTo(20, 1); // 0% at the bottom
    expect(ys[2]).toBeCloseTo(0, 1); // 100% at the top
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
