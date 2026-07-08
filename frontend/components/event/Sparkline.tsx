"use client";

// #999 L2-64 Event Concept Page — per-competitor sparkline. Tiny inline SVG of a
// probability series (0–1). Straight segments (no smoothing, D1 bind), light
// tokens. Renders nothing for <2 real points so a row never shows invented
// history — the caller passes a real series or omits the sparkline.

interface SparklineProps {
  /** Probability series in 0–1, time-ordered. */
  series: number[];
  width?: number;
  height?: number;
  className?: string;
}

export default function Sparkline({
  series,
  width = 56,
  height = 18,
  className,
}: SparklineProps) {
  const pts = (series || []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (pts.length < 2) return null;

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const n = pts.length;

  const coords = pts.map((v, i) => {
    const x = (i / (n - 1)) * (width - 2) + 1;
    // Invert Y (SVG origin top-left); pad 1px so the stroke isn't clipped.
    const y = height - 1 - ((v - min) / span) * (height - 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  // Rising overall = brand green, falling = danger, flat = muted.
  const trend = pts[n - 1] - pts[0];
  const stroke =
    trend > 0.0005
      ? "var(--accent-brand)"
      : trend < -0.0005
        ? "var(--accent-danger)"
        : "var(--text-muted)";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
