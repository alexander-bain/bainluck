"use client";

/**
 * #10868 — the soccer match's win-probability history (web).
 *
 * Draws `SoccerMatchHistory` exactly: ONE line, the home win chance (native
 * `SoccerHistoryAdapter10868` draws home only). Each run is its own path and
 * two runs are never joined, so every unrecorded stretch stays blank; a run of
 * one row is a mark; the last pre-match row is hollow (none when the kickoff is
 * not confirmed). The key names all three outcomes in the headline's order —
 * the home win with its labelled readings, then Draw (diamond) and the away win
 * (square), each with its own absence words and no line. "History
 * unavailable" when no body is held; "No recorded history" when the body has
 * no readable row.
 *
 * The plot, axis placement and Details disclosure follow the hockey chart
 * (`HockeyJourneyHistoryChart.tsx`), importing its measured axis-label rules.
 * No animation and no timer: the only effect measures the plot's width so
 * lines, marks and labels are drawn at real pixels. No Full chart or Inspect
 * control: neither has a destination on web yet.
 */

import { useId, useRef, useState } from "react";
import type { HockeyJourneyHistoryPoint, HockeyJourneyReading } from "@/lib/eventPage10868/hockeyJourneyTypes";
import type { SoccerHistoryAbsentEntry, SoccerMatchHistory } from "@/lib/eventPage10868/soccerMatchTypes";
import { axisLabelSubset, estimateLabelWidth, guideLabelPlacement } from "./HockeyJourneyHistoryChart";
import { DEFAULT_ROOT_FONT_PX, useFrameMeasure, useIsomorphicLayoutEffect } from "./useFrameMeasure";

const PLOT_HEIGHT = 230;
const AXIS_FONT_PX = 12;
const LABEL_GAP_PX = 6;

export interface SoccerMatchLineColors {
  home: string;
  away: string;
}

type Shape = "circle" | "diamond" | "square";

function Glyph({ shape, color, className }: { shape: Shape; color?: string; className?: string }) {
  const style = color ? { fill: color } : undefined;
  return (
    <svg viewBox="0 0 14 14" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
      {shape === "circle" && <circle cx="7" cy="7" r="5" style={style} className={className} />}
      {shape === "square" && <rect x="2" y="2" width="10" height="10" style={style} className={className} />}
      {shape === "diamond" && <path d="M7 1.5 L12.5 7 L7 12.5 L1.5 7 Z" style={style} className={className} />}
    </svg>
  );
}

function Mark({ x, y, color, hollow }: { x: number; y: number; color: string; hollow: boolean }) {
  return (
    <circle
      cx={x}
      cy={y}
      r={hollow ? 4.5 : 3.5}
      strokeWidth={2}
      style={{ stroke: color, fill: hollow ? undefined : color }}
      className={hollow ? "fill-surface-card" : undefined}
    />
  );
}

