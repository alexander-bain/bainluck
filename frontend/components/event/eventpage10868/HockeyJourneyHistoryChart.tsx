"use client";

/**
 * #10868 — the hockey journey's two-team win-probability history (web).
 *
 * Draws `HockeyJourneyHistory` exactly: each run is its own path and two runs
 * are never joined, so every unrecorded stretch stays blank; a run of one row
 * is a mark, never dropped; the last pregame row is hollow (none when the start
 * is not confirmed). No animation and no timer — the only effect measures the
 * plot's own width so lines, marks and labels are drawn at real pixels (no
 * stretched text at 375 px). Its one control, the Details disclosure, opens
 * the real notes list and is not offered when there are none. No Full chart or
 * Inspect control: neither has a destination on web yet.
 *
 * Compact, as the approved design draws it (`HockeyJourneyPage.tsx` +
 * `hockeyJourney.css`, prototype): under the plot one `.hj-line-key` row names
 * both teams (glyph + full name) with each team's own labelled readings — the
 * pregame slot, and the recorded slot only when the readout asks for it — and
 * a `.hj-history-basis` line carries the caption and mark key. These are the
 * line's own readings, labelled by the view model; nothing here is the
 * headline's current quote. Every reading's exact provenance (its clock words)
 * moves into the existing Details disclosure, beside the source notes. An
 * absent slot keeps its words; nothing shrinks to fit.
 *
 * Time axis (Design decision, 2026-10-30): the labels drawn are a measured,
 * text-size-aware SUBSET of the owner's ticks — first and last first, an
 * intermediate only when it fits with clear space — so enlarged text on a
 * phone reads two clear endpoints rather than a staircase. When even the two
 * endpoints cannot share a row, the last takes a second row (the minimal clear
 * placement); type never shrinks. Tick times, positions, guides and every
 * observation are unchanged.
 *
 * Period guide labels (FQ2, Design admission 2026-10-31): each label is measured
 * at its real size, like the time labels, and drawn where it always was — 3 px
 * right of its own guide line — whenever it fits inside the SVG and clears the
 * labels beside it. Only a label that would leave the SVG slides inward, as far
 * as the edge needs; only one that would then touch a neighbour takes a row
 * above, and the drawing grows by that row so the plot keeps its full height.
 * The guide line, every period, its words and its time never move or go; type
 * never shrinks (the 200% "Q3" that ran past the right edge, browser lab
 * c9bcdad25b).
 */

import { useId, useRef, useState } from "react";
import type {
  HockeyJourneyHistory,
  HockeyJourneyHistoryPoint,
  HockeyJourneyHistorySeries,
  HockeyJourneyReading,
} from "@/lib/eventPage10868/hockeyJourneyTypes";
import { DEFAULT_ROOT_FONT_PX, useFrameMeasure, useIsomorphicLayoutEffect } from "./useFrameMeasure";

const PLOT_HEIGHT = 230;
/** `text-xs` at the default root size. Axis text scales with the reader's root font. */
const AXIS_FONT_PX = 12;
/** Average advance of an axis glyph, in em — an estimate used only until the real text is measured. */
const GLYPH_EM = 0.62;
/** Clear space kept between two axis labels in one lane. */
const LABEL_GAP_PX = 6;

/** A label's width before it can be measured: its glyph count at the axis size. */
export function estimateLabelWidth(text: string, fontPx: number): number {
  return text.length * fontPx * GLYPH_EM;
}

export interface AxisLabelPlacement {
  /** Position of the drawn label's tick in the owner's `xTicks`. */
  index: number;
  /** Left edge, from the start of the plot. */
  start: number;
  /** 0 is the row nearest the plot; 1 only when the two endpoints cannot share a row. */
  lane: number;
}

/**
 * Which owner tick labels the axis draws, and where. Each label is centred on
 * its own tick and slid inward only as far as needed to stay inside `extent`
 * (the plot's width, so no x label can reach the y labels in the left margin).
 * The first and last ticks come first; an intermediate is drawn only when it
 * keeps `clearGap` from every label already drawn ("clearly fits"). When the
 * first and last cannot keep `gap` in one row, the last takes a second row and
 * no intermediate is drawn. A pure function of measured (or estimated) widths:
 * nothing is shortened, rewritten or moved off its tick beyond the slide.
 */
