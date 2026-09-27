"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { plotDims, scaleX, scaleY } from "@/lib/chartScale";

/** #4394: below this fraction of the authored width the browser's own scaling makes the TYPE
 *  illegible (a 700-unit viewBox in a 324px card renders `fontSize="11"` at 5.1 CSS px), so the
 *  chart re-authors itself at the container's width instead of being shrunk into it. Set at 0.85
 *  so the near-square By Source panels — measured at 0.903 and 0.907 on production at 390px — are
 *  left exactly as they are; the two wide-and-short call sites measure 0.463 and are the subjects. */
const REAUTHOR_BELOW = 0.85;

/** Nothing useful is drawable narrower than this; below it the card itself is the bug. */
const MIN_REAUTHORED_W = 260;

/** padL 55 + padR 20 — the component's own horizontal padding, so a caller-free `plotW` can be
 *  derived inside the pure function. Kept beside the pads it mirrors; a test pins the two equal. */
const AXIS_PAD_X = 75;

/** #4400: the pitch, in the READER's pixels, below which two x-axis labels stop reading as two
 *  numbers. Measured on production (`tools/cal-axis-overlap-1073.mjs`, master `2bf1d499`): the
 *  widest label, `100%`, paints 29.4px of ink at 1:1 on every chart on the page, at both 390px and
 *  1280px. 32 is that plus ~2.5px of gap — the smallest separation at which `90%` and `100%` are
 *  still two things. Not a round number by accident: it is one measurement plus one gap. */
const MIN_LABEL_PITCH_PX = 32;

export interface ChartGeometry {
  width: number;
  height: number;
  /** true when the container forced a new geometry rather than a browser-scaled drawing */
  reauthored: boolean;
  /** label every N percent on the x-axis; gridlines are always every 10 */
  xLabelStep: number;
}

/**
 * #4394 — the geometry decision, pure, so it can be tested without a layout engine.
 *
 * `containerW` is null on the server and on the first client paint, and the answer there is the
 * authored box exactly: the fix must never change what the server sends, only what a measured
 * client draws.
 *
 * padL+padR and padT+padB are both 75, which is why a re-authored `height = width` is exactly a
 * SQUARE plot — the right shape for two axes that are both a fixed 0–100%, and close to the shape
 * of the By Source panels that were already legible.
 *
 * #4400 — WHY THE LABEL STEP IS NOT KEYED ON `reauthored`.
 *
 * It used to be, and that read the wrong question. Re-authoring answers "is the TYPE too small";
 * label density answers "is there ROOM for eleven numbers", and a chart can fail the second while
 * passing the first — which is exactly what the seven By Source panels do. Authored at 330x260 and
 * 300x230, they measure 0.903 and 0.907 of their card, comfortably above the 0.85 trigger, so they
 * are never re-authored; but their plot is only 255 and 225 units wide, so eleven labels get 25.5px
 * and 22.5px of pitch for 29.4px of ink. Measured on production at BOTH widths, `90%` and `100%`
 * overlapped by 1.4px and 4.4px — the axis reading as `…80%90%100%`.
 *
 * So the step is decided on the on-screen pitch, `(plotW / 10) * scale`, whichever geometry won.
 * That SUBSUMES the old rule rather than sitting beside it: the shipped re-authored case (a 700-unit
 * chart in the 324px card at 390px) still gets 24.9px of pitch and still thins to every 20%, and the
 * rule now also reaches the panels that were never re-authored. Where the two rules disagree — a
 * re-authored chart wide enough for eleven legible labels, ~660px of viewport — the pitch is right
 * and "re-authored ⇒ 20" was a proxy. Gridlines stay every 10% in every arm; only labels thin.
 */
export function chartGeometry(
  authoredW: number,
  authoredH: number,
  containerW: number | null,
): ChartGeometry {
  const reauthored = containerW != null && containerW < authoredW * REAUTHOR_BELOW;
  const width = reauthored ? Math.max(MIN_REAUTHORED_W, containerW!) : authoredW;
  const height = reauthored ? width : authoredH;

  // The SVG is drawn at `width` px unless `maxWidth: 100%` clamps it to a narrower container, so
  // the scale is that clamp and nothing else. A re-authored chart is 1:1 by construction, and an
  // unmeasured one (server render, first paint) has no scale to know — both fall out as 1.
  const scale = containerW != null && containerW < width ? containerW / width : 1;
  const labelPitch = ((width - AXIS_PAD_X) / 10) * scale;
  const xLabelStep = labelPitch < MIN_LABEL_PITCH_PX ? 20 : 10;

  return { width, height, reauthored, xLabelStep };
}

