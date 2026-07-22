/**
 * Sparkline — THE single-market line renderer (L2-150 kernel-(c) consolidation).
 *
 * One component replacing five copy-pasted single-market line/sparkline renderers:
 *   • components/event/Sparkline.tsx        (leaderboard row spark, trend-colored)
 *   • components/weather/Sparkline.tsx      (weather spark — its cubic bezier is KILLED here)
 *   • components/FuturesHero.tsx (inline)   (futures hero mini spark, brand line + end dot)
 *   • app/politics/page.tsx (inline)        (politics table spark)
 *   • components/story/CaseStudyChart.tsx   (its `type:"line"` annotated moment)
 *
 * Standing chart rulings executed here (no taste calls — see L2-149):
 *   1. NO smoothing — raw `M/L` (`<path>`) segments between real observations. No bezier.
 *   2. Fixed axis for probability — `domain` defaults to [0,100] so magnitude reads
 *      honestly; pass [0,1] for 0–1 probability inputs, or "auto" for physical quantities.
 *   4. Minimal chrome — line + optional faint area / end dot / 50%-style reference line /
 *      one annotated moment. Nothing more.
 *
 * Pure presentational SVG: no client-only hooks and no `window` access, so it renders
 * from server components (the story/about case-study card) and client components alike.
 */
import { useId } from "react";

type Domain = [number, number] | "auto";

export interface SparklineProps {
  /** The value series, time-ordered. Non-finite values are dropped. */
  data: number[];
  /**
   * Y-axis domain. Default [0,100] pins probability honestly (ruling #2).
   * Pass [0,1] for 0–1 probability inputs; "auto" min/max-fits physical quantities.
   */
  domain?: Domain;
  width?: number;
  height?: number;
  /** Stroke width. Default 1.5 (sparkline); the case-study line uses ~2.5. */
  stroke?: number;
  /**
   * A CSS color string, or "trend" to color by net rise (brand) / fall (danger) /
   * flat (muted) using design-system tokens.
   */
  color?: string;
  /** Faint area under the line: "gradient" (color fade) or "flat" (single low-opacity fill). */
  area?: "gradient" | "flat" | false;
  /** Draw a dot at the last point. */
  endDot?: boolean;
  /** Dashed horizontal reference line at this domain value (e.g. 50 for the 50% line). */
  referenceValue?: number;
  /** Mark one point with a vertical line + double dot + a placed label. */
  annotation?: { index: number; label: string };
  /** Rendered as a `<figcaption>` under the chart; also switches the wrapper to `<figure>`. */
  caption?: string;
  /** Draw-on animation (weather legacy). Disabled under prefers-reduced-motion via CSS. */
  animate?: boolean;
  /** Per-side padding overrides (defaults: 2 all round; the annotated variant needs more). */
  padX?: number;
  padTop?: number;
  padBottom?: number;
  className?: string;
  /** Accessible label. When set the SVG is `role="img"`; otherwise it is `aria-hidden`. */
  ariaLabel?: string;
}

// Trend-color threshold: net move as a fraction of the domain span. Matches the old
// event spark sensitivity (~0.05pp on a [0,1] domain) and applies uniformly to any domain.
const TREND_EPS_FRACTION = 5e-4;

