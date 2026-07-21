// Chart time-range windowing for the probability-path charts (#L2-137,
// chart-excellence Phase 0). A settled event's path spans its whole run, so a
// market that sat near a flat probability for months and then spiked at
// resolution renders as a long flatline + an unreadable vertical spike at the
// right edge. Time-range chips let the reader zoom to the part that carries the
// story; this module is the pure windowing logic behind them.

import type { FuturesOutcomeHistory } from "@/lib/types";

export type ChartRangeKey = "all" | "1M" | "1W" | "1D" | "since_start";

export interface ChartRange {
  key: ChartRangeKey;
  label: string;
  /** Window length in ms, measured back from the last snapshot. null = special. */
  ms: number | null;
}

const DAY = 24 * 60 * 60 * 1000;

// Ordered widest → narrowest, with the event-anchored range last.
export const CHART_RANGES: ChartRange[] = [
  { key: "all", label: "All", ms: null },
  { key: "1M", label: "1M", ms: 30 * DAY },
  { key: "1W", label: "1W", ms: 7 * DAY },
  { key: "1D", label: "1D", ms: DAY },
  { key: "since_start", label: "Since start", ms: null },
];

function tsMs(iso: string): number {
  return new Date(iso).getTime();
}

/** The last (max) snapshot time across every outcome, or null if none exist. */
export function latestSnapshotTime(outcomes: FuturesOutcomeHistory[]): number | null {
  let max = -Infinity;
  for (const o of outcomes) {
    for (const p of o.history) {
      const t = tsMs(p.timestamp);
      if (t > max) max = t;
    }
  }
  return max === -Infinity ? null : max;
}

/**
 * Return a copy of `outcomes` whose history is clipped to the selected range.
 *
 * The window is anchored to the LAST snapshot (resolution time), not wall-clock
 * `now` — a settled event's data ends at resolution, so a now-anchored window
 * would fall past all the data and render empty. To keep each line spanning the
 * full visible width, the last point BEFORE the window is carried forward and
 * re-stamped at the window start (step-interpolation-correct).
 *
 * `all` and a `since_start` with no `startMs` return the input unchanged.
 */
export function windowOutcomeHistory(
  outcomes: FuturesOutcomeHistory[],
  range: ChartRangeKey,
  startMs?: number | null,
): FuturesOutcomeHistory[] {
  const anchor = latestSnapshotTime(outcomes);
  if (anchor === null) return outcomes;

  let windowStart: number;
  if (range === "all") return outcomes;
  if (range === "since_start") {
    if (startMs == null) return outcomes;
    windowStart = startMs;
  } else {
    const r = CHART_RANGES.find((x) => x.key === range);
    if (!r || r.ms == null) return outcomes;
    windowStart = anchor - r.ms;
  }

  return outcomes.map((o) => {
    const inWindow = o.history.filter((p) => tsMs(p.timestamp) >= windowStart);
    // Carry the last pre-window point forward to the window's left edge so the
    // line doesn't start floating mid-chart.
    const firstInWindow = inWindow.length > 0 ? tsMs(inWindow[0].timestamp) : Infinity;
    let anchorPoint: (typeof o.history)[number] | null = null;
    for (const p of o.history) {
      if (p.probability == null) continue;
      const t = tsMs(p.timestamp);
      if (t < windowStart) anchorPoint = p;
    }
    const carried =
      anchorPoint && firstInWindow > windowStart
        ? [{ ...anchorPoint, timestamp: new Date(windowStart).toISOString() }]
        : [];
    return { ...o, history: [...carried, ...inWindow] };
  });
}

/**
 * Which ranges have enough data to be worth offering, given the span of the
 * data. Ranges wider than the data (e.g. "1M" on a 3-day event) are dropped so
 * we never show a chip that renders identically to "All". `since_start` is
 * included only when an event start exists.
 */
export function availableRanges(
  outcomes: FuturesOutcomeHistory[],
  hasStart: boolean,
): ChartRange[] {
  const anchor = latestSnapshotTime(outcomes);
  let minT = Infinity;
  for (const o of outcomes) {
    for (const p of o.history) {
      const t = tsMs(p.timestamp);
      if (t < minT) minT = t;
    }
  }
  const span = anchor !== null && minT !== Infinity ? anchor - minT : 0;
  return CHART_RANGES.filter((r) => {
    if (r.key === "all") return true;
    if (r.key === "since_start") return hasStart;
    // Keep a range only if the data is meaningfully wider than it.
    return r.ms != null && span > r.ms * 1.1;
  });
}