interface CalPoint {
  midpoint: number;
  actual: number;
  n: number;
  bucket: string;
  error: number;
  ciLower?: number;
  ciUpper?: number;
}

interface Series {
  data: CalPoint[];
  color: string;
  label: string;
}

/** A maximal stretch of the curve drawn at one weight. `from`/`to` index `Series.data`. */
export interface CurveRun {
  from: number;
  to: number;
  thin: boolean;
}

/**
 * #7399 — WHY THE CURVE IS NOT ONE POLYLINE.
 *
 * `thinFloor` used to reach the DOT only: below it the marker fades to 0.28 with a
 * dashed ring and prints its n, while the connecting line stayed one 2.5px
 * full-opacity stroke from end to end. The line is the boldest mark on the chart and
 * the one a reader's eye follows, so the two halves of the same drawing disagreed —
 * under a legend that says thin samples are marked.
 *
 * Measured on the served payload 2026-09-20 (default traded cohort): the Totals (Odds
 * API) panel, published at 2.5pp ECE, drew a vertical crash to 0% at the 70-80% bin,
 * which is SEVEN outcomes; the two bins carrying 97% of its 15,537 outcomes sit within
 * 3pp of the diagonal. Spreads, published at 0.4pp ECE, zigzagged on bins of 11 and 18.
 * Both read as badly miscalibrated shapes beside a Moneylines panel whose every bin
 * clears the floor and whose line is therefore straight.
 *
 * A segment is thin if EITHER endpoint is thin — a stretch is only as trustworthy as
 * the weaker bucket it lands on. Adjacent segments of the same weight are merged so a
 * well-sampled run still draws as one continuous stroke with proper joins.
 *
 * This does NOT hide anything: L2-127 (Alex's Option 4) rules every populated bucket is
 * shown, and every point and every segment is still drawn. Only the weight changes.
 */
/**
 * How much room the thin-bucket key actually has, on the narrowest chart this
 * component is authored at anywhere on /calibration: the 300-unit shape panels inside
 * "Break out the shapes". The key is right-anchored at `width - padR`, so it grows
 * LEFTWARD, and the first thing it reaches is the rotated "Actual Win Rate" title at
 * x=14. The budget is therefore the authored width less the right pad less a gutter
 * for that title — not the plot box, which the key is allowed to overhang.
 */
export const KEY_BUDGET_W = 300 - 20 - 20;

/**
 * Advance per character for the key's `system-ui` at 9.5px. Measured on production
 * 2026-09-20: the 47-character key rendered 219 CSS px on an unscaled 300-unit panel,
 * i.e. 4.66. Rounded up so the guard bites before a reader does.
 */
export const KEY_CHAR_ADVANCE_PX = 4.75;

/**
 * #7399. Both marks, not just the dot. A reader looking at a dashed stretch of curve
 * has to be able to find out here what the dash means — the treatment is the same one
 * `curveRuns` and the marker share, so the key names it once for both. Kept to one
 * short line: this is a source mark, not a method note (standing notice 34).
 */
export function thinBucketKey(thinFloor: number): string {
  return `● size = sample count · faded + dashed = thin (n<${thinFloor})`;
}

/** The `n=` label's type size, in the chart's own user units. */
export const N_LABEL_FONT_PX = 9;

/** Clearance between the marker's edge and the label's nearest edge. */
const N_LABEL_GAP = 3;

/**
 * Baseline offset for a label placed BELOW its point: the gap plus the type's ascent, so
 * the label's top clears the marker. 11 is the value the always-below `showAllN` branch
 * has drawn at since L2-103 — the two placements are the same mark and share it.
 */
export const N_LABEL_BELOW_OFFSET = 11;

export interface NLabelPlacement {
  /** SVG baseline y for the label. */
  y: number;
  /** true when the label was flipped under its point to stay inside the plot. */
  below: boolean;
  /** #9026: horizontal offset of the label's centre from its point; set only on a side spot. */
  dx?: number;
}