export default function Sparkline({
  data,
  domain = [0, 100],
  width = 96,
  height = 28,
  stroke = 1.5,
  color = "trend",
  area = false,
  endDot = false,
  referenceValue,
  annotation,
  caption,
  animate = false,
  padX = 2,
  padTop = 2,
  padBottom = 2,
  className,
  ariaLabel,
}: SparklineProps) {
  const gradientId = useId();
  const pts = (data || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (pts.length < 2) return null;

  const [lo, hi] =
    domain === "auto"
      ? (() => {
          const mn = Math.min(...pts);
          const mx = Math.max(...pts);
          return mx === mn ? [mn - 1, mn + 1] : [mn, mx];
        })()
      : domain;
  const span = hi - lo || 1;

  const n = pts.length;
  const usableW = width - padX * 2;
  const usableH = height - padTop - padBottom;
  const x = (i: number) => padX + (usableW * i) / (n - 1);
  const y = (v: number) => padTop + usableH * (1 - (v - lo) / span);

  // Ruling #1: raw straight segments, never a smoothed curve.
  const linePath = pts
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  const areaPath =
    area && `${linePath} L${x(n - 1).toFixed(1)},${height} L${x(0).toFixed(1)},${height} Z`;

  // Trend coloring uses design-system tokens (light-mode only).
  const trend = (pts[n - 1] - pts[0]) / span;
  const strokeColor =
    color === "trend"
      ? trend > TREND_EPS_FRACTION
        ? "var(--accent-brand)"
        : trend < -TREND_EPS_FRACTION
          ? "var(--accent-danger)"
          : "var(--text-muted)"
      : color;
  const areaFill = area === "gradient" ? `url(#${gradientId})` : strokeColor;
  const areaOpacity = area === "flat" ? 0.08 : 1;

  const last = { x: x(n - 1), y: y(pts[n - 1]) };

  // Stretch decorative sparklines; keep aspect ratio for the scaled, annotated case-study line.
  const aspect = caption || annotation ? undefined : "none";

  // One annotated moment (case-study line): vertical marker, double dot, placed label.
  const ann =
    annotation && (() => {
      const ai = Math.max(0, Math.min(n - 1, annotation.index));
      const ax = x(ai);
      const ay = y(pts[ai]);
      const labelRight = ax > width / 2;
      return { ax, ay, labelRight, label: annotation.label };
    })();

  const svg = (
    <svg
      width={caption ? undefined : width}
      height={caption ? undefined : height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio={aspect}
      {...(ariaLabel ? { role: "img", "aria-label": ariaLabel } : { "aria-hidden": "true" })}
    >
      {animate && (
        <style>{`
          .spark-line-${gradientId.replace(/[^a-zA-Z0-9]/g, "")} {
            stroke-dasharray: 400;
            stroke-dashoffset: 400;
            animation: spark-draw-${gradientId.replace(/[^a-zA-Z0-9]/g, "")} 1.2s ease-out forwards;
          }
          @keyframes spark-draw-${gradientId.replace(/[^a-zA-Z0-9]/g, "")} { to { stroke-dashoffset: 0; } }
          @media (prefers-reduced-motion: reduce) {
            .spark-line-${gradientId.replace(/[^a-zA-Z0-9]/g, "")} { animation: none; stroke-dashoffset: 0; }
          }
        `}</style>
      )}
      {area === "gradient" && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity={0.18} />
            <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
          </linearGradient>
        </defs>
      )}

      {referenceValue != null && (
        <line
          x1={padX}
          x2={width - padX}
          y1={y(referenceValue)}
          y2={y(referenceValue)}
          stroke="var(--surface-border)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
      )}

      {areaPath && <path d={areaPath} fill={areaFill} fillOpacity={areaOpacity} />}

      <path
        d={linePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={
          animate ? `spark-line-${gradientId.replace(/[^a-zA-Z0-9]/g, "")}` : undefined
        }
      />

      {ann && (
        <>
          <line
            x1={ann.ax}
            x2={ann.ax}
            y1={ann.ay}
            y2={height - padBottom}
            stroke="var(--text-muted)"
            strokeWidth={1}
            strokeDasharray="2 2"
          />
          <circle cx={ann.ax} cy={ann.ay} r={5.5} fill={strokeColor} />
          <circle cx={ann.ax} cy={ann.ay} r={2.5} fill="#fff" />
          <text
            x={ann.labelRight ? ann.ax - 8 : ann.ax + 8}
            y={Math.max(padTop + 4, ann.ay - 8)}
            fill="var(--text-primary)"
            fontSize={11}
            fontWeight={600}
            textAnchor={ann.labelRight ? "end" : "start"}
          >
            {ann.label}
          </text>
        </>
      )}

      {endDot && <circle cx={last.x} cy={last.y} r={2.4} fill={strokeColor} />}
    </svg>
  );

  if (caption) {
    return (
      <figure className="m-0">
        {svg}
        <figcaption className="text-micro text-text-muted mt-1.5">{caption}</figcaption>
      </figure>
    );
  }
  return svg;
}
