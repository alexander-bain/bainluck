import type { LiveStreamFrame } from "./liveStreamController";
import type { WinProbHistoryPoint } from "./types";

// One hour at the nominal five-second publication cadence. This is a bound on
// session memory, not a sampling rule: every accepted frame keeps its own time.
export const MAX_LIVE_CHART_FRAMES = 720;
export type LiveChartPoint = { timestamp: string; home_probability: number };

/**
 * One accepted publication: the BLEND the event stamped, and — when the frame
 * carried a usable one — the venue reading behind it.
 *
 * The two are different quantities and they go to different places. `p` is the
 * answer ("the blend is the product"); `source_probability` is one feed's own
 * price, the same number the backend persists into
 * `win_prob_history[<source>][].home_probability` (`live_blend_refresh` stamps
 * both from one reading). Keeping the source reading here does not put it on
 * the plot — `mergeLiveChartHistory` decides that, under one narrow rule.
 */
export type LiveChartFrame = LiveChartPoint & {
  source?: string;
  source_probability?: number;
};

export type ChartHistory = {
  aggregate_line?: LiveChartPoint[] | null;
  win_prob_history?: Record<string, WinProbHistoryPoint[]> | null;
};

/** Record the published BLEND, never the individual venue's source_value. */
export function rememberLiveChartFrame(
  points: LiveChartFrame[], frame: LiveStreamFrame, eventId: number,
): LiveChartFrame[] {
  if (frame.event_id !== eventId || frame.status !== "live" ||
      typeof frame.p !== "number" || !Number.isFinite(frame.p) ||
      frame.p < 0 || frame.p > 1 || !Number.isFinite(Date.parse(frame.updated_at))) {
    return points;
  }
  const instant = Date.parse(frame.updated_at);
  const existing = points.find(point => Date.parse(point.timestamp) === instant);
  if (existing?.home_probability === frame.p) return points;
  const next: LiveChartFrame = {
    timestamp: frame.updated_at, home_probability: frame.p,
  };
  // Carried on the same validity bar as `p`: a probability, finite, in range.
  // A frame missing it is still a perfectly good blend observation — it simply
  // extends nothing below.
  if (typeof frame.source === "string" && frame.source !== "" &&
      typeof frame.source_value === "number" && Number.isFinite(frame.source_value) &&
      frame.source_value >= 0 && frame.source_value <= 1) {
    next.source = frame.source;
    next.source_probability = frame.source_value;
  }
  return [
    ...points.filter(point => Date.parse(point.timestamp) !== instant),
    next,
  ].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .slice(-MAX_LIVE_CHART_FRAMES);
}

/**
 * Extend the SERVED source series with this session's own readings of them.
 *
 * WHY THIS EXISTS (#8066's remainder, handed over by ux/1443). The backend
 * emits `aggregate_line` only where it blended two or more sources. #920 put
 * the stream's blend into that array, which on a single-source event drew a
 * 2-vertex line under the blend's name over the real one; #8066 fixed the
 * chart to require the blend to be the BACKEND's. Correct — and it costs a
 * single-source live page its push speed, because the only line on that plot
 * is the source line, and nothing was feeding it. It then advanced on the 32 s
 * poll while the page held a reading three seconds old. This pays that back.
 *
 * TWO RULES, BOTH LOAD-BEARING:
 *
 *   1. NEVER MINT A SERIES. A source the payload does not already carry is
 *      skipped, however good its frames. Creating `win_prob_history[x]` from
 *      two pushed frames would put a 2-vertex line on the plot with no legend
 *      entry, no colour and no served history behind it — #8066 again, wearing
 *      the source's face instead of the blend's.
 *   2. STRICTLY NEWER THAN THE SERVED EDGE. A live payload already ends in the
 *      backend's synthetic `live_edge` point at "now" carrying the last real
 *      value, so a pushed reading stamped just before it would insert BEHIND a
 *      stale endpoint and draw the line backwards. Ties go to the served point
 *      for the same reason they do on the aggregate above.
 *
 * What lands is an observation, not a delivery: these frames are stamped at
 * `live_blend_refresh`'s write time, so they carry no `live_edge` flag and
 * `chartObservationSupport` counts them as the real readings they are. Nothing
 * is carried forward or interpolated — `away_probability` is `null` because
 * the frame does not carry one, never the previous point's.
 */
function extendServedSourceSeries(
  served: Record<string, WinProbHistoryPoint[]> | null | undefined,
  points: LiveChartFrame[],
): Record<string, WinProbHistoryPoint[]> | null {
  if (!served) return null;
  let next: Record<string, WinProbHistoryPoint[]> | null = null;
  for (const [source, series] of Object.entries(served)) {
    if (!series?.length) continue;
    const edge = Date.parse(series[series.length - 1].timestamp);
    if (!Number.isFinite(edge)) continue;
    // `points` is kept sorted by `rememberLiveChartFrame`, so a filter
    // preserves that order and the concatenation below needs no re-sort.
    const added = points
      .filter(point =>
        point.source === source &&
        typeof point.source_probability === "number" &&
        Date.parse(point.timestamp) > edge)
      .map(point => ({
        timestamp: point.timestamp,
        home_probability: point.source_probability as number,
        away_probability: null,
      }));
    if (added.length === 0) continue;
    next ??= { ...served };
    next[source] = [...series, ...added];
  }
  return next;
}

/**
 * Add actual publications received while this page was open. Polls can be
 * coarser than push; retaining the session's observations preserves a real
 * spike and reversal in the input series between polls. The main chart still
 * buckets by minute; preserving subminute ink is a separate renderer change.
 * Persisted history wins exact-time ties.
 * Never move an old endpoint to a new value or manufacture a timestamp.
 *
 * `history` is the SERVED response, so `aggregate_line` here is the backend's
 * own — the same question `page.tsx` answers for the chart as
 * `backendBlendServed` (#8066). Where the backend blended, the blend line
 * carries the push and the source series are left exactly as served. Where it
 * did not, the source line is the line the reader reads the match off, and it
 * is the one that has to keep up.
 */
export function mergeLiveChartHistory<T extends ChartHistory>(
  history: T | undefined, points: LiveChartFrame[] = [],
): T | undefined {
  if (!history || points.length === 0) return history;
  const served = history.aggregate_line ?? [];
  const instants = new Set(served.map(point => Date.parse(point.timestamp)));
  const added = points.filter(point => !instants.has(Date.parse(point.timestamp)));
  const extended = served.length === 0
    ? extendServedSourceSeries(history.win_prob_history, points)
    : null;
  if (added.length === 0 && extended === null) return history;
  const next = { ...history };
  if (added.length > 0) {
    // Plot points, not frames: the source reading rides in the buffer so the
    // branch above can use it, and must not leak into the blend's own array.
    next.aggregate_line = [...served, ...added.map(
      ({ timestamp, home_probability }) => ({ timestamp, home_probability }),
    )].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }
  if (extended !== null) next.win_prob_history = extended;
  return next;
}