/**
 * #7434 — WHY THE `n=` LABEL HAS TO BE ABLE TO DODGE DOWNWARD.
 *
 * The label is drawn above its point, and the thin-bucket key (`thinBucketKey`) is drawn
 * right-anchored in the pad band ABOVE the plot, at `padT - 10`. Those two never meet
 * while points sit in the middle of the plot — but a point pinned at 100% actual sits at
 * `py(100) === padT`, so its label's baseline lands at `padT - r - 3`, which is inside the
 * key's own line. Both become unreadable.
 *
 * Measured on production 2026-09-20, all-markets cohort, 390px: the DataGolf panel drew
 * five `n=` labels and 5 of 5 intersected the key's bounding box, while the sportsbook
 * shape panels drew 18 and intersected it 0 times. That is not a coincidence of content —
 * DataGolf's five buckets are ALL at the ceiling (36 outcomes, 36 winners, #6211), and the
 * collision needs a point at the ceiling. So the population that triggers it is exactly
 * the censored population whose sample sizes a reader most needs to read: #6211 item 3
 * rules the flat line at 100% stays drawn precisely so it reads as an alarm, and the `n=`
 * labels are the part that says how little is behind it.
 *
 * The rule is an invariant, not an offset: the label stays inside the plot. The key lives
 * entirely above `padT` (baseline `padT - 10`, descenders ~2.5 below it), so "top of the
 * label is at or below the plot top" is sufficient to clear it, and it keeps clearing it
 * if the key ever moves within that band or changes length. `N_LABEL_FONT_PX` is used as
 * the ascent, which over-states a 9px cap height (~6.5) — deliberately, so the flip
 * happens a little before a reader could see the two marks touch.
 *
 * It does NOT hide anything: the label is moved, never dropped, and the flipped position
 * is the one `showAllN` has always drawn at.
 */
export function nLabelPlacement(pointY: number, r: number, plotTop: number): NLabelPlacement {
  const aboveBaseline = pointY - r - N_LABEL_GAP;
  if (aboveBaseline - N_LABEL_FONT_PX >= plotTop) return { y: aboveBaseline, below: false };
  return { y: pointY + r + N_LABEL_BELOW_OFFSET, below: true };
}

/**
 * Per-character advance for the `n=` label's 9px `system-ui`, in the chart's own user units.
 * `nSampleLabelsClearTheChartKey7434.test.tsx` derived it from production rects (`n=3` painted
 * 16.6 units over 3 characters) and rounded UP, so the box over-states the ink.
 */
export const N_LABEL_CHAR_ADVANCE_PX = 5.6;

/** The white halo (`strokeWidth` 2.5) reaches half its width past the glyphs on every side. It
 *  sizes a stacked row, but not the collision box: two halos touching erase nothing, and a label
 *  moved for a gap no reader could see drifts off its point for no gain (n=456 on DataGolf did). */
const N_LABEL_HALO = 1.25;

export interface NLabelCandidate {
  x: number;
  /** characters in the printed label, e.g. 5 for `n=764` */
  chars: number;
  /** placements in order of preference; the first is the one drawn before #8979 */
  options: NLabelPlacement[];
}

interface LabelBox {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function nLabelBox(x: number, chars: number, y: number): LabelBox {
  const half = (chars * N_LABEL_CHAR_ADVANCE_PX) / 2;
  return {
    left: x - half,
    right: x + half,
    top: y - N_LABEL_FONT_PX,
    bottom: y + N_LABEL_FONT_PX * 0.25,
  };
}

function boxesMeet(a: LabelBox, b: LabelBox): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

/** Half the curve's `strokeWidth` (2.5): a segment that passes this close to the glyphs strokes them. */
const CURVE_HALF_STROKE = 1.25;

/** One plotted point of the label's own series, in chart units: the curve runs through them in order. */
export interface NLabelPoint {
  x: number;
  y: number;
  r: number;
}

/** Liang–Barsky: does the segment (x1,y1)→(x2,y2) pass through the box? */
function segmentMeetsBox(x1: number, y1: number, x2: number, y2: number, b: LabelBox): boolean {
  const dx = x2 - x1;
  const dy = y2 - y1;
  let t0 = 0;
  let t1 = 1;
  const edges: Array<[number, number]> = [
    [-dx, x1 - b.left],
    [dx, b.right - x1],
    [-dy, y1 - b.top],
    [dy, b.bottom - y1],
  ];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const t = q / p;
    if (p < 0) t0 = Math.max(t0, t);
    else t1 = Math.min(t1, t);
    if (t0 > t1) return false;
  }
  return true;
}

/** The label's own series: its curve and markers, and the plot's side edges for a side spot. */
export interface NLabelObstacles {
  points: NLabelPoint[];
  plotLeft: number;
  plotRight: number;
}

