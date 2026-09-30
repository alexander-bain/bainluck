/**
 * #9867 — a settled chart on a phone hid the winner's line behind its RIGHT edge.
 *
 * `/futures/60770199` (Atlético Nacional vs. Millonarios FC — Halftime Result,
 * settled, Draw won), production, 390px, "All", 2026-09-30 16:13Z: the legend
 * read "● Millonarios FC ● Draw", no red Draw line was visible, and the axis
 * showed Sep 17 · Sep 18 · "Sep 2…". The served history was healthy: one
 * reading on Sep 17, six empty days, then ~170 readings per line Sep 22–25
 * with Draw climbing 0.31 → 0.9995.
 *
 * Mechanism: #6548 rests every settled chart on its LEFT edge, because on its
 * specimen (`/futures/110141`) the contest was early and the right edge a flat
 * run to 100%. Here the left edge is the empty gap, and the whole race sits in
 * the right 25% of the plot — off-screen at 390px. Neither fixed edge is right
 * for both boards; the anchor now rests on where the lines moved.
 */

import {
  anchorScrollLeft,
  maxScrollLeft,
  restingWindowStart,
  seriesMovementMarks,
} from "@/lib/chartScroll";

const PHONE = { scrollWidth: 600, clientWidth: 330 };
const FRAME = { width: 800, left: 50, right: 20 };

type Pt = { timestamp: string; probability: number | null };
const at = (iso: string, probability: number | null): Pt => ({ timestamp: iso, probability });

/** Readings every 30 min from `startIso`, linearly from `from` to `to`. */
function ramp(startIso: string, n: number, from: number, to: number): Pt[] {
  const t0 = new Date(startIso).getTime();
  return Array.from({ length: n }, (_, i) =>
    at(new Date(t0 + i * 30 * 60_000).toISOString(), from + ((to - from) * i) / (n - 1)),
  );
}

/** The 60770199 shape: a lone early reading, a six-day hole, a late race. */
const HALFTIME = [
  { history: [at("2026-09-17T07:40:00Z", 0.49), ...ramp("2026-09-23T22:00:00Z", 60, 0.205, 0.0005)] },
  { history: ramp("2026-09-22T11:30:00Z", 120, 0.313, 0.0005) },
  { history: ramp("2026-09-22T11:30:00Z", 120, 0.313, 0.9995) }, // Draw
];

/** The 110141 shape: the contest early, then a long flat run at the result. */
const EARLY_RACE = [
  { history: [...ramp("2026-03-20T00:00:00Z", 200, 0.6, 0.02), ...ramp("2026-07-01T00:00:00Z", 200, 0.02, 0.02)] },
  { history: [...ramp("2026-03-20T00:00:00Z", 200, 0.3, 0.98), ...ramp("2026-07-01T00:00:00Z", 200, 0.98, 0.98)] },
];

describe("#9867 — a settled chart rests where its lines moved", () => {
  test("the late-race specimen rests at the RIGHT edge, where Draw climbs to 100%", () => {
    const movement = seriesMovementMarks(HALFTIME, FRAME);
    expect(anchorScrollLeft(PHONE, { settled: true, movement })).toBe(maxScrollLeft(PHONE));
  });

  test("CONTROL (#6548): an early race still rests at the LEFT edge", () => {
    const movement = seriesMovementMarks(EARLY_RACE, FRAME);
    expect(anchorScrollLeft(PHONE, { settled: true, movement })).toBe(0);
  });

  test("CONTROL: live still rests at the right edge, whatever the movement says", () => {
    const movement = seriesMovementMarks(EARLY_RACE, FRAME);
    expect(anchorScrollLeft(PHONE, { settled: false, movement })).toBe(maxScrollLeft(PHONE));
  });

  test("no movement (flat lines, or none passed) falls back to #6548's left edge", () => {
    const flat = [{ history: ramp("2026-09-01T00:00:00Z", 50, 0.5, 0.5) }];
    expect(anchorScrollLeft(PHONE, { settled: true, movement: seriesMovementMarks(flat, FRAME) })).toBe(0);
    expect(anchorScrollLeft(PHONE, { settled: true })).toBe(0);
  });

  test("a plot that does not overflow rests at 0", () => {
    const movement = seriesMovementMarks(HALFTIME, FRAME);
    expect(anchorScrollLeft({ scrollWidth: 600, clientWidth: 1280 }, { settled: true, movement })).toBe(0);
  });

  test("a mid-plot race is CENTRED, not pushed against an edge", () => {
    // All movement between 40% and 50% of the width; window is 50% wide.
    const marks = [0.4, 0.42, 0.45, 0.5].map((a) => ({ at: a, weight: 0.1 }));
    expect(restingWindowStart(marks, 0.5)).toBeCloseTo(0.2, 10);
  });

  test("the window holding MORE movement wins, not the one holding more readings", () => {
    const quietButBusy = Array.from({ length: 40 }, (_, i) => ({ at: 0.05 + i * 0.005, weight: 0.001 }));
    const oneBigMove = [{ at: 0.9, weight: 0.5 }];
    expect(restingWindowStart([...quietButBusy, ...oneBigMove], 0.4)).toBe(0.6);
  });

  test("marks sit on the drawn x axis: first reading at padding.left, last at width - right", () => {
    const marks = seriesMovementMarks(
      [{ history: [at("2026-09-01T00:00:00Z", 0.2), at("2026-09-02T00:00:00Z", 0.5), at("2026-09-03T00:00:00Z", 0.6)] }],
      FRAME,
    );
    expect(marks.map((m) => m.at)).toEqual([(50 + 365) / 800, 780 / 800]);
    expect(marks[0].weight).toBeCloseTo(0.3, 10);
    expect(marks[1].weight).toBeCloseTo(0.1, 10);
  });

  test("null readings are skipped, not read as a move to zero", () => {
    const marks = seriesMovementMarks(
      [{ history: [at("2026-09-01T00:00:00Z", 0.5), at("2026-09-02T00:00:00Z", null), at("2026-09-03T00:00:00Z", 0.5)] }],
      FRAME,
    );
    expect(marks).toHaveLength(1);
    expect(marks[0].weight).toBe(0);
  });
});

describe("#9867 — FuturesChart hands the anchor the movement of what it DRAWS", () => {
  const CODE = require("fs")
    .readFileSync(require("path").join(__dirname, "../../components/FuturesChart.tsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  test("movement is computed from displayedOutcomes on the full-size frame", () => {
    expect(CODE).toMatch(
      /seriesMovementMarks\(\s*displayedOutcomes\s*,\s*\{\s*width:\s*FULL_CHART_WIDTH\s*,\s*left:\s*FULL_PADDING\.left\s*,\s*right:\s*FULL_PADDING\.right/,
    );
  });

  test("the plot draws on that same frame, so the anchor and the lines cannot drift", () => {
    expect(CODE).toMatch(/const chartWidth = mini \? MINI_CHART_WIDTH : FULL_CHART_WIDTH;/);
    expect(CODE).toMatch(/const padding = mini \? MINI_PADDING : FULL_PADDING;/);
  });
});
