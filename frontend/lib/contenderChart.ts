/**
 * The contender trend chart — legend, lines and timeframe (UX-P132 re-skin).
 *
 * Structure adopted from Alex's Kalshi reference (`_KALSHI-REFERENCE-baseball-champion.png`):
 * legend of the top three above the chart, exactly three lines drawn in the
 * legend's colours with endpoint dots, timeframe selector bottom-right, then a
 * collapsed list of three rows and a "show all N" expander.
 *
 * **Adaptation, not imitation** — the ruling is explicit. Kalshi's rows carry
 * two-sided green/red price pills; that is a trading format and we do not copy
 * it. Our rows show one blended probability per contender. What is taken is the
 * STRUCTURE: legend → three-line chart → collapsed list.
 *
 * Standing doctrine still governs everything numeric:
 *
 * - **Fixed 0-100 axis, always.** `chartGeometry` never auto-scales to the data
 *   range. An auto-scaled axis turns a 2pp wiggle into a cliff, which on a page
 *   whose subject is movement is worse than showing nothing.
 * - **No smoothing, ever.** Straight segments between real observations. The
 *   reference's line is visibly jagged and that is the point — movement IS the
 *   product, and a smoother is a machine for hiding it.
 * - **Gaps stay gaps.** A day with no reading is absent, never interpolated
 *   and never carried forward.
 */

import type { TournamentRow, TournamentTrendPoint } from "./tournament";

/** How many contenders the legend names and the chart draws. Kalshi's own
 *  reference shows exactly three, which settled the 3-vs-5 question. */
export const CHART_SERIES_COUNT = 3;

/** How many rows the collapsed board shows before "show all N". Same three, so
 *  the list and the chart describe the same set — a list showing five while the
 *  chart drew three would invite the reader to look for two missing lines. */
export const COLLAPSED_ROW_COUNT = 3;

export const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
] as const;

export type Timeframe = "1D" | "1W" | "1M" | "ALL";

export const TIMEFRAMES: Timeframe[] = ["1D", "1W", "1M", "ALL"];

const TIMEFRAME_DAYS: Record<Timeframe, number | null> = {
  "1D": 1,
  "1W": 7,
  "1M": 30,
  ALL: null,
};

export interface ChartSeries {
  entityKey: string;
  displayName: string;
  color: string;
  probability: number | null;
  isLive: boolean;
  points: TournamentTrendPoint[];
}

/**
 * The top N rows as chart series, in board order.
 *
 * Rows without a probability (settled) are skipped: a result is not a
 * standing, and a settled player has no live line to draw.
 */
export function chartSeries(rows: TournamentRow[], limit = CHART_SERIES_COUNT): ChartSeries[] {
  return rows
    .filter((row) => row.probability !== null)
    .slice(0, limit)
    .map((row, index) => ({
      entityKey: row.entity_key,
      displayName: row.display_name,
      color: SERIES_COLORS[index % SERIES_COLORS.length],
      probability: row.probability,
      isLive: row.probability_is_live === true,
      points: Array.isArray(row.trend) ? row.trend : [],
    }));
}

/**
 * Points inside a timeframe, measured back from the LATEST OBSERVATION rather
 * than from now.
 *
 * Anchoring on `now` looks more correct and is worse here: #2199 has these
 * fields dark for 8-32 days, so a "1M" window measured from today would be
 * empty for markets that have a full month of history ending three weeks ago.
 * The chart would go blank and read as "no data" when the truth is "no RECENT
 * data" — which the staleness banner is already saying, properly, in words.
 */
export function pointsInTimeframe(
  points: TournamentTrendPoint[],
  timeframe: Timeframe
): TournamentTrendPoint[] {
  if (!Array.isArray(points) || points.length === 0) return [];
  const days = TIMEFRAME_DAYS[timeframe];
  if (days === null) return points;

  const last = points[points.length - 1];
  const end = new Date(`${last.date}T00:00:00Z`).getTime();
  if (Number.isNaN(end)) return points;
  const start = end - (days - 1) * 24 * 60 * 60 * 1000;

  return points.filter((point) => {
    const at = new Date(`${point.date}T00:00:00Z`).getTime();
    return !Number.isNaN(at) && at >= start;
  });
}

/**
 * Whether a timeframe has enough data to draw. A single point is not a line,
 * and joining it to an assumed origin would draw a movement that never
 * happened — so the selector offers it disabled rather than lying.
 */
export function timeframeIsDrawable(
  series: ChartSeries[],
  timeframe: Timeframe
): boolean {
  return series.some((entry) => pointsInTimeframe(entry.points, timeframe).length >= 2);
}

export interface ChartGeometry {
  /** Shared x-domain across all series so the lines are comparable. */
  dates: string[];
  width: number;
  height: number;
}

/**
 * The shared x-domain: every date any drawn series observed, sorted.
 *
 * Built as a union rather than per-series so two players' lines line up in
 * time. Giving each line its own x-scale would put Monday under Thursday and
 * make crossing lines mean nothing.
 */
export function chartGeometry(
  series: ChartSeries[],
  timeframe: Timeframe,
  width: number,
  height: number
): ChartGeometry {
  const dates = new Set<string>();
  for (const entry of series) {
    for (const point of pointsInTimeframe(entry.points, timeframe)) {
      dates.add(point.date);
    }
  }
  return { dates: Array.from(dates).sort(), width, height };
}

/**
 * One series as SVG polyline points on a FIXED 0-100 y-axis.
 *
 * Returns "" for fewer than two points. x is positioned by the point's place in
 * the SHARED date domain, so a series that started late begins part-way across
 * instead of being stretched to fill the width.
 */
export function seriesPoints(
  entry: ChartSeries,
  geometry: ChartGeometry,
  timeframe: Timeframe
): string {
  const points = pointsInTimeframe(entry.points, timeframe);
  if (points.length < 2 || geometry.dates.length < 2) return "";
  const span = geometry.dates.length - 1;

  return points
    .map((point) => {
      const index = geometry.dates.indexOf(point.date);
      if (index < 0) return null;
      const clamped = Math.max(0, Math.min(1, point.probability));
      const x = (index * geometry.width) / span;
      const y = geometry.height - clamped * geometry.height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((value): value is string => value !== null)
    .join(" ");
}

/** The last plotted coordinate — the reference's endpoint dot. */
export function seriesEndpoint(
  entry: ChartSeries,
  geometry: ChartGeometry,
  timeframe: Timeframe
): { x: number; y: number } | null {
  const drawn = seriesPoints(entry, geometry, timeframe);
  if (drawn === "") return null;
  const last = drawn.split(" ").pop();
  if (!last) return null;
  const [x, y] = last.split(",").map(Number);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

/** Short legend name: `Aryna Sabalenka` -> `A. Sabalenka`. */
export function legendName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  if (parts.length < 2) return displayName;
  const surname = parts.slice(1).join(" ");
  return `${parts[0][0]}. ${surname}`;
}
