import React from "react";
import { sparklinePoints, trendDirection, type TournamentTrendPoint } from "@/lib/tournament";

interface Props {
  trend: TournamentTrendPoint[];
  delta: number | null;
  /** Non-live rows draw in a neutral tone — a stale line must not read as a live move. */
  muted?: boolean;
  width?: number;
  height?: number;
}

/**
 * Unsmoothed trend line on a fixed 0-100 axis (charter design doctrine).
 *
 * Every vertex is a real daily observation. There is no curve fitting, no
 * moving average and no auto-scaled axis: at a fixed axis a 2pp wiggle looks
 * like a 2pp wiggle, which is the whole reason movement is legible here.
 */
export default function TrendSparkline({
  trend,
  delta,
  muted = false,
  width = 52,
  height = 26,
}: Props) {
  const points = sparklinePoints(trend, width, height);
  if (!points) {
    // One point is not a trend. Render the slot so rows stay aligned, but draw
    // nothing rather than implying a journey we did not observe.
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
        data-testid="trend-sparkline-empty"
      />
    );
  }

  const direction = trendDirection(delta);
  const stroke = muted
    ? "var(--text-muted)"
    : direction === "down"
      ? "var(--accent-danger)"
      : direction === "up"
        ? "var(--accent-live)"
        : "var(--text-muted)";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      data-testid="trend-sparkline"
      data-direction={direction}
      data-points={trend.length}
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
