'use client';

/**
 * live/034 S2c — the last-10-minute sparkline.
 *
 * Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES 2): a live look is an animated
 * number, a "live · Ns ago" pulse, and a last-10-min sparkline — **no
 * smoothing**.
 *
 * So this draws a polyline through the points as served and nothing else: no
 * spline, no moving average, no resampling. Every vertex is a reading the
 * server actually produced. That constraint is the whole point — a smoothed
 * line invents intermediate probabilities that no source ever quoted, and on a
 * ten-minute window that is most of what you would be looking at.
 *
 * It is deliberately NOT the win-probability chart in miniature. It has no axes,
 * no tooltip and no source toggles, because it answers one question — has this
 * number been moving just now — that the full chart answers slowly.
 */

export interface SparkPoint {
  timestamp: string;
  value: number;
}

interface LiveSparklineProps {
  points: SparkPoint[];
  /** Minutes of history to draw. The ruling says ten. */
  windowMinutes?: number;
  width?: number;
  height?: number;
  className?: string;
}

/** Below this many points there is no shape to show, only noise. */
const MIN_POINTS = 3;

/**
 * The narrowest y-axis this glyph will ever draw, in probability (0-1).
 *
 * native/027 (#3313) — the original rule was "pin y to the FULL 0-100%", to stop
 * an auto-scaled axis turning a one-point wobble into a mountain. That concern is
 * real and this constant keeps it. What the rule got wrong is the other side: a
 * 24px box holding the whole 0-100 range resolves one percentage point to
 * 0.24px, so it cannot show the movement it exists to report.
 *
 * Measured against production, 26 live events, 2026-09-05 14:05 PT — of the 16
 * carrying at least MIN_POINTS in the window, **15 drew less vertical travel
 * than twice the 1.5px stroke**. Only three were actually flat (range under one
 * point); eight had moved five points or more, and a Cubs-Marlins game had swung
 * 19 — the most dramatic thing on its page — which the full-range axis rendered
 * as 4.6px of wiggle. The glyph was not reporting calm markets, it was hiding
 * live ones.
 *
 * So the axis is the data's own range widened to at least this span, never
 * narrower. Both failure modes are then bounded by one number:
 *   * a 1-point wobble spans 1/20th of the box — still visually flat, which is
 *     the honest reading, so the mountain the original rule feared cannot appear;
 *   * a 19-point swing fills the box, because the span floor is the FLOOR and
 *     a wider range widens the axis with it.
 *
 * ONE CONTRACT with the phone: `LiveSparklineChart.minimumSpan` in
 * `ios/Bain Luck/Bain Luck/Components/LiveSparklineChart.swift` carries the same
 * number, and each side pins the literal in its own test — the same arrangement
 * `CEILING_STEPS` / `RaceChart.ceilingSteps` uses (native/023, #3032). Change one
 * and the other side's test fails, which is the point.
 */
export const MIN_SPAN = 0.2;

/**
 * Vertical breathing room, in px, kept clear at the top and bottom of the box.
 *
 * native/024's lesson applied one size down: *a rule that MOVES an element
 * invalidates every spacing decision taken before the move.* Pinning y to the
 * full 0-100 range meant real data almost never reached the frame, so a stroke
 * centred on the extreme value was never noticeably sliced. With a span floor the
 * opposite is true BY CONSTRUCTION — whenever the data range exceeds the floor the
 * domain IS that range, so the highest and lowest readings sit exactly on the
 * edges and half the 1.5px stroke lands outside the box on every such glyph.
 *
 * Caught by reading the raster, not by a test: the first render of the
 * Cubs-Marlins swing measured 72px of ink in a 72px box, which is the line
 * touching both frames.
 */
const STROKE_INSET = 1;

/**
 * The y-axis [min, max] this series should be drawn against.
 *
 * Pure and exported so the rule is tested as arithmetic rather than inferred from
 * SVG coordinates. Slides rather than squashes at the edges: a series sitting at
 * 96% gets [0.8, 1.0], not a clipped or compressed box, so the span the reader is
 * judging travel against is the same everywhere on the axis.
 */
