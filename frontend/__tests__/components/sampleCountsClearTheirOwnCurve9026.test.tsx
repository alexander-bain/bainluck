/**
 * #9026 — a provider tab's curve must not strike through its own sample counts.
 *
 * Production, 2026-09-27 ~03:00Z, /calibration at 390px, traded cohort, By Source provider tabs:
 * the line ran through `21,424`, `13,106`, `11,872` and `6,613` on Sportsbooks (Odds API), and
 * through `7,096` and `15,310` on Polymarket. `dodgeNLabels` kept a label clear of other labels
 * and (since #9016) inside the plot, but never tested it against the line it annotates. On a
 * steep stretch the segment coming in runs through "below" and the one going out runs through
 * "above".
 *
 * Fixtures are the served payload's rows summed by bucket, as the page aggregates a provider
 * (`/api/calibration`, generated 2026-09-26T22:17Z). Sportsbooks = every `odds_api*` key
 * (161,196, the tab's legend). Polymarket and DataGolf = their `price_moved=true` rows, the same
 * rows `firstSampleCountClearsTheAxis9016` uses. Every box is rebuilt from the emitted SVG (the
 * #8979 model: 5.6 units per 9px character, full type size as ascent, a quarter as descent), and
 * the curve is read back from the drawn `<polyline>`s, so a label drawn anywhere other than where
 * the rule chose still reads as a hit.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, { dodgeNLabels, nLabelOptions } from "../../components/CalibrationChart";
import { aggregateBuckets, ParityBucket } from "../../lib/calibrationParity";

const FLOOR = 1000;
const ADVANCE = 5.6;
/** Half the curve's 2.5 stroke: a segment this close to the glyphs strokes them. */
const HALF_STROKE = 1.25;

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

function labels(markup: string): Array<{ text: string; rect: Rect }> {
  return Array.from(
    markup.matchAll(/(<text\b[^>]*data-n-label-below="(?:true|false)"[^>]*>)([^<]*)<\/text>/g),
    m => {
      const tag = m[1];
      expect(attr(tag, "text-anchor")).toBe("middle");
      const x = num(tag, "x");
      const y = num(tag, "y");
      const fs = num(tag, "font-size");
      const w = m[2].length * ADVANCE;
      return { text: m[2], rect: { left: x - w / 2, right: x + w / 2, top: y - fs, bottom: y + fs * 0.25 } };
    },
  );
}

type Seg = [number, number, number, number];

/** Every drawn segment of the curve, thin runs included (they are faded, not absent). */
function segments(markup: string): Seg[] {
  const segs: Seg[] = [];
  for (const m of markup.matchAll(/<polyline\b[^>]*>/g)) {
    const pts = (attr(m[0], "points") ?? "")
      .trim()
      .split(/\s+/)
      .map(p => p.split(",").map(Number));
    for (let i = 0; i + 1 < pts.length; i++) segs.push([pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]]);
  }
  return segs;
}

/** The data markers (the legend dot and click targets carry no `opacity`). */
function markers(markup: string): Array<{ x: number; y: number; r: number }> {
  return Array.from(markup.matchAll(/<circle\b[^>]*>/g), m => m[0])
    .filter(t => attr(t, "opacity") != null)
    .map(t => ({ x: num(t, "cx"), y: num(t, "cy"), r: num(t, "r") }));
}

/** Independent of the component: sample the segment densely against the grown box. */
function segmentHits(s: Seg, r: Rect): boolean {
  const g = { left: r.left - HALF_STROKE, right: r.right + HALF_STROKE, top: r.top - HALF_STROKE, bottom: r.bottom + HALF_STROKE };
  for (let i = 0; i <= 400; i++) {
    const t = i / 400;
    const x = s[0] + (s[2] - s[0]) * t;
    const y = s[1] + (s[3] - s[1]) * t;
    if (x > g.left && x < g.right && y > g.top && y < g.bottom) return true;
  }
  return false;
}

function markerHits(c: { x: number; y: number; r: number }, r: Rect): boolean {
  const nx = Math.min(Math.max(c.x, r.left), r.right);
  const ny = Math.min(Math.max(c.y, r.top), r.bottom);
  return (c.x - nx) ** 2 + (c.y - ny) ** 2 < c.r ** 2;
}

