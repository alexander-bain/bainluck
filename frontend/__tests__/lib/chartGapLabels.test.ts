/**
 * #11929 C — `placeGapLabels`: which holes a full chart names, in what words,
 * and where. The component wiring is pinned in
 * `__tests__/components/aLongGapCarriesTheEventChartsLabel11929c.test.tsx`.
 */

import {
  MIN_LABELLED_HOLE_SHARE,
  gapLabelWidth,
  holeIsLabelled,
  placeGapLabels,
  type GapLabel,
  type GapLabelFrame,
} from "../../lib/chartGapLabels";
import type { ChartHole } from "../../lib/chartSeriesPath";
import { formatGapSpan, gapNote, seriesFreshness } from "../../lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const T0 = Date.UTC(2026, 10, 1, 0, 0, 0);
// The full chart's plot at height 200: x 50→780, y 20→160.
const FRAME: GapLabelFrame = { left: 50, right: 780, top: 20, bottom: 160 };
/** A 168 h window across the plot. */
const xAt = (h: number) => 50 + (h / 168) * 730;

function hole(fromH: number, toH: number, y = 90, toY = y): ChartHole {
  return {
    from: { t: T0 + fromH * HOUR, x: xAt(fromH), y },
    to: { t: T0 + toH * HOUR, x: xAt(toH), y: toY },
  };
}

/**
 * The same, on a `windowH`-hour window. A label sits inside its own hole, so a
 * 37 h hole is labelled only where it is drawn wider than its ~250-unit
 * sentence — on a 4-day window, not a week.
 */
function holeIn(windowH: number, fromH: number, toH: number, y = 90): ChartHole {
  const x = (h: number) => 50 + (h / windowH) * 730;
  return {
    from: { t: T0 + fromH * HOUR, x: x(fromH), y },
    to: { t: T0 + toH * HOUR, x: x(toH), y },
  };
}

/** The label's box, as the placement estimates it, sits between its hole's two readings. */
function expectInsideItsHole(label: GapLabel) {
  const w = gapLabelWidth(label.text);
  expect(label.x - w / 2).toBeGreaterThanOrEqual(label.fromX);
  expect(label.x + w / 2).toBeLessThanOrEqual(label.toX);
}

describe("gapNote — the caption's sentence, shared", () => {
  test("the caption's gapped arm prints exactly gapNote of its largest hole", () => {
    const stamps = [0, 1, 2, 3, 40, 41, 42].map((h) => T0 + h * HOUR);
    const f = seriesFreshness(stamps, T0 + 42.1 * HOUR);
    expect(f.state).toBe("gapped");
    expect(f.note).toBe(gapNote(37 * HOUR));
    expect(f.note).toBe("No numbers for 37 hours in this stretch");
  });

  test("same units and the same round-UP rule as formatGapSpan", () => {
    for (const ms of [0.5 * HOUR, 3.2 * HOUR, 47.5 * HOUR, 60 * HOUR, 96 * HOUR]) {
      expect(gapNote(ms)).toBe(`No numbers for ${formatGapSpan(ms)} in this stretch`);
    }
    expect(gapNote(60 * HOUR)).toBe("No numbers for 3 days in this stretch");
  });
});