export function sparklineDomain(
  values: number[],
  minimumSpan: number = MIN_SPAN,
): [number, number] {
  if (values.length === 0) return [0, 1];
  const clamped = values.map((v) => Math.min(1, Math.max(0, v)));
  const lo = Math.min(...clamped);
  const hi = Math.max(...clamped);
  const floor = Math.min(1, Math.max(0, minimumSpan));
  if (hi - lo >= floor) return [lo, hi];
  const mid = (lo + hi) / 2;
  let min = mid - floor / 2;
  let max = mid + floor / 2;
  // Slide the window back inside [0,1] keeping its width, so a near-certain or
  // near-hopeless market is judged against the same span as an even one.
  if (min < 0) [min, max] = [0, floor];
  if (max > 1) [min, max] = [1 - floor, 1];
  return [min, max];
}

/**
 * The last `windowMinutes` of points, oldest first.
 *
 * Exported and pure so the windowing is testable directly: this harness renders
 * with `renderToStaticMarkup`, and asserting a clipped window through drawn SVG
 * path coordinates would be a test of the arithmetic's output format rather
 * than of the arithmetic.
 */
export function windowPoints(
  points: SparkPoint[],
  windowMinutes: number,
  now: number,
): SparkPoint[] {
  const cutoff = now - windowMinutes * 60_000;
  return points
    .filter((p) => {
      const t = Date.parse(p.timestamp);
      // A point we cannot place in time is dropped, not drawn at an arbitrary
      // x — a mis-placed vertex is a shape that did not happen.
      return !Number.isNaN(t) && t >= cutoff && Number.isFinite(p.value);
    })
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}

/**
 * Map points to an SVG polyline.
 *
 * The y-axis is NOT auto-scaled to the data — it is the data's range widened to
 * at least `MIN_SPAN`, which is what stops a one-point wobble reading as a
 * dramatic mountain while still letting a real swing be seen. See `MIN_SPAN`.
 */
export function polylinePoints(
  windowed: SparkPoint[],
  width: number,
  height: number,
  minimumSpan: number = MIN_SPAN,
): string {
  if (windowed.length < MIN_POINTS) return '';
  const first = Date.parse(windowed[0].timestamp);
  const last = Date.parse(windowed[windowed.length - 1].timestamp);
  const span = last - first;
  const [yMin, yMax] = sparklineDomain(
    windowed.map((p) => p.value),
    minimumSpan,
  );
  const yRange = yMax - yMin;
  // Keep the stroke inside the box at the extremes; see STROKE_INSET.
  const inset = Math.min(STROKE_INSET, height / 4);
  const usable = height - inset * 2;
  return windowed
    .map((p, i) => {
      // A zero span means every point shares a timestamp; spread them evenly
      // rather than stacking them all on x=0.
      const x =
        span > 0
          ? ((Date.parse(p.timestamp) - first) / span) * width
          : (i / (windowed.length - 1)) * width;
      const clamped = Math.min(1, Math.max(0, p.value));
      // yRange can only be 0 if MIN_SPAN was passed as 0; centre rather than
      // divide by zero.
      const unit = yRange > 0 ? (clamped - yMin) / yRange : 0.5;
      const y = height - inset - unit * usable;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

export default function LiveSparkline({
  points,
  windowMinutes = 10,
  width = 96,
  height = 24,
  className,
}: LiveSparklineProps) {
  const windowed = windowPoints(points, windowMinutes, Date.now());
  const line = polylinePoints(windowed, width, height);
  // Nothing to say is said by showing nothing, not by drawing a flat line that
  // implies a steady market we have no readings for.
  if (!line) return null;

  const firstValue = windowed[0].value;
  const lastValue = windowed[windowed.length - 1].value;
  const rising = lastValue >= firstValue;
  const stroke = rising ? '#10B981' : '#EF4444';

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label={`Last ${windowMinutes} minutes: ${Math.round(firstValue * 100)}% to ${Math.round(lastValue * 100)}%`}
      data-testid="live-sparkline"
      data-point-count={windowed.length}
    >
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