export function axisLabelSubset(
  centers: number[],
  lengths: number[],
  extent: number,
  gap: number,
  clearGap: number = gap,
): AxisLabelPlacement[] {
  const span = Math.max(0, Number.isFinite(extent) ? extent : 0);
  const count = Math.min(centers.length, lengths.length);
  if (count === 0) return [];
  const place = (index: number) => {
    const length = Math.min(Math.max(0, Number.isFinite(lengths[index]) ? lengths[index] : 0), span);
    const middle = Number.isFinite(centers[index]) ? centers[index] : 0;
    return { index, length, start: Math.min(Math.max(0, middle - length / 2), span - length) };
  };
  type Placed = ReturnType<typeof place>;
  const apart = (a: Placed, b: Placed, space: number) =>
    a.start + a.length + space <= b.start || b.start + b.length + space <= a.start;

  const first = place(0);
  if (count === 1) return [{ index: 0, start: first.start, lane: 0 }];
  const last = place(count - 1);
  if (!apart(first, last, Math.max(0, gap))) {
    return [
      { index: first.index, start: first.start, lane: 0 },
      { index: last.index, start: last.start, lane: 1 },
    ];
  }
  const shown: Placed[] = [first, last];
  const space = Math.max(0, gap, clearGap);
  for (let i = 1; i < count - 1; i += 1) {
    const candidate = place(i);
    if (shown.every((label) => apart(label, candidate, space))) shown.push(candidate);
  }
  return shown
    .sort((a, b) => a.index - b.index)
    .map((label) => ({ index: label.index, start: label.start, lane: 0 }));
}

export interface GuideLabelPlacement {
  /** Position of the label's guide among the period guides, in the owner's order. */
  index: number;
  /** Left edge of the label, in SVG coordinates. */
  start: number;
  /** 0 is the row just above the plot (every label's row before FQ2); 1, 2… only to clear a collision. */
  lane: number;
}

/**
 * Where each period guide's label is drawn. A label starts `pad` px right of its
 * own guide line — exactly where it always started — whenever it ends inside
 * `right` (the SVG's width) and clears, by `gap`, every label already placed in
 * its row. A label that would leave the SVG slides left only as far as the edge
 * needs, and never past `left` (the plot's left edge, so it cannot reach the y
 * labels). A label that would then touch a neighbour takes the next row up. A
 * pure function of measured (or estimated) widths: nothing is shortened,
 * renamed, resized, hidden or dropped, and the guide lines are not its concern.
 */
export function guideLabelPlacement(
  guideXs: number[],
  lengths: number[],
  left: number,
  right: number,
  gap: number,
  pad = 3,
): GuideLabelPlacement[] {
  const lo = Number.isFinite(left) ? left : 0;
  const hi = Math.max(lo, Number.isFinite(right) ? right : lo);
  const count = Math.min(guideXs.length, lengths.length);
  const placed: Array<GuideLabelPlacement & { length: number }> = [];
  for (let index = 0; index < count; index += 1) {
    const length = Math.max(0, Number.isFinite(lengths[index]) ? lengths[index] : 0);
    const own = (Number.isFinite(guideXs[index]) ? guideXs[index] : lo) + pad;
    // Inside the SVG: the own position when it fits, else slid in from the right edge, never past `left`.
    const start = own + length <= hi ? Math.max(lo, own) : Math.max(lo, hi - length);
    let lane = 0;
    while (placed.some((p) => p.lane === lane && start < p.start + p.length + gap && p.start < start + length + gap)) lane += 1;
    placed.push({ index, start, lane, length });
  }
  return placed.map(({ index, start, lane }) => ({ index, start, lane }));
}

export interface HockeyJourneyLineColors {
  home: string;
  away: string;
}

function Mark({
  x,
  y,
  shape,
  color,
  hollow,
}: {
  x: number;
  y: number;
  shape: "circle" | "square";
  color: string;
  hollow: boolean;
}) {
  const common = {
    style: { stroke: color, fill: hollow ? undefined : color },
    className: hollow ? "fill-surface-card" : undefined,
    strokeWidth: 2,
  };
  return shape === "circle" ? (
    <circle cx={x} cy={y} r={hollow ? 4.5 : 3.5} {...common} />
  ) : (
    <rect x={x - 3.5} y={y - 3.5} width={7} height={7} {...common} />
  );
}

