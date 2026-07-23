"use client";

import { useMemo, useState } from "react";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { canZoomSeries, computeZoomBound, resolveYAxisMax } from "@/lib/chartZoom";
import {
  SERIES_COLORS,
  SERIES_COLORS_GOLD,
  SERIES_COLORS_GREEN,
  ELIMINATED_SERIES_COLOR as ELIMINATED_COLOR,
  COMBINED_SERIES_COLOR as COMBINED_COLOR,
} from "@/lib/seriesColors";

// Series palettes live in the shared registry (L2-157, census class E). This
// kernel is the flagship series surface, so its palette is the canonical one.
const DEFAULT_COLORS = SERIES_COLORS;
const GOLD_COLORS = SERIES_COLORS_GOLD;
const GREEN_COLORS = SERIES_COLORS_GREEN;

interface FuturesChartProps {
  historyData: FuturesOutcomeHistory[];
  selectedOutcomes?: Set<number>;
  onToggleOutcome?: (id: number) => void;
  mini?: boolean;
  height?: number;
  showLegend?: boolean;
  showAxes?: boolean;
  goldTheme?: boolean;
  greenTheme?: boolean;
  className?: string;
  /** Use step interpolation (hold value until next point) for sparse data */
  stepInterpolation?: boolean;
  /** Pin the y-axis to a fixed 0–100% domain (#883 blend-line principle: the
   *  futures/field chart never rescales to the data max — movement stays honestly
   *  proportional and charts stay comparable). L2-149 made this the NON-OPTIONAL
   *  default for the consolidated field kernel: it is opt-OUT (`fixedYAxis={false}`),
   *  not opt-in. Auto-scaling is only for the rare surface that deliberately wants
   *  it. */
  fixedYAxis?: boolean;
  /** L2-135: vertical state markers giving the time axis a real sense of time —
   *  golf round boundaries (R1/R2/R3/R4), the settled-page state-marker language
   *  applied to the evolution chart. Each marker is a dashed line + top label,
   *  clipped to the chart's visible [minTime, maxTime] window. Opt-in: undefined
   *  = no markers (every non-golf surface is unaffected). Times are epoch ms. */
  timeMarkers?: { time: number; label: string }[];
  /** L2-149: per-outcome color override keyed by outcome_id. When supplied it wins
   *  over the index palette, so a caller can keep a chart's line colors in sync
   *  with an external leaderboard (EvolutionView) or with team/source colors.
   *  Outcomes absent from the map fall back to the index palette (or the
   *  eliminated grey). */
  outcomeColors?: Map<number, string>;
  /** L2-149: the currently highlighted outcome (driven by an external leaderboard
   *  hover, or by chart hover via `onHoverOutcome`). Its line is emphasized and
   *  every other line dims — the focus interaction migrated from EvolutionChart.
   *  `null`/undefined = no highlight (all lines at normal weight). */
  highlightedOutcomeId?: number | null;
  /** L2-149: fired with the top outcome under the cursor (or null on leave) so an
   *  external leaderboard can highlight in sync. Non-mini only. */
  onHoverOutcome?: (outcomeId: number | null) => void;
  /** L2-149: draw the summed probability of the displayed outcomes as a single
   *  dashed line (the "Combined" toggle migrated from EvolutionChart). Only shown
   *  when more than one outcome is displayed. */
  showCombinedProbability?: boolean;
  /** L2-164: opt-in tap-to-zoom chip for long-horizon low-probability series
   *  (season journeys). The fixed 0–100% axis stays the DEFAULT so movement is
   *  never silently exaggerated; the chip lets the user deliberately zoom to a
   *  rounded bound computed from the series max ("Zoom 0–20%"), clearly labeled,
   *  and tap again to snap back to full scale. Only offered when the series max is
   *  low enough that the fixed axis leaves real dead space; non-mini only, so
   *  sparklines never get the affordance. Every other caller is unaffected
   *  (default off). */
  allowZoom?: boolean;
}

