"use client";

import React from "react";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import {
  ATLAS_STATE_COPY,
  formatAtlasTimestampPT,
} from "@/components/atlas/atlasStateCopy";
import type { SettlementResult } from "@/lib/chartSettlementPoints";

export interface AtlasChartReadingPoint {
  t: number;
  x: number;
  y: number;
  prob: number;
  timestamp: string;
}

export interface AtlasSelectedReading {
  outcomeId: number;
  outcomeName: string;
  probability: number;
  timestamp: string;
  x: number;
  y: number;
  color: string;
  isOpening: boolean;
}

/**
 * Upper bound on visible solid reading marks drawn in `solidMarkMode="all"` (#12615).
 * Standard basketball/football/hockey games have ~120–200 readings (`<= 300`, stride 1).
 * Multi-day or marathon events (cricket, golf, 5-set tennis) with > 300 readings thin
 * above this ceiling so the step line never smears into a solid bar of circles.
 */
export const ATLAS_ALL_MARKS_CEILING = 300;

/**
 * Shared mark-grammar legend for Atlas charts (#883 Step F3, #11974, #12615):
 * - Hollow = opening or pregame
 * - Solid = recorded reading (or sampled readings when thinned above `ATLAS_ALL_MARKS_CEILING`)
 * - Connector = change
 * - ✓ Won / ✗ Lost = result shown as a word, never a 100% point
 * - Any real reading tappable for its exact time in PT
 */
export function AtlasChartMarkKey({
  settled = false,
  showOpening = true,
  showRecordedReading = true,
  recordedReadingCount,
  openingLabel = "Opening",
}: {
  settled?: boolean;
  showOpening?: boolean;
  showRecordedReading?: boolean;
  recordedReadingCount?: number;
  openingLabel?: string;
}) {
  const thinnedAboveCeiling =
    typeof recordedReadingCount === "number" &&
    recordedReadingCount > ATLAS_ALL_MARKS_CEILING;

  return (
    <div
      data-testid="atlas-chart-mark-key"
      aria-label="Chart mark key"
      className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-text-secondary"
    >
      {showOpening && (
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-primary bg-surface-card"
          />
          <span>{openingLabel}</span>
        </span>
      )}
      {showRecordedReading && (
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-2.5 rounded-full bg-text-primary"
          />
          <span>
            {thinnedAboveCeiling
              ? `Recorded readings (sampled above ${ATLAS_ALL_MARKS_CEILING})`
              : "Recorded reading"}
          </span>
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-block h-0.5 w-3.5 rounded bg-text-primary"
        />
        <span>Change</span>
      </span>
      {settled && (
        <span
          data-testid="atlas-chart-key-result-word"
          className="inline-flex items-center gap-1.5 font-medium text-text-primary"
        >
          <span>{ATLAS_STATE_COPY.wonWithCheck}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-secondary">
            {ATLAS_STATE_COPY.lostWithCross}
          </span>
          <span className="font-normal text-text-secondary">
            Result as a word
          </span>
        </span>
      )}
      <span className="text-text-muted">
        Tap any reading for exact time (PT)
      </span>
    </div>
  );
}

/**
 * Renders the SVG mark grammar for one plotted series:
 * - First real observation (when `includesOpening` is true) -> hollow opening mark (`data-testid="atlas-chart-opening-mark"`)
 * - All other real observations -> solid recorded reading marks (`data-testid="atlas-chart-recorded-mark"`)
 * - Tappable hit target on every real observation (`data-testid="atlas-chart-reading-hit"`)
 *
 * When a series has many points (> 36), visual solid dots are thinned to keep
 * the step line readable while every real point remains tappable.
 */
export function AtlasSeriesReadingMarks({
  outcomeId,
  outcomeName,
  points,
  color,
  opacity = 1,
  includesOpening = true,
  solidMarkMode = "thinned",
  solidMarkRadius = 3,
  selectedReading,
  onSelectReading,
}: {
  outcomeId: number;
  outcomeName: string;
  points: AtlasChartReadingPoint[];
  color: string;
  opacity?: number;
  includesOpening?: boolean;
  solidMarkMode?: "thinned" | "all" | "none";
  solidMarkRadius?: number;
  selectedReading?: AtlasSelectedReading | null;
  onSelectReading?: (reading: AtlasSelectedReading) => void;
}) {
  if (points.length === 0) return null;

  const stride =
    solidMarkMode === "all"
      ? points.length <= ATLAS_ALL_MARKS_CEILING
        ? 1
        : Math.max(1, Math.ceil(points.length / ATLAS_ALL_MARKS_CEILING))
      : points.length <= 36
        ? 1
        : Math.max(1, Math.ceil(points.length / 28));

  const hitStride =
    points.length <= ATLAS_ALL_MARKS_CEILING
      ? 1
      : Math.max(1, Math.ceil(points.length / ATLAS_ALL_MARKS_CEILING));

  return (
    <g
      data-testid="atlas-series-marks"
      data-outcome-id={outcomeId}
    >
      {points.map((pt, index) => {
        const isOpening = includesOpening && index === 0;
        const isLast = index === points.length - 1;
        const isSelected =
          selectedReading?.outcomeId === outcomeId &&
          selectedReading?.timestamp === pt.timestamp;
        const showVisibleSolid =
          !isOpening &&
          (solidMarkMode === "none"
            ? isSelected
            : isLast || isSelected || index % stride === 0);
        const showHitTarget =
          isOpening || isLast || isSelected || index % hitStride === 0;

        if (!isOpening && !showVisibleSolid && !showHitTarget) {
          return null;
        }

        const exactPt =
          formatAtlasTimestampPT(pt.timestamp, { includeSeconds: true }) ??
          pt.timestamp;
        const pctLabel = formatProbabilityPercent(pt.prob);
        const ariaLabel = `${outcomeName}: ${
          isOpening ? "Opening reading" : "Recorded reading"
        } ${pctLabel} at ${exactPt}`;

        const handleSelect = (e: React.SyntheticEvent) => {
          e.stopPropagation();
          onSelectReading?.({
            outcomeId,
            outcomeName,
            probability: pt.prob,
            timestamp: pt.timestamp,
            x: pt.x,
            y: pt.y,
            color,
            isOpening,
          });
        };

        return (
          <g key={`${outcomeId}-${pt.timestamp}-${index}`}>
            {isOpening ? (
              <circle
                data-testid="atlas-chart-opening-mark"
                data-outcome-id={outcomeId}
                data-timestamp={pt.timestamp}
                cx={pt.x}
                cy={pt.y}
                r={isSelected ? 5 : 4}
                className="fill-surface-card"
                stroke={color}
                strokeWidth={isSelected ? 2.5 : 2}
                strokeOpacity={opacity}
              />
            ) : (
              showVisibleSolid && (
                <circle
                  data-testid="atlas-chart-recorded-mark"
                  data-outcome-id={outcomeId}
                  data-timestamp={pt.timestamp}
                  cx={pt.x}
                  cy={pt.y}
                  r={isSelected ? Math.max(4.5, solidMarkRadius + 1.5) : solidMarkRadius}
                  fill={color}
                  fillOpacity={opacity}
                  className={isSelected ? "stroke-surface-card" : undefined}
                  strokeWidth={isSelected ? 1.5 : undefined}
                />
              )
            )}

            {isSelected && (
              <circle
                data-testid="atlas-chart-selected-mark"
                cx={pt.x}
                cy={pt.y}
                r={7}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeOpacity={0.6}
              />
            )}

            <circle
              data-testid="atlas-chart-reading-hit"
              data-outcome-id={outcomeId}
              data-timestamp={pt.timestamp}
              data-opening={isOpening ? "true" : "false"}
              cx={pt.x}
              cy={pt.y}
              r={8}
              fill="transparent"
              role="button"
              tabIndex={0}
              aria-label={ariaLabel}
              style={{ cursor: "pointer" }}
              onClick={handleSelect}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleSelect(e);
                }
              }}
            />
          </g>
        );
      })}
    </g>
  );
}

