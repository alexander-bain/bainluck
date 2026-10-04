'use client';

/**
 * #10239 — each team's projected final points, drawn apart from the points it
 * has actually scored.
 *
 * A secondary module. The win probability stays the page's headline; this
 * renders NOTHING (no title, no empty frame) when the game cannot be drawn
 * honestly: an unsupported sport, an unnamed source, or no valid pair. Every
 * rule about what counts as a reading lives in `lib/projectedFinalPointsSeries`.
 * This file only draws what that module returns.
 *
 * Inspection rebuilds the series AT the cursor (`seriesAt`), so the readout
 * and the drawn lines stop there. A scrubbed moment cannot show a later
 * projection or a later score.
 *
 * The cursor is the inspected TIMESTAMP, never a slider index. A refresh that
 * adds an earlier reading, or drops one off the window's left edge, shifts
 * every index; holding the index would silently move the reader to another
 * reading. If the inspected reading itself leaves the data, the readout says
 * so rather than showing a neighbour.
 */

import { useMemo, useState } from "react";
import { format } from "date-fns";
import {
  buildProjectedFinalPointsSeries,
  inspectionInstants,
  seriesAt,
  type ActualStep,
  type ForecastPoint,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
} from "@/lib/projectedFinalPointsSeries";
import { teamTextColor } from "@/lib/teamColors";

export interface ProjectedFinalPointsChartProps {
  input: ProjectedFinalPointsInput;
  homeTeam: string;
  awayTeam: string;
  homeColor?: string | null;
  awayColor?: string | null;
}

interface ViewProps extends ProjectedFinalPointsChartProps {
  /** The inspected reading's time (epoch ms), or null for the latest view. */
  cursorAt: number | null;
  onCursorChange?: (at: number | null) => void;
}

const W = 1000;
const H = 300;
const LEFT = 64;
const RIGHT = 990;
const TOP = 16;
const BOTTOM = 262;

export function formatProjectionTime(t: number): string {
  return format(new Date(t), "h:mm a");
}

function points(value: number): string {
  return value.toFixed(1);
}

function stepPath(
  seg: ForecastPoint[],
  key: "home" | "away",
  x: (t: number) => number,
  y: (v: number) => number,
): string {
  let d = `M${x(seg[0].at).toFixed(1)},${y(seg[0][key]).toFixed(1)}`;
  for (let i = 1; i < seg.length; i++) {
    d += ` H${x(seg[i].at).toFixed(1)} V${y(seg[i][key]).toFixed(1)}`;
  }
  return d + ` H${x(seg[seg.length - 1].holdEnd).toFixed(1)}`;
}

function actualPath(
  steps: ActualStep[],
  key: "home" | "away",
  end: number,
  x: (t: number) => number,
  y: (v: number) => number,
): string {
  let d = `M${x(steps[0].at).toFixed(1)},${y(steps[0][key]).toFixed(1)}`;
  for (let i = 1; i < steps.length; i++) {
    d += ` H${x(steps[i].at).toFixed(1)} V${y(steps[i][key]).toFixed(1)}`;
  }
  return d + ` H${x(end).toFixed(1)}`;
}

function readingLabel(series: ProjectedFinalPointsSeries, inspecting: boolean): string {
  if (inspecting) return "Projection at this point";
  if (series.phase === "after") return "Last projection before the final";
  return "Latest projection";
}

