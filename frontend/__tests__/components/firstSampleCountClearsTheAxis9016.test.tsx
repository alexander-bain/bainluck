/**
 * #9016 — a provider tab's chart must not print its first sample count on top of the axis "0%".
 *
 * Production, 2026-09-27 ~02:45Z, /calibration at 390px, By Source → Polymarket (traded cohort):
 * the 0-10% point's count `23,602` was drawn over the x-axis number `0%`; DataGolf's `6,257`
 * likewise. A single-series chart (`showAllN`) prints every count BELOW its point, and the
 * 0-10% bucket is the busiest — the biggest marker, ~4% up from the floor — so "below" fell
 * into the axis-number band. #8979's `dodgeNLabels` exempted a label's first option from the
 * inside-the-plot test, so nothing moved it.
 *
 * Fixtures are the served payload's `price_moved=true` rows summed by bucket, exactly as the
 * page aggregates them (`/api/calibration`, generated 2026-09-26T22:17Z). Boxes are built from
 * the emitted `<text>` attributes (the #8979 suite's model: 5.6 units per 9px character, full
 * type size as ascent, a quarter as descent), so a label drawn somewhere other than where the
 * rule chose still reads as a collision.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, { dodgeNLabels, nLabelOptions } from "../../components/CalibrationChart";
import { aggregateBuckets, ParityBucket } from "../../lib/calibrationParity";

const FLOOR = 1000;
const ADVANCE = 5.6;
/** Axis numbers are 11px; ~6.2 units per character over-states `0%`'s ink, deliberately. */
const AXIS_ADVANCE = 6.2;

interface Rect {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const meets = (a: Rect, b: Rect) =>
  a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`\\b${name}="([^"]*)"`));
  return m ? m[1] : null;
}

function num(tag: string, name: string): number {
  const v = attr(tag, name);
  if (v == null) throw new Error(`tag has no ${name}: ${tag}`);
  return parseFloat(v);
}

interface Label {
  text: string;
  rect: Rect;
  below: boolean;
}

function labels(markup: string): Label[] {
  return Array.from(
    markup.matchAll(/(<text\b[^>]*data-n-label-below="(?:true|false)"[^>]*>)([^<]*)<\/text>/g),
    m => {
      const tag = m[1];
      const x = num(tag, "x");
      const y = num(tag, "y");
      const fs = num(tag, "font-size");
      const w = m[2].length * ADVANCE;
      return {
        text: m[2],
        rect: { left: x - w / 2, right: x + w / 2, top: y - fs, bottom: y + fs * 0.25 },
        below: attr(tag, "data-n-label-below") === "true",
      };
    },
  );
}

/** The x-axis numbers: centred `N%` texts below the plot. */
function xAxisNumbers(markup: string, plotBottom: number): Array<{ text: string; rect: Rect }> {
  return Array.from(
    markup.matchAll(/(<text\b[^>]*text-anchor="middle"[^>]*>)(\d+%)<\/text>/g),
    m => {
      const tag = m[1];
      const x = num(tag, "x");
      const y = num(tag, "y");
      const fs = num(tag, "font-size");
      const w = m[2].length * AXIS_ADVANCE;
      return { text: m[2], rect: { left: x - w / 2, right: x + w / 2, top: y - fs, bottom: y + fs * 0.25 } };
    },
  ).filter(t => t.rect.top > plotBottom);
}

function plotBox(markup: string): { top: number; bottom: number } {
  const diag = Array.from(markup.matchAll(/<line\b[^>]*>/g), m => m[0]).filter(
    t => attr(t, "stroke-dasharray") === "6,4",
  );
  expect(diag).toHaveLength(1);
  return { top: num(diag[0], "y2"), bottom: num(diag[0], "y1") };
}

function render(rows: ParityBucket[], width: number, height: number): string {
  return renderToStaticMarkup(
    React.createElement(CalibrationChart, {
      series: [{ data: aggregateBuckets(rows), color: "#3b82f6", label: "Provider" }],
      width,
      height,
      thinFloor: FLOOR,
      showAllN: true,
    }),
  );
}

const POLYMARKET_TRADED: ParityBucket[] = [
  { bucket_idx: 0, n: 23602, winners: 926, sum_prob: 1012.8769, sum_sq_err: 876.8901 },
  { bucket_idx: 1, n: 9856, winners: 1368, sum_prob: 1431.444, sum_sq_err: 1171.721 },
  { bucket_idx: 2, n: 10296, winners: 2304, sum_prob: 2568.0854, sum_sq_err: 1786.6142 },
  { bucket_idx: 3, n: 13592, winners: 4341, sum_prob: 4736.4752, sum_sq_err: 2948.4308 },
  { bucket_idx: 4, n: 17178, winners: 6587, sum_prob: 7804.0473, sum_sq_err: 4172.4365 },
  { bucket_idx: 5, n: 15310, winners: 8035, sum_prob: 8194.6433, sum_sq_err: 3787.0911 },
  { bucket_idx: 6, n: 7096, winners: 4705, sum_prob: 4571.3061, sum_sq_err: 1582.9074 },
  { bucket_idx: 7, n: 4938, winners: 3790, sum_prob: 3679.7048, sum_sq_err: 880.0025 },
  { bucket_idx: 8, n: 3281, winners: 2793, sum_prob: 2771.8833, sum_sq_err: 412.2442 },
  { bucket_idx: 9, n: 3769, winners: 3550, sum_prob: 3555.233, sum_sq_err: 204.4124 },
];

