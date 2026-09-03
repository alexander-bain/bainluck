"use client";

import React, { useMemo, useState } from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  MAX_SERIES_COUNT,
  NO_WINDOW_STARTS,
  RANGE_LABELS,
  axisSpanDays,
  axisTicks,
  axisWindow,
  chartGeometry,
  chartRanges,
  chartSeriesFor,
  chartYLabels,
  chartableRows,
  defaultChartRange,
  filterCandidates,
  isChartWindow,
  legendName,
  pointsInTimeframe,
  rangeDescription,
  rangeIsDrawable,
  rangeTimeframe,
  selectionIsDefault,
  seriesEndpoint,
  seriesForRange,
  seriesPoints,
  type AxisTickTier,
  type ChartRange,
  type WindowStarts,
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

/**
 * Where each tick tier starts being drawn (UX-P147, Alex's item 2: the axis is
 * "still oddly sparse").
 *
 * `axisTicks` emits one set of ticks for every width and tags each with the
 * narrowest plot its label fits in; this is the half that spends the tag. The
 * axis therefore gets denser as the window grows, from a single server render,
 * with no viewport measurement anywhere — see `axisTicks` for the step ladder
 * and the label pitch that decide how many labels each width earns.
 *
 * `block` rather than `inline` on the way back because these classes are shared
 * by an SVG `<line>` and an HTML `<span>`: SVG renders on any display value
 * that is not `none`, and the span is absolutely positioned, so `block` is
 * correct for both and `inline` would be wrong for neither-but-confusing.
 *
 * The BREAKPOINTS are the plot widths `lg:h-40` / `2xl:h-56` were measured
 * against on the same element, deliberately — one story about how wide this
 * chart is, not two.
 */
const TICK_TIER_VISIBILITY: Record<AxisTickTier, string> = {
  major: "",
  wide: "hidden lg:block",
  fine: "hidden 2xl:block",
};

/**
 * Half a `26 Aug` label as a fraction of the NARROWEST plot (~15 of 358px).
 *
 * A centred label needs this much room on each side or it hangs off the card.
 * UX-P207 made this a position test rather than an index test: the axis used to
 * place its first and last ticks ON the domain's ends, so "first in the array"
 * and "at the left edge" were the same thing. They are not any more — the grid
 * is anchored on the latest reading, so the leftmost tick can sit a little way
 * in and wants centring like any other. Keying the alignment off the index
 * would shove that label ~15px right of the rule it belongs to.
 */
const LABEL_HALF_FRACTION = 15 / 358;

