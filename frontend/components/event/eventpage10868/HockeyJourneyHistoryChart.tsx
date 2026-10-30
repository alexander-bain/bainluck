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

export interface AxisLabelSlot {
  /** Left edge, from the start of the plot. */
  start: number;
  /** 0 is the row nearest the plot. */
  lane: number;
}

/**
 * Native `FieldHistoryGeometry10868.labelSlots` (FieldProbabilityHistoryPresentation10868
 * .swift:1094): each label centred on its tick, slid inward to stay inside
 * `extent` (the plot's width, so no x label can reach the y-axis labels in the
 * left margin), and placed in the first lane where it keeps `gap` clear of
 * every label already there. NOTHING IS DROPPED and no tick moves — a label
 * that would collide takes the next lane down.
 */
export function axisLabelSlots(centers: number[], lengths: number[], extent: number, gap: number): AxisLabelSlot[] {
  const span = Math.max(0, Number.isFinite(extent) ? extent : 0);
  const clear = Math.max(0, gap);
  const lanes: Array<Array<[number, number]>> = [];
  const slots: AxisLabelSlot[] = [];
  const count = Math.min(centers.length, lengths.length);
  for (let i = 0; i < count; i += 1) {
    const length = Math.min(Math.max(0, Number.isFinite(lengths[i]) ? lengths[i] : 0), span);
    const middle = Number.isFinite(centers[i]) ? centers[i] : 0;
    const start = Math.min(Math.max(0, middle - length / 2), span - length);
    const lo = start - clear;
    const hi = start + length + clear;
    let lane = lanes.findIndex((taken) => !taken.some(([a, b]) => a <= hi && lo <= b));
    if (lane < 0) {
      lane = lanes.length;
      lanes.push([]);
    }
    lanes[lane].push([start, start + length]);
    slots.push({ start, lane });
  }
  return slots;
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

function Reading({ label, reading }: { label: string; reading: HockeyJourneyReading }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm font-medium text-text-secondary">{label}</dt>
      <dd className="mt-0.5">
        {reading.kind === "reading" ? (
          <>
            <span className="text-xl font-bold tabular-nums text-text-primary">{reading.figure}</span>
            <span className="block text-sm text-text-secondary break-words">{reading.provenance}</span>
          </>
        ) : (
          <span className="text-sm font-medium text-text-secondary">{reading.words}</span>
        )}
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
  const y = (p: number) => MARGIN.top + (1 - p) * plotH;
  const path = (run: HockeyJourneyHistoryPoint[]) =>
    run.map((pt, i) => `${i === 0 ? "M" : "L"} ${x(pt.t).toFixed(1)} ${y(pt.p).toFixed(1)}`).join(" ");

  // X labels: kept clear of each other and of the y labels (lanes, nothing dropped).
  const slots = axisLabelSlots(
    history.xTicks.map((tick) => x(tick.t) - MARGIN.left),
    history.xTicks.map((tick) => lengthOf(tick.label)),
    plotW,
    LABEL_GAP_PX,
  );
  const laneCount = slots.reduce((n, slot) => Math.max(n, slot.lane + 1), 0);
  const laneHeight = Math.ceil(fontPx * 1.25);
  // The first lane starts below the lower half of the "0%" label, which is centred on the plot's floor.
  const labelBandTop = PLOT_HEIGHT - MARGIN.bottom + Math.ceil(fontPx / 2) + 4;
  const svgHeight = Math.max(PLOT_HEIGHT + 26, labelBandTop + laneCount * laneHeight + 4);

  // Real text lengths replace the estimate once the browser can measure them (not in jsdom/SSR).
  const labelSignature = `${fontPx}|${history.xTicks.map((tick) => tick.label).join("\u0001")}|${history.yTicks
    .map((tick) => tick.label)
    .join("\u0001")}`;
  useIsomorphicLayoutEffect(() => {
    const next: Record<string, number> = {};
    let changed = false;
    xLabelRefs.current.forEach((el, i) => {
      const label = history.xTicks[i]?.label;
      if (!el || label === undefined || typeof el.getComputedTextLength !== "function") return;
      const length = el.getComputedTextLength();
      if (!Number.isFinite(length) || length <= 0) return;
      const key = `${fontPx}|${label}`;
      next[key] = length;
      if (Math.abs((measured[key] ?? -1) - length) > 0.5) changed = true;
    });
    if (changed) setMeasured((prev) => ({ ...prev, ...next }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-measure only when the labels or their size change
  }, [labelSignature]);

  return (
    <section aria-labelledby={titleId} className="space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={titleId} className="text-base font-semibold">
          {history.title}
        </h3>
        <span className="text-sm text-text-secondary">{history.caption}</span>
      </header>

      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Lines">
        {history.series.map((series) => (
          <li key={series.id} className="flex items-center gap-2">
            <svg width="14" height="14" aria-hidden="true">
              {shapes[series.side] === "circle" ? (
                <circle cx="7" cy="7" r="5" style={{ fill: colorOf(series) }} />
              ) : (
                <rect x="2" y="2" width="10" height="10" style={{ fill: colorOf(series) }} />
              )}
            </svg>
            <span className="font-medium">{series.name}</span>
          </li>
        ))}
      </ul>

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
            {history.guides.map((guide) => (
              <g key={guide.id}>
                <line
                  x1={x(guide.t)}
                  x2={x(guide.t)}
                  y1={MARGIN.top}
                  y2={MARGIN.top + plotH}
                  className="stroke-surface-border"
                  strokeDasharray="3 3"
                />
                {guide.kind === "period" && (
                  <text x={x(guide.t) + 3} y={MARGIN.top - 8} className="fill-text-secondary text-xs">
                    {guide.label}
                  </text>
                )}
              </g>
            ))}
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
            {history.xTicks.map((tick, i) => (
              <text
                key={tick.t}
                ref={(el) => {
                  xLabelRefs.current[i] = el;
                }}
                x={MARGIN.left + (slots[i]?.start ?? 0)}
                y={labelBandTop + (slots[i]?.lane ?? 0) * laneHeight}
                textAnchor="start"
                dominantBaseline="hanging"
                className="fill-text-secondary text-xs"
                data-axis-lane={slots[i]?.lane ?? 0}
              >
                {tick.label}
              </text>
            ))}
          </svg>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {history.series.map((series) => (
          <div key={series.id} className="rounded-lg bg-surface-deep p-3">
            <p className="font-semibold">{series.name}</p>
            <dl className="mt-1 grid grid-cols-1 gap-2">
              <Reading label={history.beforeLabel} reading={series.before} />
              {history.readout === "beforeAndRecorded" && <Reading label={history.recordedLabel} reading={series.recorded} />}
            </dl>
          </div>
        ))}
      </div>

      {history.markKey && !history.absence && <p className="text-sm text-text-secondary">{history.markKey}</p>}

      {/* The disclosure exists only over real notes: with no history response there is
          nothing to disclose, so no control is offered (and no retry is invented). */}
      {history.notes.length > 0 && (
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
            {history.notes.map((note, i) => (
              <li key={`${i}:${note}`}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