const DATAGOLF_TRADED: ParityBucket[] = [
  { bucket_idx: 0, n: 6257, winners: 268, sum_prob: 231.5171, sum_sq_err: 250.7105 },
  { bucket_idx: 1, n: 1753, winners: 269, sum_prob: 246.941, sum_sq_err: 225.757 },
  { bucket_idx: 2, n: 764, winners: 192, sum_prob: 187.1508, sum_sq_err: 143.9903 },
  { bucket_idx: 3, n: 645, winners: 176, sum_prob: 226.6686, sum_sq_err: 130.9084 },
  { bucket_idx: 4, n: 710, winners: 201, sum_prob: 320.8248, sum_sq_err: 163.9745 },
  { bucket_idx: 5, n: 759, winners: 304, sum_prob: 415.9615, sum_sq_err: 200.3352 },
  { bucket_idx: 6, n: 456, winners: 222, sum_prob: 294.2209, sum_sq_err: 124.7947 },
  { bucket_idx: 7, n: 203, winners: 138, sum_prob: 149.9943, sum_sq_err: 44.7626 },
  { bucket_idx: 8, n: 40, winners: 34, sum_prob: 33.6308, sum_sq_err: 5.2163 },
  { bucket_idx: 9, n: 5, winners: 5, sum_prob: 4.6416, sum_sq_err: 0.0272 },
];

/** The call site authors 700x340; at 390px the chart re-authors square at its card's width. */
const SHAPES: Array<[number, number]> = [
  [700, 340],
  [318, 318],
];

describe.each([
  ["Polymarket", POLYMARKET_TRADED, "23,602"],
  ["DataGolf", DATAGOLF_TRADED, "6,257"],
] as const)("#9016 — %s tab: every sample count is readable", (_name, rows, first) => {
  test.each(SHAPES)("at %ix%i no count meets an x-axis number", (w, h) => {
    const markup = render(rows, w, h);
    const { bottom } = plotBox(markup);
    const axis = xAxisNumbers(markup, bottom);
    expect(axis.map(a => a.text)[0]).toBe("0%");
    const hits: string[] = [];
    for (const l of labels(markup))
      for (const a of axis) if (meets(l.rect, a.rect)) hits.push(`${l.text} × ${a.text}`);
    expect(hits).toEqual([]);
  });

  test.each(SHAPES)("at %ix%i every count stays inside the plot and none overlap", (w, h) => {
    const markup = render(rows, w, h);
    const { top, bottom } = plotBox(markup);
    const ls = labels(markup);
    // Nothing is dropped to make room: ten buckets, ten counts.
    expect(ls).toHaveLength(10);
    expect(ls[0].text).toBe(first);
    for (const l of ls) {
      expect(l.rect.top).toBeGreaterThanOrEqual(top);
      expect(l.rect.bottom).toBeLessThanOrEqual(bottom);
    }
    for (let i = 0; i < ls.length; i++)
      for (let j = i + 1; j < ls.length; j++) expect(meets(ls[i].rect, ls[j].rect)).toBe(false);
  });
});

describe("#9016 — only the label that left the plot moves", () => {
  test("Polymarket at 390px: the first count goes above its point; only its neighbours follow", () => {
    const ls = labels(render(POLYMARKET_TRADED, 318, 318));
    // Before #9016 all ten drew below. 23,602 moves up out of the axis band; 9,856, 10,296 and
    // 13,592 then meet the label beside them and dodge up too (#8979's rule, unchanged). The
    // upper six never meet a moved label and keep exactly the spot they had.
    expect(ls.map(l => l.below)).toEqual([false, false, false, false, true, true, true, true, true, true]);
  });

  test("dodgeNLabels: a first option already inside the plot is kept, byte for byte", () => {
    const plotTop = 25;
    const plotBottom = 180;
    const opts = nLabelOptions(100, 8, plotTop, true);
    expect(dodgeNLabels([{ x: 100, chars: 6, options: opts }], plotTop, plotBottom)).toEqual([opts[0]]);
  });

  test("dodgeNLabels: a first option below the floor gives way to the next option inside", () => {
    const plotTop = 25;
    const plotBottom = 180;
    const opts = nLabelOptions(172, 10, plotTop, true);
    const [got] = dodgeNLabels([{ x: 100, chars: 6, options: opts }], plotTop, plotBottom);
    expect(got).toEqual(opts[1]);
    expect(got.below).toBe(false);
  });
});