export default function ContenderChart({
  rows,
  draw,
  selection,
  onToggle,
  onReset,
  windowStarts = NO_WINDOW_STARTS,
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
  /**
   * The days the main draw and qualifying began (ux/1034 A1), from
   * `tournamentWindowStarts`. Omitted — or `null` on either side — and that
   * chip is simply not offered, so a hub whose payload predates the field
   * renders the four duration buttons it always had.
   */
  windowStarts?: WindowStarts;
  /** Capture seam: render with the picker already open. */
  initialPickerOpen?: boolean;
  /** Capture seam: render the picker already filtered — a static page cannot type. */
  initialFilter?: string;
}) {
  const series = useMemo(() => chartSeriesFor(rows, selection), [rows, selection]);

  /**
   * `null` means "whatever the default is", NOT a range (ux/1034 A1).
   *
   * The same reason the page holds the contender selection as `null`: the
   * default is computed from the data, and pinning the computed value at first
   * render would freeze the chart on whatever was true when it mounted. On this
   * control that matters within one session — the draw pill swaps a 16-point
   * men's field for a 9-point women's one, and a `DRAW` window that was
   * drawable on the first is not guaranteed to be on the second.
   */
  const [range, setRange] = useState<ChartRange | null>(null);
  const [pickerOpen, setPickerOpen] = useState(initialPickerOpen);
  const [pickerExpanded, setPickerExpanded] = useState(false);
  const [filter, setFilter] = useState(initialFilter);

  const ranges = useMemo(() => chartRanges(windowStarts), [windowStarts]);
  const fallbackRange = useMemo(
    () => defaultChartRange(series, windowStarts),
    [series, windowStarts]
  );
  /* A chosen range the current payload no longer offers falls back rather than
     drawing nothing — `QUAL` survives a draw change, an empty results section
     across a refetch does not. */
  const activeRange =
    range !== null && ranges.includes(range) ? range : fallbackRange;

  /* THE WINDOW IS A SMALLER SERIES (see `seriesFromDate`). Everything below
     this line is the chart exactly as it was, drawing `ALL` of whatever it is
     handed — no part of the geometry, the axis or the picker learns that a
     tournament has a start date. */
  const drawnSeries = useMemo(
    () => seriesForRange(series, activeRange, windowStarts),
    [series, activeRange, windowStarts]
  );
  const timeframe = rangeTimeframe(activeRange);

  const geometry = useMemo(
    () => chartGeometry(drawnSeries, timeframe, WIDTH, HEIGHT),
    [drawnSeries, timeframe]
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

  const drawable = drawnSeries.some(
    (entry) => pointsInTimeframe(entry.points, timeframe).length >= 2
  );
  // RULING 6 (UX-P139) gave the x-axis its ticks: it had nothing at all, so a
  // falling line could be a day or a month and the reader had no way to tell.
  //
  // The note here used to claim the y-axis was "a labelled, fixed 0-100". It
  // was fixed and it was never labelled — #2451 is Alex finding exactly that on
  // the live page, and the comment had been asserting the opposite since the
  // chart shipped. Both halves are true now, and both are guarded.
  const ticks = axisTicks(geometry, timeframe);
  /* #2451: the y-axis's three rules and their labels, top first. */
  const yLabels = chartYLabels(geometry.ceiling);
  const spanDays = axisSpanDays(geometry);
  // NOT named `window` — this is a client component and shadowing the global
  // inside a render body is a trap for whoever adds a `window.matchMedia` here.
  const axisRange = axisWindow(geometry);
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
      data-range={activeRange}
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
        <>
        {/* ═══ THE PLOT AND ITS Y-AXIS (#2451) ═══

            Alex: the three lines sit "inside roughly the bottom 15% of the plot
            area, with no y-axis labels at all ... all visually flat and
            indistinguishable", and: "Fix the scale, do not smooth the line."

            Two changes, and they only work together. `chartCeiling` moves the
            TOP of the axis onto a coarse step above the leader (zero stays
            anchored — a truncated baseline is the chart lie and is not on the
            table), which on the men's board he was reading turns a leader
            drawn at 34% of the height into one drawn at 69%. And the axis is
            LABELLED, which is what makes a moving top honest rather than a
            second way to mislead: an unlabelled adaptive scale is strictly
            worse than an unlabelled fixed one.

            `relative` on the wrapper so the labels can sit over the plot; they
            are HTML positioned by percentage for the same reason the date
            labels are, which the `svg` comment below spells out — with
            `preserveAspectRatio="none"` any SVG text in here would be
            stretched by the x-scale. */}
        <div className="relative" data-testid="chart-plot">
        <div
          className="pointer-events-none absolute inset-0 z-10"
          aria-hidden="true"
          data-testid="chart-y-axis"
          data-ceiling={yLabels[0].probability}
        >
          {yLabels.map((entry) => {
            const fromTop = 1 - entry.probability / (yLabels[0].probability || 1);
            return (
              <span
                key={entry.label}
                className="absolute left-0 -translate-y-1/2 bg-surface-card/85 pr-1 text-[9.5px] font-semibold tabular-nums leading-none text-text-muted"
                style={{ top: `${(fromTop * 100).toFixed(2)}%` }}
                data-testid="chart-y-label"
                data-probability={entry.probability}
              >
                {entry.label}
              </span>
            );
          })}
        </div>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          /**
           * UX-P145: `h-24` (96px) is the phone's height, and on a phone the
           * plot is ~358px wide, so the drawn aspect is roughly 3.7:1. In the
           * desktop left column the same 96px sits under ~690px of width —
           * nearly 7:1 — and a title race flattens into a set of horizontal
           * lines that no longer show the thing the section exists to show.
           * `lg:h-40` (160px) restores the phone's proportions at desktop
           * width. Nothing else changes: `preserveAspectRatio="none"` means the
           * viewBox never needed to match the rendered box, and the axis labels
           * are HTML positioned by percentage for exactly that reason.
           *
           * UX-P146 adds the third step, because killing the page's 1280px
           * column moved the width this was measured against. The left track,
           * end to end, arithmetic rather than estimate:
           *
           *   `lg`  (1024px window) → 1024 − 48 site − 48 page − 32 gap,
           *                           ×1.35/2.35, − 28 card = ~486px plot
           *   `xl`  (1280px window) → same chain = ~627px
           *   `2xl` (1600px+, where `max-w-content` finally binds) = ~817px
           *
           * Against 160px those are 3.0:1, 3.9:1 and 5.1:1 — so the aspect was
           * fine where UX-P145 measured it and goes flat again past `xl`, which
           * is exactly the range the shell used to cut off. `2xl:h-56` (224px)
           * puts the widest case back at 3.6:1, next to the phone's 3.7.
           */
          className="block h-24 w-full lg:h-40 2xl:h-56"
          preserveAspectRatio="none"
          role="img"
          aria-label={
            spanDays !== null && axisRange !== null
              ? `Probability history for ${series.length} contenders over ${spanDays} days, ${axisRange.from} to ${axisRange.to}`
              : `Probability history for ${series.length} contenders`
          }
          data-testid="chart-svg"
        >
          {/* THE HORIZONTAL RULES (#2451), one per y label, so a reader can
              carry a line's height across to a number. Drawn before the
              vertical ticks and before every series, so nothing the chart is
              about is ever behind a rule. The zero rule is the one that says
              the baseline has not been cropped, and it is drawn a shade
              stronger for that reason. */}
          {yLabels.map((entry) => {
            const y = HEIGHT - (entry.probability / (yLabels[0].probability || 1)) * HEIGHT;
            const isZero = entry.probability === 0;
            return (
              <line
                key={`y-${entry.label}`}
                x1={0}
                x2={WIDTH}
                y1={y}
                y2={y}
                stroke="currentColor"
                strokeWidth={1}
                className="text-surface-border"
                opacity={isZero ? 0.9 : 0.5}
                vectorEffect="non-scaling-stroke"
                data-testid="chart-y-rule"
                data-probability={entry.probability}
              />
            );
          })}
          {/* THE TICKS, drawn first so a line is never behind a rule. Vertical
              only: `preserveAspectRatio="none"` scales x and y independently,
              so any TEXT in here would be stretched — the labels are HTML
              below, positioned by the same percentages. */}
          {ticks.map((tick) => (
            <line
              key={tick.date}
              x1={tick.x}
              x2={tick.x}
              y1={0}
              y2={HEIGHT}
              stroke="currentColor"
              strokeWidth={1}
              className={`text-surface-border ${TICK_TIER_VISIBILITY[tick.tier]}`}
              opacity={0.7}
              vectorEffect="non-scaling-stroke"
              data-testid="chart-axis-tick"
              data-date={tick.date}
              data-tier={tick.tier}
            />
          ))}
          {drawnSeries.map((entry) => {
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
        </div>
        {/* THE DATE LABELS. HTML rather than SVG text, and positioned by the
            same fraction of the width the tick uses, so they cannot drift from
            the rules they belong to. First is left-aligned and last is
            right-aligned against the plot edges; only the interior tick is
            centred, because a centred label at x=0 hangs off the card. */}
        <div
          className="relative mt-0.5 h-3.5 select-none"
          aria-hidden="true"
          data-testid="chart-axis"
          data-ticks={ticks.length}
        >
          {ticks.map((tick) => {
            const fraction = tick.x / WIDTH;
            return (
              <span
                key={tick.date}
                className={`absolute top-0 whitespace-nowrap text-[9.5px] tabular-nums text-text-muted ${
                  TICK_TIER_VISIBILITY[tick.tier]
                }`}
                data-tier={tick.tier}
                style={{
                  left: `${fraction * 100}%`,
                  // By POSITION, not by index — see LABEL_HALF_FRACTION.
                  transform:
                    fraction <= LABEL_HALF_FRACTION
                      ? "none"
                      : fraction >= 1 - LABEL_HALF_FRACTION
                        ? "translateX(-100%)"
                        : "translateX(-50%)",
                }}
                data-testid="chart-axis-label"
                data-date={tick.date}
              >
                {tick.label}
              </span>
            );
          })}
        </div>
        </>
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
          {/* How long the drawn window IS, not which button is pressed. `ALL`
              on a field with four readings is four days, and the button cannot
              say that. */}
          {spanDays !== null && (
            <span data-testid="chart-span"> · {spanDays}d shown</span>
          )}
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
        {/* THE RANGE CHIPS (ux/1034 A1). The two tournament windows first and
            the four durations after, because the windows are what the reader
            wants and the durations are what they fall back to — and because a
            control whose default is its fifth item reads as an afterthought.
            `tabular-nums` is dropped from the two word chips: it is there so
            `1D` and `1M` occupy the same box, and it does nothing for `Draw`
            except widen its spaces. */}
        <div className="flex gap-1" role="group" aria-label="Chart range">
          {ranges.map((option) => {
            const enabled = rangeIsDrawable(series, option, windowStarts);
            const active = option === activeRange;
            const description = rangeDescription(option, windowStarts);
            return (
              <button
                key={option}
                type="button"
                disabled={!enabled}
                aria-pressed={active}
                aria-label={description ?? undefined}
                title={description ?? undefined}
                onClick={() => setRange(option)}
                data-testid="chart-timeframe"
                data-option={option}
                data-active={active ? "true" : "false"}
                className={`rounded px-1.5 py-0.5 text-[11px] ${
                  isChartWindow(option) ? "" : "tabular-nums "
                }${
                  active
                    ? "font-bold text-text-primary"
                    : enabled
                      ? "text-text-secondary"
                      : "cursor-not-allowed text-text-muted opacity-40"
                }`}
              >
                {RANGE_LABELS[option]}
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