/**
 * Renders the settled result word (`✓ Won` or `✗ Lost`, never a 100% point)
 * directly beside the series' result mark on the chart (`#883` Step F3).
 */
export function AtlasResultWordMark({
  outcomeId,
  result,
  x,
  y,
  plotLeft,
  plotRight,
  opacity = 1,
}: {
  outcomeId: number;
  result: SettlementResult;
  x: number;
  y: number;
  plotLeft: number;
  plotRight: number;
  opacity?: number;
}) {
  if (result !== "won" && result !== "lost") return null;
  const word =
    result === "won"
      ? ATLAS_STATE_COPY.wonWithCheck
      : ATLAS_STATE_COPY.lostWithCross;

  const placeLeft = x > plotRight - 56 && x - 48 > plotLeft;
  const labelX = placeLeft ? x - 9 : x + 9;
  const textAnchor = placeLeft ? "end" : "start";

  return (
    <text
      data-testid="atlas-chart-result-word"
      data-outcome-id={outcomeId}
      data-result={result}
      x={labelX}
      y={y + 3.5}
      textAnchor={textAnchor}
      opacity={opacity}
      className={
        result === "won"
          ? "fill-accent-live text-[10px] font-bold"
          : "fill-text-secondary text-[10px] font-semibold"
      }
    >
      {word}
    </text>
  );
}

/**
 * Displays the exact PT observation timestamp and server probability when a user
 * taps any real reading on the chart (`#883` Step F3).
 */
export function AtlasSelectedReadingReadout({
  reading,
  onClear,
}: {
  reading: AtlasSelectedReading | null;
  onClear?: () => void;
}) {
  if (!reading) return null;

  const exactTimePT =
    formatAtlasTimestampPT(reading.timestamp, { includeSeconds: true }) ??
    reading.timestamp;
  const pctText = formatProbabilityPercent(reading.probability);

  return (
    <div
      data-testid="atlas-chart-selected-reading"
      role="status"
      aria-live="polite"
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface-deep px-3 py-2 text-xs"
    >
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span
          aria-hidden="true"
          className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${
            reading.isOpening ? "bg-surface-card" : ""
          }`}
          style={
            reading.isOpening
              ? {
                  border: `2px solid ${reading.color}`,
                }
              : { backgroundColor: reading.color }
          }
        />
        <span className="font-semibold text-text-primary truncate">
          {reading.outcomeName}
        </span>
        <span className="rounded bg-surface-elevated px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
          {reading.isOpening ? "Opening" : "Recorded"}
        </span>
        <span
          data-testid="atlas-chart-selected-reading-prob"
          className="font-mono font-bold tabular-nums text-text-primary"
        >
          {pctText}
        </span>
        <span className="text-text-muted">·</span>
        <span
          data-testid="atlas-chart-selected-reading-time"
          className="font-mono text-text-secondary"
        >
          {exactTimePT}
        </span>
      </div>
      {onClear && (
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear selected reading"
          data-testid="atlas-chart-reading-clear"
          className="shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
        >
          Clear
        </button>
      )}
    </div>
  );
}
