"use client";

import React, { useMemo, useState } from "react";

import {
  CHART_SERIES_COUNT,
  TIMEFRAMES,
  chartGeometry,
  chartSeries,
  legendName,
  pointsInTimeframe,
  seriesEndpoint,
  seriesPoints,
  timeframeIsDrawable,
  type Timeframe,
} from "@/lib/contenderChart";
import { formatBoardProbability, type TournamentRow } from "@/lib/tournament";

/**
 * Legend + three-line trend chart, atop the contender list (UX-P132 re-skin).
 *
 * Structure from Alex's Kalshi reference: legend of the top three with a
 * coloured dot and each one's current probability, three matching lines with
 * endpoint dots, timeframe selector bottom-right.
 *
 * What is deliberately NOT copied: the reference's two-sided green/red price
 * pills. That is a trading format. Our rows print one blended probability per
 * contender, probabilities only — standing doctrine, and the whole reason this
 * product exists.
 *
 * The honesty rule carries over from the boards unchanged: a chart drawn from
 * non-live prices is muted and says so. #2199 has these fields dark for 8-32
 * days, so today this is the common path, not the edge case.
 */

const WIDTH = 320;
const HEIGHT = 96;

export default function ContenderChart({
  rows,
  draw,
}: {
  rows: TournamentRow[];
  draw: string;
}) {
  const series = useMemo(() => chartSeries(rows, CHART_SERIES_COUNT), [rows]);

  // Default to the widest window. With the fields price-dark, the narrow
  // windows are the empty ones, so opening on 1D would show a blank chart for a
  // market that has a month of real history.
  const [timeframe, setTimeframe] = useState<Timeframe>("ALL");

  const geometry = useMemo(
    () => chartGeometry(series, timeframe, WIDTH, HEIGHT),
    [series, timeframe]
  );

  if (series.length === 0) return null;

  const drawable = series.some(
    (entry) => pointsInTimeframe(entry.points, timeframe).length >= 2
  );
  const anyLive = series.some((entry) => entry.isLive);

  return (
    <section
      className="mt-4 rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3"
      data-testid="contender-chart"
      data-draw={draw}
      data-timeframe={timeframe}
      data-live={anyLive ? "true" : "false"}
    >
      <ul className="mb-2" data-testid="chart-legend">
        {series.map((entry) => (
          <li
            key={entry.entityKey}
            className="flex items-center gap-2 py-0.5"
            data-testid="chart-legend-item"
            data-entity={entry.entityKey}
          >
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="min-w-0 flex-1 truncate text-[12.5px] uppercase tracking-[0.04em] text-text-secondary">
              {legendName(entry.displayName)}
            </span>
            <span
              className={`text-[13px] font-bold tabular-nums ${
                entry.isLive ? "text-text-primary" : "text-text-secondary"
              }`}
              data-testid="chart-legend-probability"
            >
              {formatBoardProbability(entry.probability)}
            </span>
          </li>
        ))}
      </ul>

      {drawable ? (
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block h-24 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Probability history for the top ${series.length} contenders`}
          data-testid="chart-svg"
        >
          {series.map((entry) => {
            const points = seriesPoints(entry, geometry, timeframe);
            if (points === "") return null;
            const endpoint = seriesEndpoint(entry, geometry, timeframe);
            return (
              <g key={entry.entityKey} data-testid="chart-series" data-entity={entry.entityKey}>
                <polyline
                  points={points}
                  fill="none"
                  stroke={entry.color}
                  strokeWidth={1.75}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  opacity={anyLive ? 1 : 0.45}
                  vectorEffect="non-scaling-stroke"
                />
                {endpoint && (
                  <circle
                    cx={endpoint.x}
                    cy={endpoint.y}
                    r={3}
                    fill={entry.color}
                    opacity={anyLive ? 1 : 0.45}
                    data-testid="chart-endpoint"
                  />
                )}
              </g>
            );
          })}
        </svg>
      ) : (
        <div
          className="flex h-24 items-center justify-center text-[12px] text-text-muted"
          data-testid="chart-empty"
        >
          Not enough readings in this window to draw a line.
        </div>
      )}

      <div className="mt-1.5 flex items-center justify-between">
        <span className="text-[11px] text-text-muted">
          {series.length} of {rows.length}
        </span>
        <div className="flex gap-1" role="group" aria-label="Chart timeframe">
          {TIMEFRAMES.map((option) => {
            const enabled = timeframeIsDrawable(series, option);
            const active = option === timeframe;
            return (
              <button
                key={option}
                type="button"
                disabled={!enabled}
                aria-pressed={active}
                onClick={() => setTimeframe(option)}
                data-testid="chart-timeframe"
                data-option={option}
                data-active={active ? "true" : "false"}
                className={`rounded px-1.5 py-0.5 text-[11px] tabular-nums ${
                  active
                    ? "font-bold text-text-primary"
                    : enabled
                      ? "text-text-secondary"
                      : "cursor-not-allowed text-text-muted opacity-40"
                }`}
              >
                {option}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