function clearOfSeries(box: LabelBox, pointX: number, o: NLabelObstacles): boolean {
  const grown = {
    left: box.left - CURVE_HALF_STROKE,
    right: box.right + CURVE_HALF_STROKE,
    top: box.top - CURVE_HALF_STROKE,
    bottom: box.bottom + CURVE_HALF_STROKE,
  };
  for (let i = 0; i + 1 < o.points.length; i++) {
    const a = o.points[i];
    const b = o.points[i + 1];
    if (segmentMeetsBox(a.x, a.y, b.x, b.y, grown)) return false;
  }
  // It also has to read as ITS point's count: its box nearer its own marker than any other. A
  // label one row under a steep point otherwise lands beside the next point down. This is also
  // the marker test: a box that touches another marker is nearer that one. Every spot is built
  // off its own marker (`d >= r` while the radius stays under 10.2; it tops out at 10).
  const own = o.points.find(c => c.x === pointX);
  if (!own) return true;
  const gap = (c: NLabelPoint) => {
    const nx = Math.min(Math.max(c.x, box.left), box.right);
    const ny = Math.min(Math.max(c.y, box.top), box.bottom);
    return Math.hypot(c.x - nx, c.y - ny) - c.r;
  };
  const mine = gap(own);
  return o.points.every(c => c === own || gap(c) > mine);
}

/**
 * #8979 — WHY ONE SERIES' LABELS ARE PLACED TOGETHER.
 *
 * `nLabelPlacement` decides each label alone, so nothing stopped two neighbours from landing on
 * each other. On a 300-unit panel one bucket step is 22.5 units and `n=764` is ~28 wide, so
 * wherever the curve runs flat the labels overlap. Production, 2026-09-26, By Source →
 * DataGolf at 390px: the 20-50% buckets (764, 645, 710 outcomes, all within 3pp actual) printed
 * as one smear, `n=764n=645n=710`, which is the only place a reader learns how little is behind
 * those faded points.
 *
 * Left to right, each label takes the first option that overlaps no label already placed. The
 * first option is always today's position. The others count only if their whole box sits inside
 * the plot, so #7434's invariant (never in the key's band above `plotTop`) holds for every moved
 * label. If no option is free the label keeps today's position. Nothing is dropped, and a chart
 * with no collision draws exactly what it drew before.
 *
 * #9016 — TODAY'S POSITION HAS TO BE INSIDE THE PLOT TOO, WHEN SOMETHING INSIDE IS FREE.
 * The first option used to be exempt from the inside test. A single-series chart (`showAllN`)
 * prefers BELOW, and its 0-10% bucket is the busiest — the biggest marker, ~4% up from the
 * floor — so "below" landed in the x-axis number band. Production, 2026-09-27, By Source →
 * Polymarket at 390px: `23,602` printed over the axis `0%`; DataGolf: `6,257`. So a label takes
 * the first option that is inside AND free, and falls back to the old rule only when none is.
 * A label whose first option was already inside draws exactly where it did.
 *
 * #9026 — AND CLEAR OF ITS OWN CURVE, WHEN SOME SPOT IS.
 * Nothing tested a label against the line it annotates. On a steep stretch the segment coming
 * in from the lower left runs through "below" and the segment going out to the upper right runs
 * through "above". Production, 2026-09-27, By Source → Sportsbooks at 390px: the line struck
 * through `21,424`, `13,106`, `11,872` and `6,613`; Polymarket: `7,096` and `15,310`. So when
 * the caller passes the series' own points, a label first looks for a spot that is inside,
 * free, touches no segment, and sits nearer its own marker than any other (so on no marker);
 * the options now include four spots beside the point, the diagonals a rising curve leaves open
 * first. If no spot is that clean, the #9016 rule above
 * decides exactly as before, so a label is never worse off than it was. Without `obstacles`
 * nothing changes.
 */
export function dodgeNLabels(
  candidates: NLabelCandidate[],
  plotTop: number,
  plotBottom: number,
  obstacles?: NLabelObstacles,
): NLabelPlacement[] {
  const placed: LabelBox[] = [];
  const boxOf = (c: NLabelCandidate, p: NLabelPlacement) => nLabelBox(c.x + (p.dx ?? 0), c.chars, p.y);
  return candidates.map(c => {
    const free = (p: NLabelPlacement) => {
      const box = boxOf(c, p);
      return placed.every(o => !boxesMeet(box, o));
    };
    const inside = (p: NLabelPlacement) => {
      const box = boxOf(c, p);
      if (box.top < plotTop || box.bottom > plotBottom) return false;
      // A side spot is new, so it also has to stay within the plot's sides.
      if (p.dx == null) return true;
      return !!obstacles && box.left >= obstacles.plotLeft && box.right <= obstacles.plotRight;
    };
    const clear = (p: NLabelPlacement) => !obstacles || clearOfSeries(boxOf(c, p), c.x, obstacles);
    const chosen =
      (obstacles ? c.options.find(p => inside(p) && free(p) && clear(p)) : undefined) ??
      c.options.find(p => inside(p) && free(p)) ??
      c.options.find((p, i) => (i === 0 || inside(p)) && free(p)) ??
      c.options[0];
    placed.push(boxOf(c, chosen));
    return chosen;
  });
}