function plotBox(markup: string, width: number): Rect {
  const diag = Array.from(markup.matchAll(/<line\b[^>]*>/g), m => m[0]).filter(
    t => attr(t, "stroke-dasharray") === "6,4",
  );
  expect(diag).toHaveLength(1);
  return { left: num(diag[0], "x1"), right: num(diag[0], "x2"), top: num(diag[0], "y2"), bottom: num(diag[0], "y1") };
}

function render(rows: ParityBucket[], width: number, height: number): string {
  return renderToStaticMarkup(
    React.createElement(CalibrationChart, {
      series: [{ data: aggregateBuckets(rows), color: "#15803d", label: "Provider" }],
      width,
      height,
      thinFloor: FLOOR,
      showAllN: true,
    }),
  );
}

const SPORTSBOOKS: ParityBucket[] = [
  { bucket_idx: 0, n: 1790, winners: 188, sum_prob: 122.1689, sum_sq_err: 173.9846 },
  { bucket_idx: 1, n: 3942, winners: 571, sum_prob: 602.638, sum_sq_err: 484.1675 },
  { bucket_idx: 2, n: 6613, winners: 1387, sum_prob: 1679.7285, sum_sq_err: 1106.4698 },
  { bucket_idx: 3, n: 11872, winners: 4322, sum_prob: 4240.2436, sum_sq_err: 2732.8338 },
  { bucket_idx: 4, n: 35952, winners: 16691, sum_prob: 16550.5252, sum_sq_err: 8943.4287 },
  { bucket_idx: 5, n: 53999, winners: 28586, sum_prob: 29020.7476, sum_sq_err: 13409.2929 },
  { bucket_idx: 6, n: 21424, winners: 13620, sum_prob: 13786.6733, sum_sq_err: 4935.3574 },
  { bucket_idx: 7, n: 13106, winners: 9980, sum_prob: 9757.2021, sum_sq_err: 2385.109 },
  { bucket_idx: 8, n: 8526, winners: 7312, sum_prob: 7241.7743, sum_sq_err: 1033.9626 },
  { bucket_idx: 9, n: 3972, winners: 3705, sum_prob: 3705.0833, sum_sq_err: 252.2879 },
];

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
  ["Sportsbooks (Odds API)", SPORTSBOOKS],
  ["Polymarket", POLYMARKET_TRADED],
  ["DataGolf", DATAGOLF_TRADED],
] as const)("#9026 — %s tab", (_name, rows) => {
  test.each(SHAPES)("at %ix%i the curve strokes through no count", (w, h) => {
    const markup = render(rows, w, h);
    const segs = segments(markup);
    expect(segs).toHaveLength(9);
    const hits: string[] = [];
    for (const l of labels(markup)) if (segs.some(s => segmentHits(s, l.rect))) hits.push(l.text);
    expect(hits).toEqual([]);
  });

  test.each(SHAPES)("at %ix%i no count sits on a marker", (w, h) => {
    const markup = render(rows, w, h);
    const ms = markers(markup);
    expect(ms).toHaveLength(10);
    const hits: string[] = [];
    for (const l of labels(markup)) if (ms.some(c => markerHits(c, l.rect))) hits.push(l.text);
    expect(hits).toEqual([]);
  });

  test.each(SHAPES)("at %ix%i every count sits nearer its own point than any other", (w, h) => {
    const markup = render(rows, w, h);
    const ms = markers(markup);
    const gap = (c: { x: number; y: number; r: number }, r: Rect) =>
      Math.hypot(c.x - Math.min(Math.max(c.x, r.left), r.right), c.y - Math.min(Math.max(c.y, r.top), r.bottom)) - c.r;
    const wrong: string[] = [];
    labels(markup).forEach((l, i) => {
      const mine = gap(ms[i], l.rect);
      if (ms.some((c, j) => j !== i && gap(c, l.rect) <= mine)) wrong.push(l.text);
    });
    expect(wrong).toEqual([]);
  });

  test.each(SHAPES)("at %ix%i all ten counts print, inside the plot, none overlapping", (w, h) => {
    const markup = render(rows, w, h);
    const box = plotBox(markup, w);
    const ls = labels(markup);
    expect(ls.map(l => l.text)).toEqual(rows.map(r => r.n.toLocaleString()));
    for (const l of ls) {
      expect(l.rect.top).toBeGreaterThanOrEqual(box.top);
      expect(l.rect.bottom).toBeLessThanOrEqual(box.bottom);
      expect(l.rect.left).toBeGreaterThanOrEqual(box.left - 20); // a centred count at 5%/95% may overhang the plot side, as before
      expect(l.rect.right).toBeLessThanOrEqual(box.right + 20);
    }
    for (let i = 0; i < ls.length; i++)
      for (let j = i + 1; j < ls.length; j++) expect(meets(ls[i].rect, ls[j].rect)).toBe(false);
  });
});

