"use client";

import React, { useMemo, useState } from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  MAX_SERIES_COUNT,
  TIMEFRAMES,
  chartGeometry,
  chartSeriesFor,
  chartableRows,
  filterCandidates,
  legendName,
  pointsInTimeframe,
  selectionIsDefault,
  seriesEndpoint,
  seriesPoints,
  timeframeIsDrawable,
  type Timeframe,
} from "@/lib/contenderChart";
import { TITLE_COLUMN_LABEL } from "@/lib/bracket";
import { formatBoardProbability, type TournamentRow } from "@/lib/tournament";

/**
 * Legend + trend chart, now the FIRST thing under the pills (UX-P132 re-skin,
 * re-placed and given a picker by UX-P137, Alex's ruling 6).
 *
 * Structure from Alex's Kalshi reference: legend with a coloured dot and each
 * contender's current probability, matching lines with endpoint dots,
 * timeframe selector bottom-right.
 *
 * WHAT UX-P137 CHANGED, and why:
 *
 * - **It moved up.** It used to live inside `TournamentBoard`, which sits
 *   below the day's matches — so on a full match day the chart was thirty rows
 *   down a phone screen. The title race is the page's subject; it now opens on
 *   it. The component is unchanged by the move, which is the point of it
 *   having been a component.
 *
 * - **The legend is a picker**, DataGolf's handling as the reference: tap a
 *   legend row to drop that line, tap `Add players` to open the rest of the
 *   field and add one. Default stays the top three. The selection is owned by
 *   the page rather than by this component, because the board's name-underline
 *   colour tie-in has to follow the same choice — two components disagreeing
 *   about which three players are "the" three would be worse than no tie-in.
 *
 * WHAT UX-P138 CHANGED (Alex's ruling 5: "is it as good as DataGolf's picker?
 * If not, close the gap"). The honest answer was no, in three specific ways,
 * and the report gives the full comparison. Two are closed here:
 *
 * - **A filter.** DataGolf filters as you type. Ours made you expand a list of
 *   41 names and scan it. On a 44-player field that is a directory, not a
 *   picker. `filterCandidates` folds accents, because `Sørensen` and `Dvořák`
 *   are exactly the names a reader types unaccented.
 * - **A way back.** DataGolf has clear-all; ours had no route to the default
 *   short of removing lines one at a time and re-adding the three you started
 *   with. `Reset to top 3`, offered only when the selection has actually moved.
 *
 * The third gap is NOT closed and is not a gap this lane can close: DataGolf
 * shows a hover tooltip reading every line's value at a point in time, which
 * needs pointer state on an SVG this rig cannot render or screenshot. It is in
 * the report as owed work, not as a solved item.
 *
 * Standing doctrine still governs everything numeric — fixed 0-100 axis, no
 * smoothing, gaps stay gaps — and the honesty rule carries over: a chart drawn
 * from non-live prices is muted and says so.
 */

const WIDTH = 320;
const HEIGHT = 96;