/** One labelled reading in the line key: the label, then the figure or the slot's own absence words. */
function KeySlot({ label, reading }: { label: string; reading: HockeyJourneyReading }) {
  // An absent slot whose words are its label (no history response) prints them once.
  const once = reading.kind === "absent" && reading.words === label;
  return (
    <div className="flex min-w-0 flex-wrap items-baseline gap-x-1">
      <dt className={once ? "sr-only" : "text-text-secondary"}>{label}</dt>
      <dd className={reading.kind === "reading" ? "text-base font-bold tabular-nums text-text-primary" : "text-text-secondary"}>
        {reading.kind === "reading" ? reading.figure : reading.words}
      </dd>
    </div>
  );
}

export default function HockeyJourneyHistoryChart({
  history,
  colors,
}: {
  history: HockeyJourneyHistory;
  colors: HockeyJourneyLineColors;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const { width, rootFontPx } = useFrameMeasure(frame, 600);
  const titleId = useId();
  const detailsId = useId();
  const [detailsOpen, setDetailsOpen] = useState(false);

  // Axis text follows the reader's text size; so do the margins and the label band that hold it.
  const fontPx = (AXIS_FONT_PX * rootFontPx) / DEFAULT_ROOT_FONT_PX;
  const xLabelRefs = useRef<Array<SVGTextElement | null>>([]);
  const [measured, setMeasured] = useState<Record<string, number>>({});
  const lengthOf = (text: string) => measured[`${fontPx}|${text}`] ?? estimateLabelWidth(text, fontPx);
  const yLabelWidth = Math.max(0, ...history.yTicks.map((tick) => lengthOf(tick.label)));
  const MARGIN = {
    top: Math.max(22, Math.ceil(fontPx + 10)),
    right: 14,
    bottom: 6,
    left: Math.max(44, Math.ceil(yLabelWidth + 12)),
  };

  const [home, away] = history.series;
  const shapes: Record<string, "circle" | "square"> = { home: "circle", away: "square" };
  const colorOf = (series: HockeyJourneyHistorySeries) => (series.side === "home" ? colors.home : colors.away);

  const domain = history.domain;
  const plotW = Math.max(width - MARGIN.left - MARGIN.right, 40);
  const plotH = PLOT_HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (t: number) =>
    domain && domain.upper > domain.lower
      ? MARGIN.left + ((t - domain.lower) / (domain.upper - domain.lower)) * plotW
      : MARGIN.left + plotW / 2;
  const laneHeight = Math.ceil(fontPx * 1.25);

  // Period guide labels (FQ2): measured, kept 3 px right of their own line when they fit inside
  // the SVG and clear their neighbours; otherwise slid in from the edge and, only on a collision,
  // lifted a row. A lifted row adds height ABOVE the plot (`guideBand`), so the plot keeps its height.
  const periodGuides = history.guides.filter((guide) => guide.kind === "period");
  const guideLabels = guideLabelPlacement(
    periodGuides.map((guide) => x(guide.t)),
    periodGuides.map((guide) => lengthOf(guide.label)),
    MARGIN.left,
    width,
    LABEL_GAP_PX,
  );
  const guideLabelAt = new Map(periodGuides.map((guide, i) => [guide.id, guideLabels[i]]));
  const guideBand = guideLabels.reduce((n, label) => Math.max(n, label.lane), 0) * laneHeight;
  const plotTop = MARGIN.top + guideBand;

  const y = (p: number) => plotTop + (1 - p) * plotH;
  const path = (run: HockeyJourneyHistoryPoint[]) =>
    run.map((pt, i) => `${i === 0 ? "M" : "L"} ${x(pt.t).toFixed(1)} ${y(pt.p).toFixed(1)}`).join(" ");

  // X labels: a measured subset of the owner's ticks — endpoints first, an intermediate only
  // with a full em of clear space — kept clear of each other and of the y labels.
  const placements = axisLabelSubset(
    history.xTicks.map((tick) => x(tick.t) - MARGIN.left),
    history.xTicks.map((tick) => lengthOf(tick.label)),
    plotW,
    LABEL_GAP_PX,
    Math.max(LABEL_GAP_PX, fontPx),
  );
  const laneCount = placements.reduce((n, label) => Math.max(n, label.lane + 1), 0);
  // The first lane starts below the lower half of the "0%" label, which is centred on the plot's floor.
  const labelBandTop = PLOT_HEIGHT + guideBand - MARGIN.bottom + Math.ceil(fontPx / 2) + 4;
  const svgHeight = Math.max(PLOT_HEIGHT + guideBand + 26, labelBandTop + laneCount * laneHeight + 4);

  // Real text lengths replace the estimate once the browser can measure them (not in jsdom/SSR).
  // A label drawn for the first time is measured too, so the drawn subset is re-checked against real widths.
  // The period guide labels are measured by the same rule (FQ2).
  const guideLabelRefs = useRef<Array<SVGTextElement | null>>([]);
  const labelSignature = `${fontPx}|${history.xTicks.map((tick) => tick.label).join("\u0001")}|${history.yTicks
    .map((tick) => tick.label)
    .join("\u0001")}|${placements.map((label) => label.index).join(",")}|${periodGuides.map((guide) => guide.label).join("\u0001")}`;
  useIsomorphicLayoutEffect(() => {
    const next: Record<string, number> = {};
    let changed = false;
    // forEach skips the holes a drawn SUBSET leaves in the ref arrays (only drawn labels hold an element).
    const measure = (el: SVGTextElement | null, label: string | undefined) => {
      if (!el || label === undefined || typeof el.getComputedTextLength !== "function") return;
      const length = el.getComputedTextLength();
      if (!Number.isFinite(length) || length <= 0) return;
      const key = `${fontPx}|${label}`;
      next[key] = length;
      if (Math.abs((measured[key] ?? -1) - length) > 0.5) changed = true;
    };
    xLabelRefs.current.forEach((el, i) => measure(el, history.xTicks[i]?.label));
    guideLabelRefs.current.forEach((el, i) => measure(el, periodGuides[i]?.label));
    if (changed) setMeasured((prev) => ({ ...prev, ...next }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-measure only when the labels, their size or the drawn subset change
  }, [labelSignature]);

  // Each team's labelled slots: the pregame slot always, the recorded slot only when the readout asks.
  const slotsOf = (series: HockeyJourneyHistorySeries) => [
    { key: "before", label: history.beforeLabel, reading: series.before },
    ...(history.readout === "beforeAndRecorded"
      ? [{ key: "recorded", label: history.recordedLabel, reading: series.recorded }]
      : []),
  ];
  // Exact source and timing support lives in Details: each reading's own provenance, then the notes.
  const readingDetails = history.series.flatMap((series) =>
    slotsOf(series).flatMap(({ label, reading }) =>
      reading.kind === "reading" ? [`${series.name} · ${label} ${reading.figure} · ${reading.provenance}`] : [],
    ),
  );
  const detailLines = [...readingDetails, ...history.notes];

  return (
    <section aria-labelledby={titleId} className="space-y-3">
      <header>
        <h3 id={titleId} className="text-base font-semibold">
          {history.title}
        </h3>
      </header>

      <div ref={frame} className="w-full">
        {history.absence || !domain ? (
          <div
            className="flex flex-col items-center justify-center rounded-lg bg-surface-deep p-4 text-center"
            style={{ minHeight: PLOT_HEIGHT }}
          >
            <p className="text-base font-semibold">{history.absence?.title}</p>
            {history.absence?.words && <p className="mt-1 text-sm text-text-secondary">{history.absence.words}</p>}
          </div>
        ) : (
          <svg
            role="img"
            aria-label={history.summary}
            width={width}
            height={svgHeight}
            viewBox={`0 0 ${width} ${svgHeight}`}
            className="block max-w-full overflow-visible"
          >
            {history.yTicks.map((tick) => (
              <g key={tick.p}>
                <line x1={MARGIN.left} x2={MARGIN.left + plotW} y1={y(tick.p)} y2={y(tick.p)} className="stroke-surface-border" />
                <text
                  x={MARGIN.left - 6}
                  y={y(tick.p)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="fill-text-secondary text-xs"
                >
                  {tick.label}
                </text>
              </g>
            ))}
            {history.guides.map((guide) => {
              // The line stays on its own time; only a period label's box is placed (FQ2).
              const label = guide.kind === "period" ? guideLabelAt.get(guide.id) : undefined;
              return (
                <g key={guide.id}>
                  <line
                    x1={x(guide.t)}
                    x2={x(guide.t)}
                    y1={plotTop}
                    y2={plotTop + plotH}
                    className="stroke-surface-border"
                    strokeDasharray="3 3"
                  />
                  {label && (
                    <text
                      ref={(el) => {
                        guideLabelRefs.current[label.index] = el;
                      }}
                      x={label.start}
                      y={plotTop - 8 - label.lane * laneHeight}
                      className="fill-text-secondary text-xs"
                      data-guide-label={guide.id}
                      data-guide-lane={label.lane}
                    >
                      {guide.label}
                    </text>
                  )}
                </g>
              );
            })}
            {[home, away].flatMap((series) =>
              series.runs.flatMap((run, i) =>
                run.length > 1
                  ? [
                      <path
                        key={`${series.id}#run-${i}`}
                        d={path(run)}
                        fill="none"
                        strokeWidth={2.5}
                        strokeLinejoin="round"
                        strokeLinecap="round"
                        style={{ stroke: colorOf(series) }}
                      />,
                    ]
                  : [],
              ),
            )}
            {[home, away].flatMap((series) =>
              series.runs.flatMap((run) =>
                run
                  .filter((pt, i) => pt.hollow || run.length === 1 || i === run.length - 1)
                  .map((pt) => (
                    <Mark
                      key={pt.id}
                      x={x(pt.t)}
                      y={y(pt.p)}
                      shape={shapes[series.side]}
                      color={colorOf(series)}
                      hollow={pt.hollow}
                    />
                  )),
              ),
            )}
            {placements.map((label) => (
              <text
                key={history.xTicks[label.index].t}
                ref={(el) => {
                  xLabelRefs.current[label.index] = el;
                }}
                x={MARGIN.left + label.start}
                y={labelBandTop + label.lane * laneHeight}
                textAnchor="start"
                dominantBaseline="hanging"
                className="fill-text-secondary text-xs"
                data-axis-lane={label.lane}
                data-axis-tick={label.index}
              >
                {history.xTicks[label.index].label}
              </text>
            ))}
          </svg>
        )}
      </div>

      {/* .hj-line-key: both teams, glyph + full name, each with its own labelled readings.
          Side by side while they fit, one under the other when they do not (200% text). */}
      <ul className="flex flex-wrap justify-between gap-x-6 gap-y-2 text-sm" aria-label="Lines" data-line-key="">
        {history.series.map((series) => (
          <li key={series.id} className="min-w-0 max-w-full">
            <p className="flex items-center gap-2 font-semibold">
              <svg viewBox="0 0 14 14" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                {shapes[series.side] === "circle" ? (
                  <circle cx="7" cy="7" r="5" style={{ fill: colorOf(series) }} />
                ) : (
                  <rect x="2" y="2" width="10" height="10" style={{ fill: colorOf(series) }} />
                )}
              </svg>
              <span className="min-w-0 break-words">{series.name}</span>
            </p>
            <dl className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
              {slotsOf(series).map(({ key, label, reading }) => (
                <KeySlot key={key} label={label} reading={reading} />
              ))}
            </dl>
          </li>
        ))}
      </ul>

      {/* .hj-history-basis */}
      <p className="flex flex-wrap gap-x-3 text-sm text-text-secondary" data-history-basis="">
        <span>{history.caption}</span>
        {history.markKey && !history.absence && <span>{history.markKey}</span>}
      </p>

      {/* The disclosure exists only over real support: with no history response there is
          nothing to disclose, so no control is offered (and no retry is invented). */}
      {detailLines.length > 0 && (
        <div>
          <button
            type="button"
            aria-expanded={detailsOpen}
            aria-controls={detailsId}
            onClick={() => setDetailsOpen((open) => !open)}
            className="min-h-11 text-sm font-semibold text-text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {history.detailsLabel}
          </button>
          <ul id={detailsId} hidden={!detailsOpen} className="list-disc space-y-1 pl-5 text-sm text-text-secondary">
            {detailLines.map((line, i) => (
              <li key={`${i}:${line}`} className="break-words">
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
