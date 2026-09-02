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
 * The y-axis is the FULL 0-100% range, never auto-scaled to the data. An
 * auto-scaled sparkline turns a one-point wobble into a dramatic mountain,
 * which is exactly the false story a "has this been moving" glance must not be
 * told.
 */
export function polylinePoints(
  windowed: SparkPoint[],
  width: number,
  height: number,
): string {
  if (windowed.length < MIN_POINTS) return '';
  const first = Date.parse(windowed[0].timestamp);
  const last = Date.parse(windowed[windowed.length - 1].timestamp);
  const span = last - first;
  return windowed
    .map((p, i) => {
      // A zero span means every point shares a timestamp; spread them evenly
      // rather than stacking them all on x=0.
      const x =
        span > 0
          ? ((Date.parse(p.timestamp) - first) / span) * width
          : (i / (windowed.length - 1)) * width;
      const clamped = Math.min(1, Math.max(0, p.value));
      const y = height - clamped * height;
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
