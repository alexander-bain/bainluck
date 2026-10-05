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
 * #10539 (Alex, on 14781135): one chart, read at a glance. The full timeline
 * and its latest (or last) valid projection are the whole view. The old
 * "step through" slider is gone and nothing replaces it; the readout above
 * the plot carries both quantities and the recorded time as text. The plot is
 * taller, the source sits in "How to read this" instead of an unexplained
 * name in the heading, and the game's evidenced period boundaries are marked
 * where they were observed.
 */

import { useMemo } from "react";
import { format } from "date-fns";
import {
  buildProjectedFinalPointsSeries,
  type ActualStep,
  type ForecastPoint,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
  type ProjectedFinalPointsUnsupported,
} from "@/lib/projectedFinalPointsSeries";
import {
  anchorPeriodLabels,
  collapseDuplicateTransitions,
  isEstimatedBoundary,
  PERIOD_LABEL_ROW_HEIGHT_PX,
  periodBoundaryChipLabel,
  placePeriodLabels,
  type PeriodBoundary,
} from "@/lib/periodMarkers";
import { colorDistance } from "@/lib/probabilityBarPair";
import { hexToRgb, teamTextColor } from "@/lib/teamColors";

export interface ProjectedFinalPointsChartProps {
  input: ProjectedFinalPointsInput;
  homeTeam: string;
  awayTeam: string;
  homeColor?: string | null;
  awayColor?: string | null;
  /**
   * The game's final score as the page's hero prints it, or null when the page has none it would
   * show. It is the only thing that lets the last recorded score be called final. It is printed in
   * the readout, never drawn as a step or given a time.
   */
  finalScore?: { home: number; away: number } | null;
  /**
   * The page's evidenced period boundaries (`derivePeriodBoundaries`). Only
   * observed ones inside the drawn span are marked; see `drawnPeriodMarkers`.
   */
  periodBoundaries?: PeriodBoundary[];
}

const W = 1000;
const H = 300;
const LEFT = 64;
const RIGHT = 990;
const TOP = 16;
// #10539: the gutter below the plot holds only the gap marks (BOTTOM+4..+12). The plot stretches
// to its box, so a wider gutter grew into an empty strip above the time labels once the box got taller.
const BOTTOM = 284;

export function formatProjectionTime(t: number): string {
  return format(new Date(t), "h:mm a");
}

/**
 * #10547 — two team lines this close read as one line. Redmean distance, the
 * same instrument `probabilityBarPair` uses, but not its threshold: a bar half
 * is a block and 80 separates blocks, while these are 3px strokes that cross
 * each other. Bills `#00338D` / Patriots `#002244` measure 131, two NFL navies
 * that were one line at 390px on /events/14781135; navy against black is 136
 * and two reds 128. Royal blue against dark green (164) stays as supplied.
 */
export const MIN_LINE_PAIR_DISTANCE = 150;

/** What a team with no readable colour already gets here: the two text tokens (globals.css). */
const AWAY_FALLBACK = "#6B7280"; // --text-secondary
const HOME_FALLBACK = "#111827"; // --text-primary

/**
 * Where a too-close side goes: existing tokens a team name can be printed in
 * (every one clears `teamTextColor`'s 3:1 floor; a test asserts it). Not the
 * bar ladder's `#9CA3AF`, which is too faint to be text.
 */
export const LINE_RESCUE_COLORS = [
  AWAY_FALLBACK,
  "#4F46E5", // the bar ladder's indigo
  "#EF4444", // --accent-danger
  "#8B5CF6", // --accent-futures
  HOME_FALLBACK,
] as const;

function lineDistance(a: string, b: string): number {
  const [pa, pb] = [a, b].map((hex) => (hexToRgb(hex) ?? "0 0 0").split(" ").map(Number));
  return colorDistance([pa[0], pa[1], pa[2]], [pb[0], pb[1], pb[2]]);
}

function withHash(hex: string): string {
  const raw = hex.trim();
  return raw.startsWith("#") ? raw : `#${raw}`;
}

/**
 * #10547 — the two teams' colours, decided as a pair. The team name, its solid
 * projection and its dashed score all take the one colour returned here, so the
 * names above the plot stay the key to the lines.
 *
 * A readable supplied colour is kept unless the pair is too close. Then a real
 * colour is kept over a fallback and, between two real ones, the away side is
 * kept (arbitrary, but fixed, so one game never renders two ways). The other
 * side takes the rescue colour farthest from the kept one.
 */
