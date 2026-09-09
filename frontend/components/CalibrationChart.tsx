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
 */
export function chartGeometry(
  authoredW: number,
  authoredH: number,
  containerW: number | null,
): ChartGeometry {
  const reauthored = containerW != null && containerW < authoredW * REAUTHOR_BELOW;
  if (!reauthored) {
    return { width: authoredW, height: authoredH, reauthored: false, xLabelStep: 10 };
  }
  const width = Math.max(MIN_REAUTHORED_W, containerW!);
  // Eleven "100%" labels need ~28px each and a re-authored plot gives ~25px per tick, so they are
  // thinned to every 20%. The gridlines stay every 10%, so no resolution is lost — only the smear.
  return { width, height: width, reauthored: true, xLabelStep: 20 };
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

      {/* Dot-size + thin-bucket key (L2-75 §B) */}
      <text x={width - padR} y={padT - 10} textAnchor="end" fill="#a8a29e" fontSize="9.5">
        {`● size = sample count · faded ○ = thin (n<${thinFloor})`}
      </text>
    </svg>
    </div>
  );
}