export default function ContenderChart({
  rows,
  draw,
  selection,
  onToggle,
  onReset,
  initialPickerOpen = false,
  initialFilter = "",
}: {
  rows: TournamentRow[];
  draw: string;
  /** Entity keys currently drawn, in the order they were added. */
  selection: string[];
  onToggle: (entityKey: string) => void;
  /** Back to the board's top three (ruling 5). Omitted, no reset is offered. */
  onReset?: () => void;
  /** Capture seam: render with the picker already open. */
  initialPickerOpen?: boolean;
  /** Capture seam: render the picker already filtered — a static page cannot type. */
  initialFilter?: string;
}) {
  const series = useMemo(() => chartSeriesFor(rows, selection), [rows, selection]);

  // Default to the widest window. With the fields price-dark, the narrow
  // windows are the empty ones, so opening on 1D would show a blank chart for a
  // market that has a month of real history.
  const [timeframe, setTimeframe] = useState<Timeframe>("ALL");
  const [pickerOpen, setPickerOpen] = useState(initialPickerOpen);
  const [pickerExpanded, setPickerExpanded] = useState(false);
  const [filter, setFilter] = useState(initialFilter);

  const geometry = useMemo(
    () => chartGeometry(series, timeframe, WIDTH, HEIGHT),
    [series, timeframe]
  );

  const available = useMemo(
    () => chartableRows(rows).filter((row) => !selection.includes(row.entity_key)),
    [rows, selection]
  );

  /** Ruling 5's gap-closer: 41 names is a directory until you can type at it. */
  const candidates = useMemo(
    () => filterCandidates(available, filter),
    [available, filter]
  );

  const canReset = onReset !== undefined && !selectionIsDefault(rows, selection);

  if (series.length === 0) return null;

  const drawable = series.some(
    (entry) => pointsInTimeframe(entry.points, timeframe).length >= 2
  );
  const anyLive = series.some((entry) => entry.isLive);
  const atCeiling = series.length >= MAX_SERIES_COUNT;
  const pickerVisible = pickerExpanded
    ? candidates
    : candidates.slice(0, COLLAPSED_LIST_COUNT);

  return (
    <section
      className="mt-4 rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3"
      data-testid="contender-chart"
      data-draw={draw}
      data-timeframe={timeframe}
      data-live={anyLive ? "true" : "false"}
      data-selected={series.length}
    >
      {/* Ruling 2, applied here too: this column is the same title probability
          the board and the bracket print, and it was equally unlabelled. */}
      <div
        className="mb-1 flex items-center justify-between gap-2 text-[9.5px] font-bold uppercase tracking-[0.06em] text-text-muted"
        data-testid="chart-column-header"
      >
        <span>Contender</span>
        <span data-testid="chart-column-label">{TITLE_COLUMN_LABEL}</span>
      </div>

      <ul className="mb-2" data-testid="chart-legend">
        {series.map((entry) => (
          <li
            key={entry.entityKey}
            data-testid="chart-legend-item"
            data-entity={entry.entityKey}
          >
            <button
              type="button"
              onClick={() => onToggle(entry.entityKey)}
              aria-pressed
              aria-label={`Remove ${entry.displayName} from the chart`}
              className="flex w-full items-center gap-2 py-0.5 text-left"
              data-testid="chart-legend-toggle"
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
              <span aria-hidden="true" className="w-3 shrink-0 text-right text-[13px] text-text-muted">
                &times;
              </span>
            </button>
          </li>
        ))}
      </ul>

      {drawable ? (
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block h-24 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Probability history for ${series.length} contenders`}
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
          {canReset && (
            // RULING 5's second gap. DataGolf's picker has a clear-all; ours
            // had no way back to the default short of removing lines one at a
            // time and re-adding the three you started with. Only offered when
            // the selection has actually moved — an affordance that does
            // nothing is worse than an absent one.
            <>
              {" · "}
              <button
                type="button"
                onClick={onReset}
                className="font-semibold text-text-secondary underline decoration-dotted underline-offset-2"
                data-testid="chart-reset"
              >
                Reset to top 3
              </button>
            </>
          )}
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

      {available.length > 0 && (
        <div className="mt-2 border-t border-surface-border pt-2" data-testid="chart-picker">
          <button
            type="button"
            onClick={() => setPickerOpen((value) => !value)}
            aria-expanded={pickerOpen}
            disabled={atCeiling && !pickerOpen}
            className="w-full text-left text-[12px] font-semibold text-text-primary disabled:text-text-muted"
            data-testid="chart-picker-toggle"
            data-open={pickerOpen ? "true" : "false"}
          >
            {pickerOpen
              ? "Done adding"
              : atCeiling
                ? `Showing the most lines this chart draws (${MAX_SERIES_COUNT})`
                : `Add players (${available.length} more)`}
          </button>

          {pickerOpen && (
            <>
              {/* THE FILTER (ruling 5). The single biggest gap against
                  DataGolf: a 44-player field behind a five-then-expand list is
                  a directory, not a picker. Folds accents, matches anywhere in
                  the name — see `filterCandidates`. */}
              <input
                type="search"
                value={filter}
                onChange={(event) => {
                  setFilter(event.target.value);
                  setPickerExpanded(false);
                }}
                placeholder="Find a player"
                aria-label="Find a player to add to the chart"
                className="mt-1.5 w-full rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-[12.5px] text-text-primary placeholder:text-text-muted"
                data-testid="chart-picker-filter"
                data-value={filter}
              />
              {candidates.length === 0 && (
                <p
                  className="mt-1.5 text-[12px] text-text-muted"
                  data-testid="chart-picker-no-match"
                >
                  No contender in this draw matches &ldquo;{filter}&rdquo;.
                </p>
              )}
              <ul className="mt-1.5" data-testid="chart-picker-list">
              {pickerVisible.map((row) => (
                <li key={row.entity_key}>
                  <button
                    type="button"
                    onClick={() => onToggle(row.entity_key)}
                    disabled={atCeiling}
                    aria-pressed={false}
                    className="flex w-full items-center gap-2 py-1 text-left disabled:opacity-40"
                    data-testid="chart-picker-option"
                    data-entity={row.entity_key}
                  >
                    <span
                      aria-hidden="true"
                      className="h-2 w-2 shrink-0 rounded-full border border-surface-border"
                    />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-text-secondary">
                      {row.display_name}
                    </span>
                    <span className="text-[12.5px] tabular-nums text-text-muted">
                      {formatBoardProbability(row.probability)}
                    </span>
                  </button>
                </li>
              ))}
              {candidates.length > COLLAPSED_LIST_COUNT && (
                <li>
                  <ShowMore
                    expanded={pickerExpanded}
                    total={candidates.length}
                    onToggle={() => setPickerExpanded((value) => !value)}
                    bordered={false}
                  />
                </li>
              )}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
