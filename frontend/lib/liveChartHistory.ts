import type { LiveStreamFrame } from "./liveStreamController";

// One hour at the nominal five-second publication cadence. This is a bound on
// session memory, not a sampling rule: every accepted frame keeps its own time.
export const MAX_LIVE_CHART_FRAMES = 720;
export type LiveChartPoint = { timestamp: string; home_probability: number };
export type ChartHistory = { aggregate_line?: LiveChartPoint[] | null };

/** Record the published BLEND, never the individual venue's source_value. */
export function rememberLiveChartFrame(
  points: LiveChartPoint[], frame: LiveStreamFrame, eventId: number,
): LiveChartPoint[] {
  if (frame.event_id !== eventId || frame.status !== "live" ||
      typeof frame.p !== "number" || !Number.isFinite(frame.p) ||
      frame.p < 0 || frame.p > 1 || !Number.isFinite(Date.parse(frame.updated_at))) {
    return points;
  }
  const instant = Date.parse(frame.updated_at);
  const existing = points.find(point => Date.parse(point.timestamp) === instant);
  if (existing?.home_probability === frame.p) return points;
  return [
    ...points.filter(point => Date.parse(point.timestamp) !== instant),
    { timestamp: frame.updated_at, home_probability: frame.p },
  ].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .slice(-MAX_LIVE_CHART_FRAMES);
}

/**
 * Add actual publications received while this page was open. Polls can be
 * coarser than push; retaining the session's observations preserves a real
 * spike and reversal in the input series between polls. The main chart still
 * buckets by minute; preserving subminute ink is a separate renderer change.
 * Persisted history wins exact-time ties.
 * Never move an old endpoint to a new value or manufacture a timestamp.
 */
export function mergeLiveChartHistory<T extends ChartHistory>(
  history: T | undefined, points: LiveChartPoint[] = [],
): T | undefined {
  if (!history || points.length === 0) return history;
  const served = history.aggregate_line ?? [];
  const instants = new Set(served.map(point => Date.parse(point.timestamp)));
  const added = points.filter(point => !instants.has(Date.parse(point.timestamp)));
  if (added.length === 0) return history;
  return {
    ...history,
    aggregate_line: [...served, ...added]
      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp)),
  };
}