export function ProjectedFinalPointsChartView({
  input,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  cursorAt,
  onCursorChange,
}: ViewProps) {
  const full = useMemo(() => buildProjectedFinalPointsSeries(input), [input]);
  const instants = useMemo(() => (full.supported ? inspectionInstants(full) : []), [full]);
  const cursorIndex = cursorAt === null ? -1 : instants.indexOf(cursorAt);
  // The inspected reading is no longer in the data (dropped at the window edge, or withdrawn).
  const cursorGone = cursorAt !== null && cursorIndex < 0;
  const view = useMemo(
    () => (cursorAt === null || cursorGone || !full.supported ? full : seriesAt(input, cursorAt)),
    [full, input, cursorAt, cursorGone],
  );
  if (!full.supported) return null;

  const homeStroke = teamTextColor(homeColor) ?? "var(--text-primary)";
  const awayStroke = teamTextColor(awayColor) ?? "var(--text-secondary)";
  const span = Math.max(1, full.end - full.start);
  const x = (t: number) => LEFT + ((Math.min(Math.max(t, full.start), full.end) - full.start) / span) * (RIGHT - LEFT);
  const y = (v: number) => BOTTOM - (v / full.yMax) * (BOTTOM - TOP);

  // A cursor before the first valid reading leaves nothing to read yet.
  const shown = cursorGone ? null : view.supported ? view : null;
  const inspecting = cursorAt !== null;
  const reading = shown?.latest ?? null;
  const actual = shown?.latestActual ?? null;
  const showActual = !cursorGone && (shown?.phase ?? "before") !== "before";
  const withheldAtCursor = inspecting && full.withheld.some((w) => w.at === cursorAt);
  const lastIndex = instants.length - 1;
  // A gone cursor parks the thumb at the last instant before it; the readout says it is gone.
  const sliderIndex =
    cursorAt === null
      ? lastIndex
      : cursorGone
        ? Math.max(0, instants.filter((t) => t < cursorAt).length - 1)
        : cursorIndex;

  const valueText = cursorGone
    ? `${formatProjectionTime(cursorAt)}, that reading is no longer shown`
    : !reading || withheldAtCursor
      ? `${cursorAt !== null ? formatProjectionTime(cursorAt) : ""}, no usable projection`
      : `recorded ${formatProjectionTime(reading.at)}, ${homeTeam} ${points(reading.home)}, ${awayTeam} ${points(reading.away)} projected final points`;

  return (
    <section
      className="rounded-xl border border-surface-border bg-surface-card p-4"
      aria-labelledby="projected-final-points-title"
      data-projected-final-points={full.phase}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 id="projected-final-points-title" className="text-base font-semibold text-text-primary">
          Projected final points
        </h3>
        <span className="text-xs text-text-secondary">{full.sourceName}</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3" aria-live="polite" data-testid="projected-reading">
        {([
          ["home", homeTeam, homeStroke],
          ["away", awayTeam, awayStroke],
        ] as const).map(([key, name, stroke]) => (
          <div key={key} data-side={key}>
            <div className="truncate text-sm font-medium" style={{ color: stroke }}>
              {name}
            </div>
            <div className="text-2xl font-semibold tabular-nums text-text-primary">
              {reading && !withheldAtCursor ? points(reading[key]) : "—"}
            </div>
            <div className="text-xs text-text-secondary">projected final</div>
            {/* Only a recorded score is printed. Without one there is no "— final" placeholder:
                a dash beside "final" reads as a result nobody recorded. */}
            {showActual && actual && (
              <div className="text-sm tabular-nums text-text-primary" data-actual={key}>
                {actual[key]} {shown?.phase === "after" && !inspecting ? "final" : "scored"}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="mt-2 text-xs text-text-secondary" data-testid="projected-stamp">
        {cursorGone
          ? "That reading is no longer shown"
          : reading && !withheldAtCursor
            ? `${readingLabel(full, inspecting)} · recorded ${formatProjectionTime(reading.at)}`
            : "No usable projection at this point"}
        {!inspecting && full.latestIntervalUnavailable && reading && (
          <>
            <br />
            No usable projection since then
          </>
        )}
      </p>

      <div className="relative mt-3 h-48">
      {full.yTicks.map((v) => (
        <span
          key={`tick-${v}`}
          aria-hidden="true"
          className="absolute left-0 -translate-y-1/2 text-xs tabular-nums text-text-secondary"
          style={{ top: `${(y(v) / H) * 100}%` }}
        >
          {v}
        </span>
      ))}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Projected final points for ${homeTeam} and ${awayTeam}, with the actual score as a quieter dashed step line. Gaps are missing or unusable readings and are not joined.`}
      >
        {full.yTicks.map((v) => (
          <line
            key={v}
            x1={LEFT}
            x2={RIGHT}
            y1={y(v)}
            y2={y(v)}
            stroke="var(--surface-border)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {shown && showActual && shown.actualSteps.length > 0 &&
          ([
            ["home", homeStroke],
            ["away", awayStroke],
          ] as const).map(([key, stroke]) => (
            <path
              key={`actual-${key}`}
              data-series={`actual-${key}`}
              d={actualPath(shown.actualSteps, key, shown.end, x, y)}
              fill="none"
              stroke={stroke}
              strokeWidth={2.5}
              strokeDasharray="6 5"
              strokeOpacity={0.75}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        {shown &&
          ([
            ["home", homeStroke],
            ["away", awayStroke],
          ] as const).map(([key, stroke]) =>
            shown.segments.map((seg, i) =>
              seg.length === 1 && seg[0].holdEnd === seg[0].at ? (
                // A round-capped stroke, not a circle: the plot stretches to its
                // box, and a circle would stretch with it into an ellipse.
                <path
                  key={`${key}-${i}`}
                  data-series={`forecast-${key}`}
                  data-single-point="true"
                  d={`M${x(seg[0].at).toFixed(1)},${y(seg[0][key]).toFixed(1)} h0.01`}
                  stroke={stroke}
                  strokeWidth={8}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              ) : (
                <path
                  key={`${key}-${i}`}
                  data-series={`forecast-${key}`}
                  d={stepPath(seg, key, x, y)}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={3}
                  vectorEffect="non-scaling-stroke"
                />
              ),
            ),
          )}
        {shown?.withheld.map((w) => (
          <line
            key={`gap-${w.at}`}
            data-withheld={w.reason}
            x1={x(w.at)}
            x2={x(w.at)}
            y1={BOTTOM + 4}
            y2={BOTTOM + 12}
            stroke="var(--text-secondary)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {cursorAt !== null && !cursorGone && (
          <line
            data-testid="projected-cursor"
            x1={x(cursorAt)}
            x2={x(cursorAt)}
            y1={TOP}
            y2={BOTTOM}
            stroke="var(--text-secondary)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      </div>
      <div className="flex justify-between pl-6 text-xs text-text-secondary" aria-hidden="true">
        <span>{formatProjectionTime(full.start)}</span>
        <span>{formatProjectionTime(full.end)}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        <span>━ Projected final</span>
        <span>┅ Actual score</span>
        <span>Gaps are not joined</span>
      </div>

      {instants.length > 1 && (
        <label className="mt-3 block text-xs text-text-secondary">
          Step through the projections
          <input
            type="range"
            className="mt-1 block w-full accent-graphite"
            min={0}
            max={lastIndex}
            value={sliderIndex}
            aria-label="Inspect projected final points over time"
            aria-valuetext={valueText}
            onChange={(e) => {
              const index = Number(e.target.value);
              onCursorChange?.(index === lastIndex ? null : instants[index]);
            }}
          />
        </label>
      )}
      {inspecting && (
        <button
          type="button"
          className="mt-2 text-xs font-medium text-text-primary underline"
          onClick={() => onCursorChange?.(null)}
        >
          Back to latest
        </button>
      )}

      <details className="mt-3 text-xs text-text-secondary">
        <summary className="cursor-pointer">How to read this</summary>
        <p className="mt-1">
          Each line is the final score {full.sourceName}&apos;s point spread and total imply for one team. The dashed
          steps are the score so far. A break in a line means that reading was missing or could not be right, such as a
          projection below points already scored. The last projection is never joined to the final score.
        </p>
      </details>
    </section>
  );
}

export default function ProjectedFinalPointsChart(props: ProjectedFinalPointsChartProps) {
  const [cursorAt, setCursorAt] = useState<number | null>(null);
  return <ProjectedFinalPointsChartView {...props} cursorAt={cursorAt} onCursorChange={setCursorAt} />;
}