/**
 * The ordered options for one label: today's spot first, then the other side, then one row out.
 * #9026: given the label's width in characters, four spots beside the point (lower-right,
 * upper-left, right, left) come after the first two and before one row out. Only
 * `dodgeNLabels` called with `obstacles` takes them.
 */
export function nLabelOptions(
  pointY: number,
  r: number,
  plotTop: number,
  preferBelow: boolean,
  chars?: number,
): NLabelPlacement[] {
  const above = { y: pointY - r - N_LABEL_GAP, below: false };
  const below = { y: pointY + r + N_LABEL_BELOW_OFFSET, below: true };
  // One row = the label's full box (ascent + descent + halo both sides), so a stacked label clears.
  const row = Math.ceil(N_LABEL_FONT_PX * 1.25 + 2 * N_LABEL_HALO);
  let options: NLabelPlacement[];
  if (preferBelow) options = [below, above, { y: below.y + row, below: true }];
  else {
    const first = nLabelPlacement(pointY, r, plotTop);
    options = first.below
      ? [first, { y: first.y + row, below: true }]
      : [first, below, { y: first.y - row, below: false }];
  }
  if (chars == null) return options;
  const half = (chars * N_LABEL_CHAR_ADVANCE_PX) / 2;
  // Diagonals first: a rising curve leaves the lower-right and upper-left of each point open.
  // The box's near corner sits a gap off the marker's 45-degree point.
  const d = r * Math.SQRT1_2 + N_LABEL_GAP;
  const lowerRight = { y: pointY + d + N_LABEL_FONT_PX, below: true, dx: d + half };
  // A point near the ceiling would push this one into the key's band, so it slides down to the plot
  // top instead; `dodgeNLabels` still has to find it clear of the curve and the marker.
  const upperLeft = {
    y: Math.max(pointY - d - N_LABEL_FONT_PX * 0.25, plotTop + N_LABEL_FONT_PX),
    below: false,
    dx: -(d + half),
  };
  // The box spans `y - FONT` to `y + FONT/4`, so this baseline puts its middle on the point.
  const sideY = pointY + (N_LABEL_FONT_PX * 0.75) / 2;
  const sideDx = r + N_LABEL_GAP + half;
  const beside = [lowerRight, upperLeft, { y: sideY, below: false, dx: sideDx }, { y: sideY, below: false, dx: -sideDx }];
  // Beside the point comes before one row out: a row out is the spot most likely to sit nearer a
  // neighbour than its own point. Without `obstacles` the beside spots are never taken, so the
  // order a caller without the series sees is unchanged.
  return [...options.slice(0, 2), ...beside, ...options.slice(2)];
}

export function curveRuns(ns: number[], thinFloor: number): CurveRun[] {
  const runs: CurveRun[] = [];
  for (let i = 0; i + 1 < ns.length; i++) {
    const thin = ns[i] < thinFloor || ns[i + 1] < thinFloor;
    const last = runs[runs.length - 1];
    if (last && last.thin === thin && last.to === i) last.to = i + 1;
    else runs.push({ from: i, to: i + 1, thin });
  }
  return runs;
}

interface CalibrationChartProps {
  series: Series[];
  width?: number;
  height?: number;
  showLegend?: boolean;
  /** L2-75 §B: buckets with n below this render faded + dashed + show their n, so
   *  thin samples are honest without shouting. */
  thinFloor?: number;
  /** L2-103 Item 1: when a single series is shown, print each bucket's sample
   *  count below its point — consistent per-bucket n-counts on every source, not
   *  just the low-volume ones where a thin bucket happened to surface. */
  showAllN?: boolean;
  /** L2-103 Item 2: click a point to drill into the bucket's sample outcomes. */
  onPointClick?: (seriesIndex: number, point: CalPoint) => void;
}