describe("#9026 — dodgeNLabels without the series is unchanged", () => {
  const plotTop = 25;
  const plotBottom = 180;

  test("side spots are offered only when the label's width is given", () => {
    expect(nLabelOptions(100, 8, plotTop, true)).toHaveLength(3);
    const withSides = nLabelOptions(100, 8, plotTop, true, 6);
    expect(withSides).toHaveLength(7);
    const old = nLabelOptions(100, 8, plotTop, true);
    // today's three keep their order; lower-right, upper-left, right, left sit before one row out
    expect(withSides.filter(p => p.dx == null)).toEqual(old);
    expect(withSides[6]).toEqual(old[2]);
    expect(withSides.slice(2, 6).map(p => Math.sign(p.dx!))).toEqual([1, -1, 1, -1]);
    expect(withSides.slice(2, 6).map(p => p.below)).toEqual([true, false, false, false]);
  });

  test("without obstacles a side spot is never taken, even when every vertical spot is boxed in", () => {
    const cands = [
      { x: 100, chars: 6, options: nLabelOptions(100, 8, plotTop, true, 6) },
      { x: 100, chars: 6, options: nLabelOptions(100, 8, plotTop, true, 6) },
      { x: 100, chars: 6, options: nLabelOptions(100, 8, plotTop, true, 6) },
      { x: 100, chars: 6, options: nLabelOptions(100, 8, plotTop, true, 6) },
    ];
    for (const p of dodgeNLabels(cands, plotTop, plotBottom)) expect(p.dx).toBeUndefined();
  });

  test("a line through today's spot moves the label; the same label with no line stays", () => {
    const opts = nLabelOptions(100, 6, plotTop, true, 6);
    // A segment straight through the below spot (baseline 117, box 108..119) at x=100.
    const line = {
      points: [
        { x: 80, y: 114, r: 0 },
        { x: 120, y: 114, r: 0 },
      ],
      plotLeft: 0,
      plotRight: 400,
    };
    const [moved] = dodgeNLabels([{ x: 100, chars: 6, options: opts }], plotTop, plotBottom, line);
    expect(moved).toEqual(opts[1]);
    const [kept] = dodgeNLabels([{ x: 100, chars: 6, options: opts }], plotTop, plotBottom);
    expect(kept).toEqual(opts[0]);
  });

  test("a spot nearer another point than its own is refused, even when nothing crosses it", () => {
    // Before beside-spots came ahead of one row out, a row-out count on a steep curve landed
    // beside the NEXT point down (Kalshi 13,343 beside the 66% dot, Polymarket 7,096 beside 52%).
    const far = { y: 160, below: true };
    const near = { y: 93, below: false };
    const series = {
      points: [
        { x: 100, y: 100, r: 4 },
        { x: 140, y: 170, r: 4 },
      ],
      plotLeft: 0,
      plotRight: 400,
    };
    const [got] = dodgeNLabels([{ x: 100, chars: 6, options: [far, near] }], plotTop, 200, series);
    expect(got).toEqual(near);
  });

  test("when no spot clears the line, the #9016 rule decides exactly as before", () => {
    const opts = nLabelOptions(100, 6, plotTop, true, 6);
    // A vertical line through the point crosses below, above and the second row; the plot is too
    // narrow for either side. Nothing is clean, so today's choice (below) stands.
    const line = {
      points: [
        { x: 100, y: 0, r: 0 },
        { x: 100, y: 200, r: 0 },
      ],
      plotLeft: 95,
      plotRight: 105,
    };
    const [got] = dodgeNLabels([{ x: 100, chars: 6, options: opts }], plotTop, plotBottom, line);
    expect(got).toEqual(opts[0]);
  });
});
