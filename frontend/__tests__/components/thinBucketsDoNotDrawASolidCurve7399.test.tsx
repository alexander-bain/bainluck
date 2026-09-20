// #7399 — THE THIN CONVENTION HAS TO REACH THE MARK THE EYE FOLLOWS.
//
// ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
//
// `https://bainluck.com/calibration` at 1280px and 390px, 2026-09-20, By Source →
// "Break out the shapes (3)" inside the Odds API panel. Three panels, one component:
//
//   Totals (Odds API)      2.5pp ECE · 15,537 outcomes   curve crashes vertically to 0%
//   Spreads (Odds API)     0.4pp ECE · 15,120 outcomes   curve zigzags 68% → 40% → 46%
//   Moneylines (Odds API)  1.5pp ECE · 18,440 outcomes   clean diagonal
//
// Reproducing the page's own `aggregateBuckets` off the served payload, default traded
// cohort, the Totals crash is the 70-80% bin and the 70-80% bin is SEVEN outcomes. The
// two bins carrying 97% of that panel's outcomes (5,759 and 9,414) sit within 3pp of
// the diagonal. Spreads' zigzag is bins of 11 and 18. A reader comparing the three
// panels concludes two of our three sportsbook shapes are badly miscalibrated. The
// published ECEs say otherwise and the ECEs are right.
//
// ── WHY THE DRAWING SAID IT ─────────────────────────────────────────────────
//
// `thinFloor` reached the DOT only. Below it the marker fades to opacity 0.28, takes a
// dashed ring and prints its n — and every one of these charts prints a key saying so.
// The connecting line was one `<polyline stroke-width="2.5">` over every point, thin or
// not, at full opacity. So the boldest mark on the chart was drawn identically through
// a 7-outcome bucket and a 9,414-outcome one, directly under a legend claiming thin
// samples are marked. The two halves of one drawing disagreed.
//
// ── WHAT THIS FILE PINS, AND WHAT IT DELIBERATELY DOES NOT ──────────────────
//
// It pins the split (`curveRuns`, pure) and the rendered consequence (the real Totals
// series through the real component). It does NOT pin a bucket count, an error value or
// a floor: L2-127 (Alex's Option 4) rules every populated bucket is shown, so the
// no-hiding arm below is the load-bearing one — a future "fix" that drops the thin bins
// would make the curve look lovely and is exactly what this file must refuse.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, {
  curveRuns,
  thinBucketKey,
  KEY_CHAR_ADVANCE_PX,
  KEY_BUDGET_W,
} from "../../components/CalibrationChart";

const FLOOR = 1000;

/** The Totals (Odds API) panel exactly as production drew it on 2026-09-20. */
const TOTALS = [
  { midpoint: 5, actual: 23.1, n: 26, bucket: "0-10%", error: 14.7 },
  { midpoint: 15, actual: 33.3, n: 48, bucket: "10-20%", error: 17.8 },
  { midpoint: 25, actual: 20.6, n: 34, bucket: "20-30%", error: -4.4 },
  { midpoint: 35, actual: 25.9, n: 135, bucket: "30-40%", error: -11.8 },
  { midpoint: 45, actual: 44.9, n: 5759, bucket: "40-50%", error: -2.7 },
  { midpoint: 55, actual: 49.4, n: 9414, bucket: "50-60%", error: -1.9 },
  { midpoint: 65, actual: 50.0, n: 114, bucket: "60-70%", error: -12.8 },
  { midpoint: 75, actual: 0.0, n: 7, bucket: "70-80%", error: -72.3 },
];

function render(data: typeof TOTALS): string {
  return renderToStaticMarkup(
    React.createElement(CalibrationChart, {
      series: [{ data, color: "#0f766e", label: "Totals (Odds API)" }],
      width: 300,
      height: 230,
      thinFloor: FLOOR,
      showLegend: false,
    }),
  );
}

/** Every `<polyline>` tag in the markup, as a tag string. A scan, not a replace
 *  chain — see the rig note on hand-rolled HTML readers in jest tests. */
function polylines(markup: string): string[] {
  return Array.from(markup.matchAll(/<polyline\b[^>]*>/g), m => m[0]);
}

function isDashed(tag: string): boolean {
  return /stroke-dasharray="[^"]+"/.test(tag);
}

function isFaded(tag: string): boolean {
  const m = tag.match(/opacity="([^"]+)"/);
  return m != null && parseFloat(m[1]) < 1;
}

/** The x coordinates of a polyline's points, in order. */
function xs(tag: string): number[] {
  const m = tag.match(/points="([^"]*)"/);
  if (!m) return [];
  return m[1]
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map(p => parseFloat(p.split(",")[0]));
}

