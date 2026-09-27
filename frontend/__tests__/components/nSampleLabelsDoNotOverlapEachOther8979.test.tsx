/**
 * #8979 — the `n=` labels on a calibration panel must not print on top of each other.
 *
 * Production, 2026-09-26, /calibration at 390px, By Source → DataGolf (traded cohort). The
 * 20-50% buckets hold 764, 645 and 710 outcomes, all under the 1,000 floor, all within 3pp
 * actual of each other, so each printed its label above its point and the three read as one
 * smear: `n=764n=645n=710`. #7434 kept each label clear of the key, but only one at a time.
 *
 * The fixture below is the served payload's DataGolf `price_moved=true` rows summed by bucket,
 * exactly as the page aggregates them (`/api/calibration`, fetched 2026-09-26 23:55Z).
 *
 * The box model is the one #7434's suite uses: 5.6 units per character (rounded UP from
 * production rects), full type size as ascent, a quarter of it as descent. It is built here
 * from the emitted `<text>` attributes, not by calling the component's box function, so a
 * label drawn somewhere other than where the placement rule chose still reads as a collision.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, {
  dodgeNLabels,
  nLabelOptions,
  nLabelPlacement,
} from "../../components/CalibrationChart";
import { aggregateBuckets, ParityBucket } from "../../lib/calibrationParity";

const FLOOR = 1000;
const ADVANCE = 5.6;

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

/** Every per-bucket sample label the chart drew: `n=123` (thin) or `1,234` (showAllN). */
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

function collisions(ls: Label[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < ls.length; i++)
    for (let j = i + 1; j < ls.length; j++)
      if (meets(ls[i].rect, ls[j].rect)) out.push(`${ls[i].text} × ${ls[j].text}`);
  return out;
}

/** The plot box, read off the drawing: the diagonal runs (px(0), py(0)) → (px(100), py(100)). */
function plotBox(markup: string): { top: number; bottom: number } {
  const diag = Array.from(markup.matchAll(/<line\b[^>]*>/g), m => m[0]).filter(
    t => attr(t, "stroke-dasharray") === "6,4",
  );
  expect(diag).toHaveLength(1);
  return { top: num(diag[0], "y2"), bottom: num(diag[0], "y1") };
}

function render(
  rows: ParityBucket[],
  width: number,
  height: number,
  extra: Record<string, unknown> = {},
): string {
  return renderToStaticMarkup(
    React.createElement(CalibrationChart, {
      series: [{ data: aggregateBuckets(rows), color: "#f59e0b", label: "DataGolf" }],
      width,
      height,
      thinFloor: FLOOR,
      showLegend: false,
      ...extra,
    }),
  );
}

// Production, served 2026-09-26: DataGolf, traded (`price_moved=true`), summed per bucket.
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

/** Provider panels are authored 330x260, the shape panels 300x230 (call-site facts, page.tsx). */
const SHAPES: Array<[number, number]> = [
  [330, 260],
  [300, 230],
];

describe("#8979 — the DataGolf panel's sample labels are each readable", () => {
  test.each(SHAPES)("at %ix%i no two n= labels overlap", (w, h) => {
    const ls = labels(render(DATAGOLF_TRADED, w, h));
    // Every thin bucket still prints its n — nothing is dropped to make room.
    expect(ls.map(l => l.text)).toEqual([
      "n=764", "n=645", "n=710", "n=759", "n=456", "n=203", "n=40", "n=5",
    ]);
    expect(collisions(ls)).toEqual([]);
  });

  test.each(SHAPES)("at %ix%i every label moved off its first spot stays inside the plot", (w, h) => {
    const markup = render(DATAGOLF_TRADED, w, h);
    const { top, bottom } = plotBox(markup);
    // #7434: the key lives above the plot top, so a label inside the plot clears it.
    for (const l of labels(markup)) {
      expect(l.rect.top).toBeGreaterThanOrEqual(top);
      expect(l.rect.bottom).toBeLessThanOrEqual(bottom + 3);
    }
  });

  test("the flat stretch is resolved by moving the middle label, not by thinning", () => {
    const ls = labels(render(DATAGOLF_TRADED, 300, 230));
    const byText = Object.fromEntries(ls.map(l => [l.text, l]));
    expect(byText["n=764"].below).toBe(false);
    expect(byText["n=645"].below).toBe(true);
    expect(byText["n=710"].below).toBe(false);
  });
});

describe("#8979 — dodgeNLabels", () => {
  const plotTop = 25;
  const plotBottom = 180;

  test("labels that do not meet keep exactly the spot they had before", () => {
    const opts = [nLabelOptions(120, 5, plotTop, false), nLabelOptions(60, 5, plotTop, false)];
    const got = dodgeNLabels(
      [
        { x: 80, chars: 5, options: opts[0] },
        { x: 200, chars: 5, options: opts[1] },
      ],
      plotTop,
      plotBottom,
    );
    expect(got).toEqual([nLabelPlacement(120, 5, plotTop), nLabelPlacement(60, 5, plotTop)]);
  });

  test("a second label that would overlap the first moves to the other side of its point", () => {
    const got = dodgeNLabels(
      [
        { x: 100, chars: 5, options: nLabelOptions(120, 5, plotTop, false) },
        { x: 122, chars: 5, options: nLabelOptions(118, 5, plotTop, false) },
      ],
      plotTop,
      plotBottom,
    );
    expect(got[0]).toEqual({ y: 112, below: false });
    expect(got[1].below).toBe(true);
  });

  test("an alternative outside the plot is never taken — today's spot is kept instead", () => {
    // The second point sits on the floor, so below is off the plot; with a third
    // label boxing it in from above, no free option remains inside.
    const got = dodgeNLabels(
      [
        { x: 100, chars: 5, options: nLabelOptions(178, 5, plotTop, false) },
        { x: 110, chars: 5, options: nLabelOptions(178, 5, plotTop, false) },
      ],
      plotTop,
      plotBottom,
    );
    // below (y 194) leaves the plot, so it goes one row further up instead
    expect(got[1]).toEqual({ y: 156, below: false });
  });

  test("with no free option the label keeps today's position rather than disappearing", () => {
    const tight = 60;
    const got = dodgeNLabels(
      [
        { x: 100, chars: 5, options: nLabelOptions(40, 4, 25, false) },
        { x: 104, chars: 5, options: nLabelOptions(40, 4, 25, false) },
      ],
      25,
      tight,
    );
    expect(got).toHaveLength(2);
    expect(got[1]).toEqual(nLabelPlacement(40, 4, 25));
  });
});

describe("#8979 — the always-below counts (single-category view) get the same rule", () => {
  // A flat thin category: every bucket lands near 50% actual, labels would sit side by side.
  const FLAT: ParityBucket[] = Array.from({ length: 10 }, (_, i) => ({
    bucket_idx: i,
    n: 12000 + i * 111,
    winners: Math.round((12000 + i * 111) * 0.5),
    sum_prob: (12000 + i * 111) * (i * 0.1 + 0.05),
    sum_sq_err: 3000,
  }));

  test("wide counts on a flat curve are all printed and none overlap", () => {
    const markup = render(FLAT, 300, 300, { showAllN: true });
    const ls = labels(markup);
    expect(ls).toHaveLength(10);
    expect(collisions(ls)).toEqual([]);
  });
});