export default function CalibrationChart({
  series,
  width: authoredW = 560,
  height: authoredH = 360,
  showLegend = true,
  thinFloor = 30,
  showAllN = false,
  onPointClick,
}: CalibrationChartProps) {
  const padL = 55, padR = 20, padT = 25, padB = 50;

  // #4394 — WHY THE CHART MEASURES ITS OWN CARD.
  //
  // #4330 took the dead space out of the box; the drawing inside it was still half size. A
  // `viewBox` scales the type with the geometry, so `width={700}` in a 324px card rendered every
  // axis number at 5.1 CSS px and every `n=` label at 4.2 px — present to a DOM census, texture to
  // a reader. Scaling the FONTS back up instead would keep an 11-label axis in a 249px plot, so
  // the geometry is what has to give: below `REAUTHOR_BELOW` of the authored width the chart is
  // re-authored at the container's own width, 1:1, where 11px means 11px.
  //
  // `null` until the observer fires — that is also the server render, so the SSR markup is the
  // authored geometry unchanged and #4330's guard still reads what it was written to read.
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [containerW, setContainerW] = useState<number | null>(null);
  useEffect(() => {
    const el = hostRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(entries => {
      const w = entries[entries.length - 1]?.contentRect.width;
      if (w && w > 0) setContainerW(Math.round(w));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { width, height, reauthored, xLabelStep } = chartGeometry(authoredW, authoredH, containerW);

  const { plotW, plotH } = plotDims(width, height, { padL, padR, padT, padB });

  // Both axes are fixed 0–100% (predicted × actual). Shared px/py skeleton — see lib/chartScale.ts.
  const px = scaleX(0, 100, padL, plotW);
  const py = scaleY(0, 100, padT, plotH);

  const bandPointsUpper = useMemo(() =>
    Array.from({ length: 21 }, (_, i) => i * 5)
      .map(v => `${px(v)},${py(Math.min(100, v + 5))}`)
      .join(" "), [width, height]);

  const bandPointsLower = useMemo(() =>
    Array.from({ length: 21 }, (_, i) => 100 - i * 5)
      .map(v => `${px(v)},${py(Math.max(0, v - 5))}`)
      .join(" "), [width, height]);

  // The legend sits in the plot's empty top-left corner, which holds two rows. A re-authored
  // chart fits one column, so five categories would stack five rows deep across the curves —
  // below the plot instead, with the box grown by exactly the rows it uses.
  const legendItemW = 165;
  const legendRowH = 16;
  const legendCols = Math.max(1, Math.floor((width - padL - padR) / legendItemW));
  const legendRows = showLegend && series.length > 0 ? Math.ceil(series.length / legendCols) : 0;
  const legendBelow = legendRows > 2;
  const legendH = legendBelow ? legendRows * legendRowH + 10 : 0;
  const boxH = height + legendH;

  return (
    <div ref={hostRef} className="w-full">
    <svg
      width={width}
      height={boxH}
      viewBox={`0 0 ${width} ${boxH}`}
      data-authored-width={authoredW}
      data-reauthored={reauthored ? "true" : "false"}
      // #4400: the label decision, readable by a production probe. Notice 34 — a number a probe
      // needs lives in a data-attribute, never in prose on the reader's screen.
      data-x-label-step={xLabelStep}
      className="block mx-auto"
      // #4330: `height` is a presentation attribute, so it sets the CSS height and nothing
      // overrode it, while `maxWidth` shrank only the width. Below 700px `preserveAspectRatio`
      // then drew a 157px-tall chart centred in the 340px box it was still given, and the two
      // transparent bands (91px and 107px on the page's two wide-and-short call sites) read to a
      // phone reader as the card being broken. `height: auto` lets the viewBox's aspect ratio
      // set the height once the width is constrained. Measured on production: every band → 0px
      // at 390px with `drawn` byte-identical, and all nine charts identical at 1280px, where the
      // max-width never binds. Probe: tools/chart-letterbox-1067.mjs.
      style={{ fontFamily: "-apple-system, system-ui, sans-serif", maxWidth: "100%", height: "auto" }}
    >
      <rect width={width} height={boxH} fill="white" rx="8" />

      {/* Grid lines */}
      {Array.from({ length: 11 }, (_, i) => i * 10).map(v => (
        <g key={v}>
          <line x1={padL} y1={py(v)} x2={width - padR} y2={py(v)} stroke="#f0f0f0" strokeWidth="1" />
          <line x1={px(v)} y1={padT} x2={px(v)} y2={height - padB} stroke="#f0f0f0" strokeWidth="1" />
          <text x={padL - 8} y={py(v) + 4} textAnchor="end" fill="#a8a29e" fontSize="11">{v}%</text>
          {v % xLabelStep === 0 && (
            <text x={px(v)} y={height - padB + 18} textAnchor="middle" fill="#a8a29e" fontSize="11">{v}%</text>
          )}
        </g>
      ))}

      {/* Axis labels */}
      <text x={width / 2} y={height - 5} textAnchor="middle" fill="#57534e" fontSize="12" fontWeight="600">
        Predicted Probability
      </text>
      <text
        x="14" y={height / 2} textAnchor="middle" fill="#57534e" fontSize="12" fontWeight="600"
        transform={`rotate(-90,14,${height / 2})`}
      >
        Actual Win Rate
      </text>

      {/* ±5pp confidence band */}
      <polygon points={`${bandPointsUpper} ${bandPointsLower}`} fill="#f1f5f9" opacity="0.5" />

      {/* Perfect calibration diagonal */}
      <line x1={px(0)} y1={py(0)} x2={px(100)} y2={py(100)} stroke="#cbd5e1" strokeWidth="2" strokeDasharray="6,4" />

      {/* Data series */}
      {series.map((s, si) => {
        if (!s.data.length) return null;
        const maxN = Math.max(...s.data.map(d => d.n));
        const radius = (n: number) => 4 + 6 * Math.sqrt(n / maxN);
        // #8979: which points print a label, and where — decided for the series at once so
        // neighbours cannot land on each other. Same two rules as the marks below.
        const allN = showAllN && series.length === 1;
        const labelled = s.data
          .map((d, di) => ({ d, di }))
          .filter(({ d }) => allN || d.n < thinFloor);
        const placements = new Map<number, NLabelPlacement>();
        dodgeNLabels(
          labelled.map(({ d }) => {
            const chars = (allN ? d.n.toLocaleString() : `n=${d.n}`).length;
            const options = nLabelOptions(py(d.actual), radius(d.n), padT, allN, allN ? chars : undefined);
            return { x: px(d.midpoint), chars, options };
          }),
          padT,
          height - padB,
          // #9026: the series' own curve and markers, so a count does not land on the line it
          // annotates. Only the every-bucket counts: they sit on the solid line. A thin bucket's
          // `n=` sits on a faded dashed stretch and keeps exactly the #8979 placement.
          allN
            ? {
                points: s.data.map(d => ({ x: px(d.midpoint), y: py(d.actual), r: radius(d.n) })),
                plotLeft: padL,
                plotRight: width - padR,
              }
            : undefined,
        ).forEach((p, i) => placements.set(labelled[i].di, p));
        return (
          <g key={si}>
            {/* #7399: one polyline per run, not one for the whole curve. See
                `curveRuns` — the thin convention has to reach the mark the eye
                actually follows. */}
            {curveRuns(s.data.map(d => d.n), thinFloor).map((run, ri) => (
              <polyline
                key={`run-${ri}`}
                points={s.data
                  .slice(run.from, run.to + 1)
                  .map(d => `${px(d.midpoint)},${py(d.actual)}`)
                  .join(" ")}
                fill="none"
                stroke={s.color}
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={run.thin ? 0.28 : 1}
                strokeDasharray={run.thin ? "4,4" : undefined}
                data-thin={run.thin ? "true" : "false"}
              />
            ))}
            {/* CI error bars — rendered behind dots */}
            {s.data.map((d, di) => {
              if (d.ciLower == null || d.ciUpper == null) return null;
              const cx = px(d.midpoint);
              const capW = 4;
              return (
                <g key={`ci-${di}`} opacity="0.4">
                  <line x1={cx} y1={py(d.ciLower)} x2={cx} y2={py(d.ciUpper)} stroke={s.color} strokeWidth="2" />
                  <line x1={cx - capW} y1={py(d.ciLower)} x2={cx + capW} y2={py(d.ciLower)} stroke={s.color} strokeWidth="2" />
                  <line x1={cx - capW} y1={py(d.ciUpper)} x2={cx + capW} y2={py(d.ciUpper)} stroke={s.color} strokeWidth="2" />
                </g>
              );
            })}
            {s.data.map((d, di) => {
              const r = radius(d.n);
              // L2-75 §B: thin buckets (below the n-floor) are faded + dashed-ring
              // + show their n, so a small sample is visibly less certain.
              const thin = d.n < thinFloor;
              const ciStr = d.ciLower != null && d.ciUpper != null
                ? `, 95% CI: ${d.ciLower.toFixed(1)}%-${d.ciUpper.toFixed(1)}%`
                : "";
              // L2-103 Item 1: on single-series views, print every bucket's n
              // below the point (consistent treatment across all sources). On the
              // multi-series "All" view this would collide, so it stays off there.
              const singleSeries = series.length === 1;
              const clickable = !!onPointClick;
              return (
                <g
                  key={di}
                  onClick={clickable ? () => onPointClick!(si, d) : undefined}
                  style={clickable ? { cursor: "pointer" } : undefined}
                >
                  {clickable && (
                    <circle cx={px(d.midpoint)} cy={py(d.actual)} r={r + 6} fill="transparent" />
                  )}
                  <circle
                    cx={px(d.midpoint)} cy={py(d.actual)} r={r}
                    fill={s.color}
                    opacity={thin ? 0.28 : 0.85}
                    stroke={thin ? s.color : "none"}
                    strokeWidth={thin ? 1.5 : 0}
                    strokeDasharray={thin ? "2,2" : undefined}
                  />
                  {thin && !(showAllN && singleSeries) && (() => {
                    // #7434: above the point unless that would put it in the key's band;
                    // #8979: moved off a neighbour when the two would overlap.
                    const place = placements.get(di) ?? nLabelPlacement(py(d.actual), r, padT);
                    return (
                      <text
                        x={px(d.midpoint) + (place.dx ?? 0)} y={place.y}
                        textAnchor="middle" fill="#a8a29e" fontSize={N_LABEL_FONT_PX}
                        // #7434: a flipped label lands over its own CI bar (a ceiling point's
                        // bar runs the height of the plot), and either placement can land on a
                        // gridline. A white halo behind the glyphs costs nothing and is the same
                        // treatment for both, so the fix does not trade one illegibility for
                        // another. Applied to the always-below label too — one mark, one rule.
                        stroke="white" strokeWidth="2.5" paintOrder="stroke"
                        data-n-label-below={place.below ? "true" : "false"}
                      >
                        n={d.n}
                      </text>
                    );
                  })()}
                  {showAllN && singleSeries && (() => {
                    const place = placements.get(di) ?? { y: py(d.actual) + r + N_LABEL_BELOW_OFFSET, below: true };
                    return (
                    <text
                      x={px(d.midpoint) + (place.dx ?? 0)} y={place.y}
                      textAnchor="middle" fill="#a8a29e" fontSize={N_LABEL_FONT_PX}
                      stroke="white" strokeWidth="2.5" paintOrder="stroke"
                      data-n-label-below={place.below ? "true" : "false"}
                    >
                      {d.n.toLocaleString()}
                    </text>
                    );
                  })()}
                  <title>
                    {d.bucket}: {d.actual.toFixed(1)}% actual at {d.midpoint}% predicted (n={d.n.toLocaleString()}{thin ? ", thin sample" : ""}, error={d.error > 0 ? "+" : ""}{d.error.toFixed(1)}pp{ciStr})
                  </title>
                </g>
              );
            })}
          </g>
        );
      })}

      {/* Legend (L2-80 Item 5: wrap onto rows so many series — By Source / By Category
          can have 5-6 — don't pile up at one clamped x-position and overlap).
          #4394: three rows or more no longer fit the empty top-left corner, so they go under the
          chart and the box grows to hold them, rather than being drawn across the curves. */}
      {showLegend && series.length > 0 && (() => {
        const itemW = legendItemW;
        const cols = legendCols;
        const rowH = legendRowH;
        return (
          <g>
            {series.map((s, i) => {
              const col = i % cols;
              const row = Math.floor(i / cols);
              const lx = (legendBelow ? padL - 40 : padL + 10) + col * itemW;
              const ly = (legendBelow ? height + 10 : padT + 8) + row * rowH;
              return (
                <g key={i}>
                  <circle cx={lx} cy={ly} r="5" fill={s.color} />
                  <text x={lx + 10} y={ly + 4} fill="#57534e" fontSize="11">{s.label}</text>
                </g>
              );
            })}
          </g>
        );
      })()}

      {/* Dot-size + thin-bucket key (L2-75 §B; #7399 adds the line, which carries
          the same convention and used to be the one mark the key did not cover). */}
      <text x={width - padR} y={padT - 10} textAnchor="end" fill="#a8a29e" fontSize="9.5">
        {thinBucketKey(thinFloor)}
      </text>
    </svg>
    </div>
  );
}