export function FuturesChart({
  historyData,
  selectedOutcomes,
  onToggleOutcome,
  mini = false,
  height,
  showLegend,
  showAxes,
  goldTheme = false,
  greenTheme = false,
  className,
  stepInterpolation = false,
  fixedYAxis = true,
  timeMarkers,
  outcomeColors,
  highlightedOutcomeId,
  onHoverOutcome,
  showCombinedProbability = false,
  allowZoom = false,
}: FuturesChartProps) {
  const effectiveShowLegend = showLegend ?? !mini;
  const effectiveShowAxes = showAxes ?? !mini;
  const palette = greenTheme ? GREEN_COLORS : goldTheme ? GOLD_COLORS : DEFAULT_COLORS;

  // Filter to selected outcomes, or show top 5 if none selected
  const displayedOutcomes = useMemo(() => {
    if (selectedOutcomes && selectedOutcomes.size > 0) {
      return historyData.filter((o) => selectedOutcomes.has(o.outcome_id));
    }
    return historyData.slice(0, 5);
  }, [historyData, selectedOutcomes]);

  // Resolve a line color: explicit per-outcome override > eliminated grey >
  // index palette. Centralized so lines, hover dots and the legend never drift.
  const colorFor = (outcome: FuturesOutcomeHistory, idx: number): string => {
    const override = outcomeColors?.get(outcome.outcome_id);
    if (override) return override;
    if (outcome.eliminated) return ELIMINATED_COLOR;
    return palette[idx % palette.length];
  };

  // Hover tooltip state (non-mini only) — must be before any early returns
  const [hoverInfo, setHoverInfo] = useState<{
    svgX: number;
    time: number;
    values: { outcomeId: number; name: string; prob: number; color: string }[];
  } | null>(null);

  // L2-164: zoom state for the opt-in low-prob zoom chip — also before any
  // early returns so the hooks order is stable.
  const [zoomed, setZoomed] = useState(false);

  if (displayedOutcomes.length === 0) {
    if (mini) return null;
    return (
      <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
        Select outcomes below to see their probability trends
      </div>
    );
  }

  // Find time range and probability range
  let minTime = Infinity;
  let maxTime = -Infinity;
  let maxProb = 0;

  for (const outcome of displayedOutcomes) {
    for (const point of outcome.history) {
      const time = new Date(point.timestamp).getTime();
      if (time < minTime) minTime = time;
      if (time > maxTime) maxTime = time;
      if (point.probability !== null && point.probability > maxProb) {
        maxProb = point.probability;
      }
    }
  }

  // Check total data points across all displayed outcomes
  const totalPoints = displayedOutcomes.reduce(
    (sum, o) => sum + o.history.filter((p) => p.probability !== null).length,
    0
  );

  if (minTime === Infinity || maxTime === -Infinity || maxTime === minTime || totalPoints < 2) {
    if (mini) return null;
    return (
      <div className="h-32 flex flex-col items-center justify-center gap-2 text-sm text-text-secondary">
        <svg className="w-5 h-5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <span>Limited price history available</span>
        <span className="text-xs text-text-muted">
          Prices update every 1{"–"}2 hours for this market
        </span>
      </div>
    );
  }

  // L2-164: the raw series max (before any axis pinning) drives the zoom chip.
  const dataMax = maxProb;
  const zoomBound = computeZoomBound(dataMax);
  const canZoom = canZoomSeries(dataMax, allowZoom, mini);
  const isZoomed = canZoom && zoomed;
  maxProb = resolveYAxisMax({ dataMax, fixedYAxis, zoomed, allowZoom, mini });

  const chartWidth = mini ? 400 : 800;
  const effectiveHeight = height ?? (mini ? 80 : 200);
  const padding = mini
    ? { top: 4, right: 4, bottom: 4, left: 4 }
    : { top: 20, right: 20, bottom: 40, left: 50 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = effectiveHeight - padding.top - padding.bottom;

  const xScale = (time: number) =>
    padding.left + ((time - minTime) / (maxTime - minTime)) * innerWidth;

  const yScale = (prob: number) =>
    padding.top + (1 - prob / maxProb) * innerHeight;

  // L2-149: combined probability line — the forward-filled sum of the displayed
  // outcomes across the union of their timestamps, capped at 100%. Only meaningful
  // for more than one outcome. Migrated from EvolutionChart's "Combined" toggle.
  // NOTE: a plain computation (not a hook) — it lives below the early returns, so
  // a useMemo here would break the rules of hooks. The loop is O(points) and cheap.
  const combinedPoints: { t: number; sum: number }[] | null = (() => {
    if (!showCombinedProbability || displayedOutcomes.length < 2) return null;
    const stamps = new Set<number>();
    for (const o of displayedOutcomes) {
      for (const p of o.history) {
        if (p.probability !== null) stamps.add(new Date(p.timestamp).getTime());
      }
    }
    const sortedStamps = Array.from(stamps).sort((a, b) => a - b);
    if (sortedStamps.length < 2) return null;
    // Pre-sort each outcome's real points once for a linear forward-fill walk.
    const series = displayedOutcomes.map((o) =>
      o.history
        .filter((p) => p.probability !== null)
        .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.probability as number }))
        .sort((a, b) => a.t - b.t)
    );
    const cursors = series.map(() => 0);
    const last = series.map(() => null as number | null);
    const pts: { t: number; sum: number }[] = [];
    for (const t of sortedStamps) {
      let sum = 0;
      let anyKnown = false;
      series.forEach((pointsList, i) => {
        while (cursors[i] < pointsList.length && pointsList[cursors[i]].t <= t) {
          last[i] = pointsList[cursors[i]].v;
          cursors[i] += 1;
        }
        if (last[i] !== null) {
          sum += last[i] as number;
          anyKnown = true;
        }
      });
      if (anyKnown) pts.push({ t, sum: Math.min(1, sum) });
    }
    return pts.length >= 2 ? pts : null;
  })();

  // Hover handler for interactive tooltip
  function handleChartHover(e: React.MouseEvent<SVGSVGElement>) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * chartWidth;
    if (svgX < padding.left || svgX > chartWidth - padding.right) {
      setHoverInfo(null);
      onHoverOutcome?.(null);
      return;
    }
    const time =
      minTime + ((svgX - padding.left) / innerWidth) * (maxTime - minTime);
    const values = displayedOutcomes
      .map((outcome, idx) => {
        let best: number | null = null;
        let bestDist = Infinity;
        for (const pt of outcome.history) {
          if (pt.probability === null) continue;
          const d = Math.abs(new Date(pt.timestamp).getTime() - time);
          if (d < bestDist) {
            bestDist = d;
            best = pt.probability;
          }
        }
        return best !== null
          ? {
              outcomeId: outcome.outcome_id,
              name: outcome.name,
              prob: best,
              color: colorFor(outcome, idx),
            }
          : null;
      })
      .filter((v): v is NonNullable<typeof v> => v !== null)
      .sort((a, b) => b.prob - a.prob);
    setHoverInfo({ svgX, time, values });
    // Keep an external leaderboard highlighted on the top line under the cursor.
    onHoverOutcome?.(values.length > 0 ? values[0].outcomeId : null);
  }

  function handleChartLeave() {
    setHoverInfo(null);
    onHoverOutcome?.(null);
  }

  function formatTooltipTime(ts: number): string {
    const d = new Date(ts);
    const range = maxTime - minTime;
    if (range < 24 * 60 * 60 * 1000) {
      return d.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
      });
    }
    return (
      d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
      " " +
      d.toLocaleTimeString("en-US", { hour: "numeric" })
    );
  }

  return (
    <div className={`${mini ? "" : "space-y-4"} ${className ?? ""}`}>
      <div className={mini ? "" : "overflow-x-auto relative"}>
        {/* L2-164: tap-to-zoom chip. Fixed 0–100% is the default; the chip lets
            the user opt into a rounded low-prob zoom and snap back. Absolutely
            positioned so it never shifts the chart layout. */}
        {canZoom && (
          <button
            type="button"
            onClick={() => setZoomed((z) => !z)}
            aria-pressed={isZoomed}
            className="absolute top-0 right-0 z-20 rounded-full border border-surface-border bg-surface-card/90 px-2 py-0.5 text-[10px] font-semibold text-text-secondary backdrop-blur-sm transition-colors hover:text-text-primary"
          >
            {isZoomed ? "Full 0–100%" : `Zoom 0–${Math.round(zoomBound * 100)}%`}
          </button>
        )}
        <svg
          viewBox={`0 0 ${chartWidth} ${effectiveHeight}`}
          className={mini ? "w-full" : "w-full min-w-[600px]"}
          style={{
            // Honor the caller's requested height (L2-149): the old hard 250px
            // non-mini cap silently shrank taller surfaces (event-concept charts
            // ask for 260–280; EvolutionView asks for 300, or 600 fullscreen).
            maxHeight: `${effectiveHeight}px`,
            cursor: mini ? undefined : "crosshair",
          }}
          onMouseMove={mini ? undefined : handleChartHover}
          onMouseLeave={mini ? undefined : handleChartLeave}
        >
          {/* Y-axis grid lines */}
          {effectiveShowAxes &&
            [0, 0.25, 0.5, 0.75, 1].map((pct) => (
              <g key={pct}>
                <line
                  x1={padding.left}
                  y1={yScale(maxProb * pct)}
                  x2={chartWidth - padding.right}
                  y2={yScale(maxProb * pct)}
                  stroke="#e5e7eb"
                  strokeDasharray="4"
                />
                <text
                  x={padding.left - 8}
                  y={yScale(maxProb * pct)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="text-xs fill-slate"
                >
                  {Math.round(maxProb * pct * 100)}%
                </text>
              </g>
            ))}

          {/* X-axis time labels */}
          {effectiveShowAxes &&
            (() => {
              const timeRange = maxTime - minTime;
              const tickCount = Math.min(
                5,
                Math.max(2, Math.floor(innerWidth / 150))
              );
              const ticks: number[] = [];
              for (let i = 0; i <= tickCount; i++) {
                ticks.push(minTime + (timeRange * i) / tickCount);
              }

              const formatTime = (ts: number) => {
                const d = new Date(ts);
                if (timeRange < 24 * 60 * 60 * 1000) {
                  return d.toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                  });
                } else if (timeRange < 7 * 24 * 60 * 60 * 1000) {
                  return (
                    d.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    }) +
                    " " +
                    d.toLocaleTimeString("en-US", { hour: "numeric" })
                  );
                } else {
                  return d.toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  });
                }
              };

              return ticks.map((t, i) => (
                <g key={`x-${i}`}>
                  <line
                    x1={xScale(t)}
                    y1={padding.top + innerHeight}
                    x2={xScale(t)}
                    y2={padding.top + innerHeight + 4}
                    stroke="#94a3b8"
                  />
                  <text
                    x={xScale(t)}
                    y={padding.top + innerHeight + 16}
                    textAnchor="middle"
                    className="text-xs fill-slate"
                    style={{ fontSize: "9px" }}
                  >
                    {formatTime(t)}
                  </text>
                </g>
              ));
            })()}

          {/* L2-135: round/state boundary markers — dashed verticals + top labels
              (R1/R2/R3/R4) giving the axis a real sense of time. Clipped to the
              visible window; skipped in mini mode. */}
          {!mini &&
            effectiveShowAxes &&
            timeMarkers?.map((m, i) =>
              m.time < minTime || m.time > maxTime ? null : (
                <g key={`marker-${i}`}>
                  <line
                    x1={xScale(m.time)}
                    y1={padding.top}
                    x2={xScale(m.time)}
                    y2={padding.top + innerHeight}
                    stroke="#cbd5e1"
                    strokeDasharray="4 3"
                    strokeWidth={1}
                  />
                  <text
                    x={xScale(m.time) + 3}
                    y={padding.top + 10}
                    textAnchor="start"
                    className="fill-slate"
                    style={{ fontSize: "9px", fontWeight: 600 }}
                  >
                    {m.label}
                  </text>
                </g>
              ),
            )}

          {/* Lines */}
          {displayedOutcomes.map((outcome, idx) => {
            const points = outcome.history
              .filter((p) => p.probability !== null)
              .map((p) => ({
                x: xScale(new Date(p.timestamp).getTime()),
                y: yScale(p.probability!),
              }));

            if (points.length < 2) return null;

            const pathD = stepInterpolation
              ? points
                  .map((p, i) =>
                    i === 0
                      ? `M ${p.x} ${p.y}`
                      : `H ${p.x} V ${p.y}`
                  )
                  .join(" ")
              : points
                  .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
                  .join(" ");

            // L2-149: highlight/eliminated line weighting. When one outcome is
            // highlighted (leaderboard or chart hover), it thickens and the rest
            // dim; eliminated contenders draw thin + dashed + faded for context.
            const elim = !!outcome.eliminated;
            const isFocus = highlightedOutcomeId === outcome.outcome_id;
            const isDimmed =
              highlightedOutcomeId != null && highlightedOutcomeId !== outcome.outcome_id;
            const strokeWidth = mini
              ? 1.5
              : isFocus
                ? 2.75
                : isDimmed
                  ? 1
                  : elim
                    ? 1.25
                    : 2;
            const strokeOpacity = isDimmed ? 0.2 : elim ? 0.4 : 1;

            return (
              <path
                key={outcome.outcome_id}
                d={pathD}
                fill="none"
                stroke={colorFor(outcome, idx)}
                strokeWidth={strokeWidth}
                strokeOpacity={strokeOpacity}
                strokeDasharray={elim ? "4 3" : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}

          {/* L2-149: combined (summed) probability line — dashed, dark, drawn on
              top so the aggregate reads clearly against the contender lines. */}
          {!mini && combinedPoints && (
            <path
              d={combinedPoints
                .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.t)} ${yScale(p.sum)}`)
                .join(" ")}
              fill="none"
              stroke={COMBINED_COLOR}
              strokeWidth={2.2}
              strokeOpacity={highlightedOutcomeId != null ? 0.45 : 0.9}
              strokeDasharray="7 4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Hover crosshair and dots */}
          {hoverInfo && !mini && (
            <>
              <line
                x1={hoverInfo.svgX}
                y1={padding.top}
                x2={hoverInfo.svgX}
                y2={padding.top + innerHeight}
                stroke={greenTheme ? "#006747" : goldTheme ? "#D4AF37" : "#94a3b8"}
                strokeWidth={1}
                strokeDasharray="4 2"
                opacity={0.6}
              />
              {hoverInfo.values.map((v, i) => (
                <circle
                  key={i}
                  cx={hoverInfo.svgX}
                  cy={yScale(v.prob)}
                  r={4}
                  fill={v.color}
                  stroke={greenTheme ? "#e6f7ef" : goldTheme ? "#fef9e7" : "#FFFFFF"}
                  strokeWidth={2}
                />
              ))}
            </>
          )}
        </svg>

        {/* Hover tooltip */}
        {hoverInfo && !mini && (
          <div
            className="absolute pointer-events-none z-50"
            style={{
              left: `${(hoverInfo.svgX / chartWidth) * 100}%`,
              top: 0,
              transform:
                hoverInfo.svgX > chartWidth * 0.6
                  ? "translateX(-105%)"
                  : "translateX(5%)",
            }}
          >
            <div className="bg-surface-deep/95 backdrop-blur-sm rounded-lg px-3 py-2 border border-surface-border shadow-lg min-w-[140px]">
              <div className="text-[10px] text-text-muted mb-1 font-mono">
                {formatTooltipTime(hoverInfo.time)}
              </div>
              {hoverInfo.values.map((v, i) => (
                <div key={i} className="flex items-center gap-2 py-0.5">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: v.color }}
                  />
                  <span className="text-[11px] text-text-secondary truncate max-w-[120px]">
                    {v.name}
                  </span>
                  <span className="text-[11px] font-mono font-bold text-text-primary ml-auto pl-2">
                    {Math.round(v.prob * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Legend — interactive (toggle) when a handler is supplied, otherwise a
          static key so single-question charts (e.g. the settled Path to
          resolution) still say which colored line is which contender. The
          flex-wrap layout is the collision-safe alternative to end-of-line
          labels, which pile up when contenders converge (#L2-137). */}
      {effectiveShowLegend && onToggleOutcome && (
        <div className="flex flex-wrap gap-3">
          {displayedOutcomes.map((outcome, idx) => (
            <button
              key={outcome.outcome_id}
              onClick={() => onToggleOutcome(outcome.outcome_id)}
              className="flex items-center gap-2 text-sm hover:opacity-80 transition-opacity"
            >
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: colorFor(outcome, idx) }}
              />
              <span className="text-text-primary">{outcome.name}</span>
            </button>
          ))}
        </div>
      )}
      {effectiveShowLegend && !onToggleOutcome && (
        <div className="flex flex-wrap gap-x-3 gap-y-1.5" aria-label="Chart legend">
          {displayedOutcomes.map((outcome, idx) => (
            <span
              key={outcome.outcome_id}
              className="flex items-center gap-2 text-sm"
            >
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: colorFor(outcome, idx) }}
              />
              <span className="text-text-primary truncate max-w-[160px]">{outcome.name}</span>
            </span>
          ))}
        </div>
      )}

      {effectiveShowLegend &&
        selectedOutcomes &&
        selectedOutcomes.size === 0 && (
          <p className="text-xs text-text-secondary text-center">
            Showing top 5 outcomes. Check boxes below to compare specific
            outcomes.
          </p>
        )}
    </div>
  );
}