describe("#7399 — curveRuns splits the curve where the sample gives out", () => {
  test("a segment is thin when EITHER endpoint is thin", () => {
    // The rule that matters. A stretch is only as trustworthy as the weaker bucket
    // it lands on, so a well-sampled point joined to a 7-outcome one is not a
    // well-sampled segment. Keyed on the LEFT endpoint alone, the Totals crash — a
    // 114-outcome bucket falling into a 7-outcome one — would still draw solid on
    // its way down, which is the half of the picture that reads as the defect.
    expect(curveRuns([5000, 10], FLOOR)).toEqual([{ from: 0, to: 1, thin: true }]);
    expect(curveRuns([10, 5000], FLOOR)).toEqual([{ from: 0, to: 1, thin: true }]);
    expect(curveRuns([5000, 6000], FLOOR)).toEqual([{ from: 0, to: 1, thin: false }]);
  });

  test("adjacent segments of the same weight merge into one stroke", () => {
    // Not cosmetic: eight separate abutting polylines would show eight butt-joins
    // on a curve that used to have one continuous `stroke-linejoin`.
    expect(curveRuns([5000, 6000, 7000, 8000], FLOOR)).toEqual([
      { from: 0, to: 3, thin: false },
    ]);
  });

  test("the real Totals series splits exactly where the sample does", () => {
    // 26·48·34·135 thin, then 5,759 and 9,414, then 114 and 7 thin again. The
    // one solid stretch is the pair of bins holding 97% of the panel.
    expect(curveRuns(TOTALS.map(d => d.n), FLOOR)).toEqual([
      { from: 0, to: 4, thin: true },
      { from: 4, to: 5, thin: false },
      { from: 5, to: 7, thin: true },
    ]);
  });

  test("a curve with nothing thin is one solid run, and a curve with nothing else is one thin run", () => {
    // The two ends of the range. Without these the split could be keyed on
    // anything that happens to agree with the Totals shape.
    expect(curveRuns([2000, 3000, 4000], FLOOR)).toEqual([{ from: 0, to: 2, thin: false }]);
    expect(curveRuns([2, 3, 4], FLOOR)).toEqual([{ from: 0, to: 2, thin: true }]);
  });

  test("a curve too short to have a segment produces no runs", () => {
    expect(curveRuns([], FLOOR)).toEqual([]);
    expect(curveRuns([5000], FLOOR)).toEqual([]);
  });

  test("the floor is the floor and nothing else — a bucket AT it is not thin", () => {
    expect(curveRuns([FLOOR, FLOOR], FLOOR)).toEqual([{ from: 0, to: 1, thin: false }]);
    expect(curveRuns([FLOOR - 1, FLOOR], FLOOR)).toEqual([{ from: 0, to: 1, thin: true }]);
  });
});

describe("#7399 — the rendered Totals panel draws its crash as the guess it is", () => {
  const markup = render(TOTALS);
  const lines = polylines(markup);

  test("the stretch into the 7-outcome bucket is faded AND dashed", () => {
    // The mark the reader follows off the bottom of the chart. Runs are emitted
    // left to right, so the crash is the last one, and it must be the run that
    // ends on the rightmost point the series has.
    const crash = lines[lines.length - 1];
    const allX = lines.flatMap(xs);
    expect(xs(crash)[xs(crash).length - 1]).toBe(Math.max(...allX));
    expect(isDashed(crash)).toBe(true);
    expect(isFaded(crash)).toBe(true);
  });

  test("the stretch between the two well-sampled bins is solid and full strength", () => {
    // The other half of the claim, and the one that stops the fix from being
    // "fade the whole curve", which would be just as untrue in the other
    // direction — 15,173 of the panel's 15,537 outcomes are in those two bins.
    const solid = lines.filter(t => !isDashed(t) && !isFaded(t));
    expect(solid).toHaveLength(1);
    expect(xs(solid[0])).toHaveLength(2);
  });

  test("every bucket is still drawn — nothing is hidden (L2-127)", () => {
    // THE ARM THAT MATTERS MOST. Alex's Option 4 is that every populated bucket is
    // shown; the remedy here is drawing weight, never suppression. A fix that
    // filtered the thin bins would pass every assertion above.
    const covered = new Set<number>();
    for (const tag of lines) for (const x of xs(tag)) covered.add(Math.round(x * 1000));
    expect(covered.size).toBe(TOTALS.length);
    // and the marker for the 7-outcome bucket is still in the markup, with its n
    expect(markup).toContain("n=7");
  });

  test("CONTROL: a curve with no thin bucket is one solid polyline, as it always was", () => {
    // The no-change arm. If this ever goes dashed, the split has stopped reading
    // `thinFloor` and every assertion above is passing for the wrong reason.
    const fat = TOTALS.map(d => ({ ...d, n: 5000 }));
    const fatLines = polylines(render(fat));
    expect(fatLines).toHaveLength(1);
    expect(isDashed(fatLines[0])).toBe(false);
    expect(isFaded(fatLines[0])).toBe(false);
    expect(xs(fatLines[0])).toHaveLength(TOTALS.length);
  });
});

describe("#7399 — the key names the mark it now applies to", () => {
  test("it names the dot, the line and the floor", () => {
    const key = thinBucketKey(FLOOR);
    expect(key).toContain("faded");
    expect(key).toContain("dashed");
    expect(key).toContain("n<1000");
  });

  test("it is rendered on the chart", () => {
    expect(render(TOTALS)).toContain("faded + dashed = thin (n&lt;1000)");
  });

  test("it still fits the narrowest panel it is right-anchored in", () => {
    // #7399 lengthened this string, and it grows LEFTWARD from `width - padR`
    // into the rotated axis title. An over-long key collides on a 300-unit shape
    // panel and nowhere else, which is a chart nobody would think to re-measure.
    // Caught here rather than in a screenshot.
    const widthPx = thinBucketKey(FLOOR).length * KEY_CHAR_ADVANCE_PX;
    expect(widthPx).toBeLessThan(KEY_BUDGET_W);
  });
});
