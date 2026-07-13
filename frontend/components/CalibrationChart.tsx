"use client";

import { useMemo } from "react";

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
  width = 560,
  height = 360,
  showLegend = true,
  thinFloor = 30,
  showAllN = false,
  onPointClick,
}: CalibrationChartProps) {
  const padL = 55, padR = 20, padT = 25, padB = 50;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const px = (pct: number) => padL + (pct / 100) * plotW;
  const py = (pct: number) => padT + ((100 - pct) / 100) * plotH;

  const bandPointsUpper = useMemo(() =>
    Array.from({ length: 21 }, (_, i) => i * 5)
      .map(v => `${px(v)},${py(Math.min(100, v + 5))}`)
      .join(" "), [width, height]);

  const bandPointsLower = useMemo(() =>
    Array.from({ length: 21 }, (_, i) => 100 - i * 5)
      .map(v => `${px(v)},${py(Math.max(0, v - 5))}`)
      .join(" "), [width, height]);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block mx-auto"
      style={{ fontFamily: "-apple-system, system-ui, sans-serif", maxWidth: "100%" }}
    >
      <rect width={width} height={height} fill="white" rx="8" />

      {/* Grid lines */}
      {Array.from({ length: 11 }, (_, i) => i * 10).map(v => (
        <g key={v}>
          <line x1={padL} y1={py(v)} x2={width - padR} y2={py(v)} stroke="#f0f0f0" strokeWidth="1" />
          <line x1={px(v)} y1={padT} x2={px(v)} y2={height - padB} stroke="#f0f0f0" strokeWidth="1" />
          <text x={padL - 8} y={py(v) + 4} textAnchor="end" fill="#a8a29e" fontSize="11">{v}%</text>
          <text x={px(v)} y={height - padB + 18} textAnchor="middle" fill="#a8a29e" fontSize="11">{v}%</text>
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
        const pathPoints = s.data.map(d => `${px(d.midpoint)},${py(d.actual)}`).join(" ");
        return (
          <g key={si}>
            <polyline points={pathPoints} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" />
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
              const r = 4 + 6 * Math.sqrt(d.n / maxN);
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
                  {thin && !(showAllN && singleSeries) && (
                    <text
                      x={px(d.midpoint)} y={py(d.actual) - r - 3}
                      textAnchor="middle" fill="#a8a29e" fontSize="9"
                    >
                      n={d.n}
                    </text>
                  )}
                  {showAllN && singleSeries && (
                    <text
                      x={px(d.midpoint)} y={py(d.actual) + r + 11}
                      textAnchor="middle" fill="#a8a29e" fontSize="9"
                    >
                      {d.n.toLocaleString()}
                    </text>
                  )}
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
          can have 5-6 — don't pile up at one clamped x-position and overlap) */}
      {showLegend && series.length > 0 && (() => {
        const itemW = 165;
        const cols = Math.max(1, Math.floor((width - padL - padR) / itemW));
        const rowH = 16;
        return (
          <g>
            {series.map((s, i) => {
              const col = i % cols;
              const row = Math.floor(i / cols);
              const lx = padL + 10 + col * itemW;
              const ly = padT + 8 + row * rowH;
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

      {/* Dot-size + thin-bucket key (L2-75 §B) */}
      <text x={width - padR} y={padT - 10} textAnchor="end" fill="#a8a29e" fontSize="9.5">
        {`● size = sample count · faded ○ = thin (n<${thinFloor})`}
      </text>
    </svg>
  );
}
