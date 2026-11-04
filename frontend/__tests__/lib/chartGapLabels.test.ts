/**
 * #11929 C — `placeGapLabels`: which holes a full chart names, in what words,
 * and where. The component wiring is pinned in
 * `__tests__/components/aLongGapCarriesTheEventChartsLabel11929c.test.tsx`.
 */

import {
  MIN_LABELLED_HOLE_SHARE,
  gapLabelWidth,
  placeGapLabels,
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
    const [label, ...rest] = placeGapLabels([hole(60, 97, 90)], FRAME);
    expect(rest).toEqual([]);
    expect(label.text).toBe("No numbers for 37 hours in this stretch");
    expect(label.x).toBeCloseTo((xAt(60) + xAt(97)) / 2, 9);
    expect(label.y).toBeLessThan(90);
    expect(label.ms).toBe(37 * HOUR);
  });

  test("a hole at the plot's edge keeps its label inside the plot, still overlapping it", () => {
    const [label] = placeGapLabels([hole(150, 168)], FRAME);
    const w = gapLabelWidth(label.text);
    expect(label.x + w / 2).toBeLessThanOrEqual(FRAME.right);
    expect(label.x - w / 2).toBeLessThan(label.toX);
  });

  test("a line at the ceiling puts its label inside the plot, never above it", () => {
    const [label] = placeGapLabels([hole(60, 97, 20)], FRAME);
    expect(label.y).toBeGreaterThan(FRAME.top);
    expect(label.y).toBeLessThan(FRAME.bottom);
  });

  test("lines sharing one stretch share one label, sized by the longest", () => {
    const labels = placeGapLabels(
      [hole(60, 97, 60), hole(60, 97, 120), hole(60, 97.5, 140)],
      FRAME,
    );
    expect(labels).toHaveLength(1);
    expect(labels[0].ms).toBe(37.5 * HOUR);
    // Above the topmost of the lines it explains.
    expect(labels[0].y).toBeLessThan(60);
  });

  test("holes that only partly overlap are different stretches", () => {
    const labels = placeGapLabels([hole(10, 40, 50), hole(25, 70, 140)], FRAME);
    expect(labels).toHaveLength(2);
  });

  test("labels never overlap, and the longest hole always gets one", () => {
    const holes = [hole(10, 25), hole(30, 48), hole(52, 70), hole(75, 120), hole(124, 140)];
    const labels = placeGapLabels(holes, FRAME);
    expect(labels.map((l) => l.ms)).toContain(45 * HOUR);
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
    const plotW = FRAME.right - FRAME.left;
    const hairlineH = ((plotW * 0.009) / 730) * 168;
    expect(placeGapLabels([hole(80, 80 + hairlineH)], FRAME)).toEqual([]);
    const visibleH = ((plotW * 0.011) / 730) * 168;
    expect(placeGapLabels([hole(80, 80 + visibleH)], FRAME)).toHaveLength(1);
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