describe("placeGapLabels", () => {
  test("no holes, no labels", () => {
    expect(placeGapLabels([], FRAME)).toEqual([]);
  });

  test("one hole: its sentence, centred on the stretch, just above the line", () => {
    // A 37 h hole on a 4-day window: 281 units, room for its 250-unit sentence.
    const h = holeIn(96, 30, 67, 90);
    const [label, ...rest] = placeGapLabels([h], FRAME);
    expect(rest).toEqual([]);
    expect(label.text).toBe("No numbers for 37 hours in this stretch");
    expect(label.x).toBeCloseTo((h.from.x + h.to.x) / 2, 9);
    expect(label.y).toBeLessThan(90);
    expect(label.ms).toBe(37 * HOUR);
    expectInsideItsHole(label);
  });

  test("a hole at the plot's edge too narrow for its sentence gets NO label — never slid over the readings beside it", () => {
    // 18 h at the right edge of a week is 78 units; its sentence is ~250. The
    // old centre-then-clamp slid it left over 170 units of real readings.
    expect(placeGapLabels([hole(150, 168)], FRAME)).toEqual([]);
    // The same at the left edge (the old clamp pinned it against the y-axis).
    expect(placeGapLabels([hole(0, 18)], FRAME)).toEqual([]);
  });

  test("a hole at the plot's edge wide enough for its sentence is labelled inside it", () => {
    for (const h of [hole(100, 168), hole(0, 68)]) {
      const [label, ...rest] = placeGapLabels([h], FRAME);
      expect(rest).toEqual([]);
      expect(label.x).toBeCloseTo((h.from.x + h.to.x) / 2, 9);
      expectInsideItsHole(label);
      expect(label.x + gapLabelWidth(label.text) / 2).toBeLessThanOrEqual(FRAME.right);
      expect(label.x - gapLabelWidth(label.text) / 2).toBeGreaterThanOrEqual(FRAME.left);
    }
  });

  test("a line at the ceiling puts its label inside the plot, never above it", () => {
    const [label] = placeGapLabels([hole(40, 100, 20)], FRAME);
    expect(label.y).toBeGreaterThan(FRAME.top);
    expect(label.y).toBeLessThan(FRAME.bottom);
  });

  test("lines sharing one stretch share one label, sized by the longest", () => {
    const labels = placeGapLabels(
      [hole(40, 100, 60), hole(40, 100, 120), hole(40, 100.5, 140)],
      FRAME,
    );
    expect(labels).toHaveLength(1);
    expect(labels[0].ms).toBe(60.5 * HOUR);
    // Above the topmost of the lines it explains.
    expect(labels[0].y).toBeLessThan(60);
  });

  test("holes that only partly overlap are different stretches", () => {
    const labels = placeGapLabels([hole(0, 70, 50), hole(40, 110, 140)], FRAME);
    expect(labels).toHaveLength(2);
    labels.forEach(expectInsideItsHole);
  });

  test("labels never overlap, and the longest hole always gets one", () => {
    // Five lines' holes, partly overlapping (never one stretch), at nearly the
    // same height, every one wide enough for its sentence: the placement must
    // stack or drop them, never print one over another.
    const holes = [
      hole(0, 75, 90),
      hole(10, 80, 92),
      hole(20, 100, 89),
      hole(60, 130, 88),
      hole(100, 168, 91),
    ];
    const labels = placeGapLabels(holes, FRAME);
    expect(labels.map((l) => l.ms)).toContain(80 * HOUR);
    expect(labels.length).toBeGreaterThanOrEqual(2);
    labels.forEach(expectInsideItsHole);
    for (let i = 0; i < labels.length; i += 1) {
      for (let j = i + 1; j < labels.length; j += 1) {
        const a = labels[i];
        const b = labels[j];
        const xApart =
          Math.abs(a.x - b.x) >= (gapLabelWidth(a.text) + gapLabelWidth(b.text)) / 2;
        const yApart = Math.abs(a.y - b.y) >= 13;
        expect(xApart || yApart).toBe(true);
      }
    }
    // Returned in time order.
    expect(labels.map((l) => l.fromT)).toEqual([...labels.map((l) => l.fromT)].sort((p, q) => p - q));
  });

  test("a hairline hole — under 1% of the plot wide — is not labelled", () => {
    expect(MIN_LABELLED_HOLE_SHARE).toBe(0.01);
    // On the real 730-unit plot a 1% hole (7 units) can never hold its sentence,
    // so the fit rule already drops it. The 1% rule still holds on its own: on
    // a plot wide enough for the sentence to fit inside a 0.9% hole, the
    // hairline is still dropped and a 1.1% hole is labelled.
    const wide: GapLabelFrame = { left: 0, right: 40_000, top: 20, bottom: 160 };
    const plotW = wide.right - wide.left;
    const span = (share: number): ChartHole => ({
      from: { t: T0, x: 10_000, y: 90 },
      to: { t: T0 + 20 * HOUR, x: 10_000 + plotW * share, y: 90 },
    });
    expect(plotW * 0.009).toBeGreaterThan(gapLabelWidth(gapNote(20 * HOUR)) + 6);
    expect(placeGapLabels([span(0.009)], wide)).toEqual([]);
    expect(placeGapLabels([span(0.011)], wide)).toHaveLength(1);
    // On the real plot, a hole past the hairline but narrower than its sentence: no label.
    const visibleH = (((FRAME.right - FRAME.left) * 0.011) / 730) * 168;
    expect(placeGapLabels([hole(80, 80 + visibleH)], FRAME)).toEqual([]);
  });

  test("guard (production 2026-11-04): every placed label lies inside its own hole, wherever the hole sits", () => {
    // Holes from 5 h to 120 h wide, swept from the left edge to the right edge
    // of a week, alone and in pairs. Under the old centre-then-clamp every
    // narrow edge hole printed a label over the readings beside it.
    let placed = 0;
    let dropped = 0;
    for (const widthH of [5, 18, 37, 55, 60, 72, 96, 120]) {
      for (let fromH = 0; fromH + widthH <= 168; fromH += 4) {
        for (const set of [[hole(fromH, fromH + widthH)], [hole(fromH, fromH + widthH, 40), hole(0, 168, 140)]]) {
          const labels = placeGapLabels(set, FRAME);
          for (const l of labels) expectInsideItsHole(l);
          placed += labels.length;
        }
        // Pinned at both edges, too.
        for (const edge of [hole(0, widthH), hole(168 - widthH, 168)]) {
          const labels = placeGapLabels([edge], FRAME);
          labels.forEach(expectInsideItsHole);
          if (labels.length === 0) dropped += 1;
        }
      }
    }
    // Not vacuous: the sweep both places labels and refuses them.
    expect(placed).toBeGreaterThan(50);
    expect(dropped).toBeGreaterThan(50);
  });

  test("holeIsLabelled: a hole is covered by the label of its own stretch, and only that", () => {
    const wideHole = hole(40, 110, 60);
    const sameStretch = hole(40, 110.5, 120); // another line, one stretch
    const narrow = hole(150, 168, 60);
    const labels = placeGapLabels([wideHole, sameStretch, narrow], FRAME);
    expect(labels).toHaveLength(1);
    expect(holeIsLabelled(wideHole, labels)).toBe(true);
    expect(holeIsLabelled(sameStretch, labels)).toBe(true);
    expect(holeIsLabelled(narrow, labels)).toBe(false);
    // A hole that only partly overlaps the labelled stretch is not covered by it.
    expect(holeIsLabelled(hole(70, 140, 60), labels)).toBe(false);
    expect(holeIsLabelled(wideHole, [])).toBe(false);
  });

  test("total: NaN stamps, backwards holes and NaN pixels produce no label and no throw", () => {
    const bad: ChartHole[] = [
      { from: { t: NaN, x: 100, y: 90 }, to: { t: T0, x: 200, y: 90 } },
      { from: { t: T0 + HOUR, x: 200, y: 90 }, to: { t: T0, x: 100, y: 90 } },
      { from: { t: T0, x: NaN, y: 90 }, to: { t: T0 + 30 * HOUR, x: 300, y: 90 } },
    ];
    expect(placeGapLabels(bad, FRAME)).toEqual([]);
  });
});