export function projectedTeamStrokes(
  homeColor?: string | null,
  awayColor?: string | null,
): { home: string; away: string } {
  const homeReal = teamTextColor(homeColor);
  const awayReal = teamTextColor(awayColor);
  const home = homeReal ? withHash(homeReal) : HOME_FALLBACK;
  const away = awayReal ? withHash(awayReal) : AWAY_FALLBACK;
  if (lineDistance(home, away) >= MIN_LINE_PAIR_DISTANCE) return { home, away };
  const keepHome = !!homeReal && !awayReal;
  const kept = keepHome ? home : away;
  let best: string = LINE_RESCUE_COLORS[0];
  for (const c of LINE_RESCUE_COLORS) {
    if (lineDistance(c, kept) > lineDistance(best, kept)) best = c;
  }
  return keepHome ? { home, away: best } : { home: best, away };
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

function readingLabel(series: ProjectedFinalPointsSeries): string {
  if (series.phase === "after") return "Last projection before the final";
  return "Latest projection";
}

/** How much a marker's time says about the period's start, in a reader's words. */
function markerTiming(b: PeriodBoundary): string {
  if (b.precision === "boundary_observed") return "began";
  if (b.precision === "first_score") return "first score";
  // Every client-derived boundary, and a provenance-less one, is a first observed state.
  return "first seen in progress";
}

/**
 * The period boundaries this chart marks, laid out by the page's shared label
 * rules (#888: one implementation, every chart). Only a boundary an instrument
 * OBSERVED, inside the drawn span, at its own timestamp: an `estimated` one is
 * arithmetic on the schedule and is left off rather than drawn as timing. No
 * marker before the game (a scheduled page draws forecasts only), none after
 * `end` (so nothing later than now on a live game), and the span is never
 * stretched to reach one. A missing boundary is a missing marker.
 */
export function drawnPeriodMarkers(
  series: ProjectedFinalPointsSeries | ProjectedFinalPointsUnsupported,
  boundaries: PeriodBoundary[] | null | undefined,
) {
  if (!series.supported || series.phase === "before" || !boundaries?.length) return [];
  const span = Math.max(1, series.end - series.start);
  const inSpan = boundaries
    .filter((b) => !isEstimatedBoundary(b))
    .map((b) => ({ b, t: Date.parse(b.timestamp) }))
    .filter(({ t }) => Number.isFinite(t) && t >= series.start && t <= series.end)
    .sort((a, z) => a.t - z.t)
    .map(({ b }) => b);
  // The time axis here is linear, so the time-span form of the shared spacing rule is the painted one.
  return anchorPeriodLabels(placePeriodLabels(collapseDuplicateTransitions(inSpan), span), span, series.end);
}

export default function ProjectedFinalPointsChart({
  input,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  finalScore = null,
  periodBoundaries,
}: ProjectedFinalPointsChartProps) {
  const full = useMemo(() => buildProjectedFinalPointsSeries(input), [input]);
  const markers = useMemo(() => drawnPeriodMarkers(full, periodBoundaries), [full, periodBoundaries]);
  if (!full.supported) return null;

  const { home: homeStroke, away: awayStroke } = projectedTeamStrokes(homeColor, awayColor);
  const span = Math.max(1, full.end - full.start);
  const x = (t: number) => LEFT + ((Math.min(Math.max(t, full.start), full.end) - full.start) / span) * (RIGHT - LEFT);
  const y = (v: number) => BOTTOM - (v / full.yMax) * (BOTTOM - TOP);

  const reading = full.latest;
  const actual = full.latestActual;
  const after = full.phase === "after";
  const showActual = full.phase !== "before";
  // Before the score floor there is no actual line, so the legend does not name one.
  const actualDrawn = showActual && full.actualSteps.length > 0;
  // The last recorded score is the final only when it equals the page's own final. A completion
  // timestamp does not make an earlier observation final: a game whose last recorded row is 26–7
  // (before the extra point) still ended 27–7.
  const recordedIsFinal =
    !!finalScore && !!actual && actual.home === finalScore.home && actual.away === finalScore.away;
  const showFinalApart = after && !!finalScore && !recordedIsFinal;
  const markerRows = markers.reduce((n, m) => Math.max(n, m.labelRow + 1), 0);

  return (
    <section
      className="rounded-xl border border-surface-border bg-surface-card p-4"
      aria-labelledby="projected-final-points-title"
      data-projected-final-points={full.phase}
    >
      <h3 id="projected-final-points-title" className="text-base font-semibold text-text-primary">
        Projected final points
      </h3>

      <div className="mt-3 grid grid-cols-2 gap-3" aria-live="polite" data-testid="projected-reading">
        {([
          ["home", homeTeam, homeStroke],
          ["away", awayTeam, awayStroke],
        ] as const).map(([key, name, stroke]) => (
          <div key={key} data-side={key}>
            <div className="flex items-center gap-1.5 text-sm font-medium" style={{ color: stroke }}>
              {/* The key: this team's line, beside its name. */}
              <span
                aria-hidden="true"
                data-team-key={key}
                className="h-[3px] w-3 shrink-0 rounded-full"
                style={{ backgroundColor: stroke }}
              />
              <span className="min-w-0 truncate">{name}</span>
            </div>
            <div className="text-2xl font-semibold tabular-nums text-text-primary">
              {points(reading[key])}
            </div>
            <div className="text-xs text-text-secondary">projected final</div>
            {/* Only a recorded score is printed. Without one there is no "— final" placeholder:
                a dash beside "final" reads as a result nobody recorded. */}
            {showActual && actual && (
              <div className="text-sm tabular-nums text-text-primary" data-actual={key}>
                {actual[key]} {!after ? "scored" : recordedIsFinal ? "final" : "last recorded"}
              </div>
            )}
            {showFinalApart && finalScore && (
              <div className="text-sm tabular-nums text-text-primary" data-final={key}>
                {finalScore[key]} final
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="mt-2 text-xs text-text-secondary" data-testid="projected-stamp">
        {`${readingLabel(full)} · recorded ${formatProjectionTime(reading.at)}`}
        {full.latestIntervalUnavailable && (
          <>
            <br />
            No usable projection since then
          </>
        )}
      </p>

      {/* The marker labels get their own rows above the plot: the plot stretches to its box, and
          text inside it would stretch with it. Positions are the plot's own x, as percentages. */}
      {markerRows > 0 && (
        <div
          className="relative mt-3"
          style={{ height: markerRows * PERIOD_LABEL_ROW_HEIGHT_PX }}
          aria-hidden="true"
          data-testid="projected-period-labels"
        >
          {markers.map((m) => (
            <span
              key={`label-${m.timestamp}`}
              data-period-label={m.label}
              className={`absolute whitespace-nowrap text-[10px] font-semibold leading-[13px] text-text-secondary ${
                m.labelPosition === "insideTopRight" ? "-translate-x-full pr-0.5" : "pl-0.5"
              }`}
              style={{ left: `${(x(Date.parse(m.timestamp)) / W) * 100}%`, top: m.labelRow * PERIOD_LABEL_ROW_HEIGHT_PX }}
            >
              {periodBoundaryChipLabel(m)}
            </span>
          ))}
        </div>
      )}
      <div className={`relative h-64 sm:h-80 ${markerRows > 0 ? "mt-0.5" : "mt-3"}`} data-testid="projected-plot">
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
        {markers.map((m) => (
          <line
            key={`period-${m.timestamp}`}
            data-period-marker={m.label}
            x1={x(Date.parse(m.timestamp))}
            x2={x(Date.parse(m.timestamp))}
            y1={TOP}
            y2={BOTTOM}
            stroke="var(--text-muted)"
            strokeWidth={1}
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {actualDrawn &&
          ([
            ["home", homeStroke],
            ["away", awayStroke],
          ] as const).map(([key, stroke]) => (
            <path
              key={`actual-${key}`}
              data-series={`actual-${key}`}
              d={actualPath(full.actualSteps, key, full.end, x, y)}
              fill="none"
              stroke={stroke}
              strokeWidth={2.5}
              strokeDasharray="6 5"
              strokeOpacity={0.75}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        {([
            ["home", homeStroke],
            ["away", awayStroke],
          ] as const).map(([key, stroke]) =>
            full.segments.map((seg, i) =>
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
        {full.withheld.map((w) => (
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
      </svg>
      </div>
      <div className="flex justify-between pl-6 text-xs text-text-secondary" aria-hidden="true">
        <span>{formatProjectionTime(full.start)}</span>
        <span>{formatProjectionTime(full.end)}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        <span>━ Projected final</span>
        {actualDrawn && <span>┅ Actual score</span>}
        <span>Gaps are not joined</span>
      </div>

      {markers.length > 0 && (
        <p className="sr-only" data-testid="projected-period-markers-text">
          Game state marked on the chart:{" "}
          {markers.map((m) => `${m.label} ${markerTiming(m)} ${formatProjectionTime(Date.parse(m.timestamp))}`).join(", ")}.
        </p>
      )}

      <details className="mt-3 text-xs text-text-secondary">
        <summary className="cursor-pointer">How to read this</summary>
        <p className="mt-1" data-testid="projected-source">
          Projection source: {full.sourceName}. Estimated from that one sportsbook&apos;s expected winning margin and total
          points for the full game, recorded together, which imply a final score for each team. It is not the Bain Luck probability above and not an
          average of sources.
        </p>
        <p className="mt-1">
          The solid lines are the projections; the dashed steps are the score so far. A break in a line means that reading
          was missing or could not be right, such as a projection below points already scored. The last projection is never
          joined to the final score.
          {markers.length > 0 &&
            " The thin vertical rules mark each quarter, halftime or overtime where it was first seen in progress, which can be a little after it began."}
        </p>
      </details>
    </section>
  );
}