function KeySlot({ label, reading }: { label: string; reading: HockeyJourneyReading }) {
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

function AbsentKey({ entry, shape, color }: { entry: SoccerHistoryAbsentEntry; shape: Shape; color?: string }) {
  return (
    <li className="min-w-0 max-w-full" data-history-absent={entry.key}>
      <p className="flex items-center gap-2 font-semibold">
        <Glyph shape={shape} color={color} className={color ? undefined : "fill-text-secondary"} />
        <span className="min-w-0 break-words">{entry.name}</span>
      </p>
      <p className="mt-0.5 text-text-secondary">{entry.words}</p>
    </li>
  );
}

export default function SoccerMatchHistoryChart({
  history,
  colors,
}: {
  history: SoccerMatchHistory;
  colors: SoccerMatchLineColors;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const { width, rootFontPx } = useFrameMeasure(frame, 600);
  const titleId = useId();
  const detailsId = useId();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const fontPx = (AXIS_FONT_PX * rootFontPx) / DEFAULT_ROOT_FONT_PX;
  const xLabelRefs = useRef<Array<SVGTextElement | null>>([]);
  const guideLabelRefs = useRef<Array<SVGTextElement | null>>([]);
  const [measured, setMeasured] = useState<Record<string, number>>({});
  const lengthOf = (text: string) => measured[`${fontPx}|${text}`] ?? estimateLabelWidth(text, fontPx);
  const yLabelWidth = Math.max(0, ...history.yTicks.map((tick) => lengthOf(tick.label)));
  const MARGIN = {
    top: Math.max(22, Math.ceil(fontPx + 10)),
    right: 14,
    bottom: 6,
    left: Math.max(44, Math.ceil(yLabelWidth + 12)),
  };

  const home = history.home;
  const domain = history.domain;
  const plotW = Math.max(width - MARGIN.left - MARGIN.right, 40);
  const plotH = PLOT_HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (t: number) =>
    domain && domain.upper > domain.lower
      ? MARGIN.left + ((t - domain.lower) / (domain.upper - domain.lower)) * plotW
      : MARGIN.left + plotW / 2;
  const laneHeight = Math.ceil(fontPx * 1.25);

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

  const placements = axisLabelSubset(
    history.xTicks.map((tick) => x(tick.t) - MARGIN.left),
    history.xTicks.map((tick) => lengthOf(tick.label)),
    plotW,
    LABEL_GAP_PX,
    Math.max(LABEL_GAP_PX, fontPx),
  );
  const laneCount = placements.reduce((n, label) => Math.max(n, label.lane + 1), 0);
  const labelBandTop = PLOT_HEIGHT + guideBand - MARGIN.bottom + Math.ceil(fontPx / 2) + 4;
  const svgHeight = Math.max(PLOT_HEIGHT + guideBand + 26, labelBandTop + laneCount * laneHeight + 4);

  const labelSignature = `${fontPx}|${history.xTicks.map((tick) => tick.label).join("\u0001")}|${placements
    .map((label) => label.index)
    .join(",")}|${periodGuides.map((guide) => guide.label).join("\u0001")}`;
  useIsomorphicLayoutEffect(() => {
    const next: Record<string, number> = {};
    let changed = false;
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

  const slots = [
    { key: "before", label: history.beforeLabel, reading: home.before },
    ...(history.readout === "beforeAndRecorded" ? [{ key: "recorded", label: history.recordedLabel, reading: home.recorded }] : []),
  ];
  const readingDetails = slots.flatMap(({ label, reading }) =>
    reading.kind === "reading" ? [`${home.name} · ${label} ${reading.figure} · ${reading.provenance}`] : [],
  );
  const detailLines = [...readingDetails, ...history.notes];

  return (
    <section aria-labelledby={titleId} className="space-y-3" data-soccer-history={history.line ?? "unavailable"}>
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
                <text x={MARGIN.left - 6} y={y(tick.p)} textAnchor="end" dominantBaseline="middle" className="fill-text-secondary text-xs">
                  {tick.label}
                </text>
              </g>
            ))}
            {history.guides.map((guide) => {
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
                    >
                      {guide.label}
                    </text>
                  )}
                </g>
              );
            })}
            {home.runs.map((run, i) =>
              run.length > 1 ? (
                <path
                  key={`${home.id}#run-${i}`}
                  d={path(run)}
                  fill="none"
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  style={{ stroke: colors.home }}
                />
              ) : null,
            )}
            {home.runs.flatMap((run) =>
              run
                .filter((pt, i) => pt.hollow || run.length === 1 || i === run.length - 1)
                .map((pt) => <Mark key={pt.id} x={x(pt.t)} y={y(pt.p)} color={colors.home} hollow={pt.hollow} />),
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
                data-axis-tick={label.index}
              >
                {history.xTicks[label.index].label}
              </text>
            ))}
          </svg>
        )}
      </div>

      {/* The key: all three outcomes in the headline's order. Only the home win has a line. */}
      <ul className="flex flex-wrap justify-between gap-x-6 gap-y-2 text-sm" aria-label="Lines" data-line-key="">
        <li className="min-w-0 max-w-full" data-history-line="home">
          <p className="flex items-center gap-2 font-semibold">
            <Glyph shape="circle" color={colors.home} />
            <span className="min-w-0 break-words">{home.name}</span>
          </p>
          <dl className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
            {slots.map(({ key, label, reading }) => (
              <KeySlot key={key} label={label} reading={reading} />
            ))}
          </dl>
        </li>
        <AbsentKey entry={history.draw} shape="diamond" />
        <AbsentKey entry={history.away} shape="square" color={colors.away} />
      </ul>

      <p className="flex flex-wrap gap-x-3 text-sm text-text-secondary" data-history-basis="">
        <span>{history.caption}</span>
        {history.markKey && !history.absence && <span>{history.markKey}</span>}
      </p>

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
