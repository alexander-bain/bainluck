/**
 * #4974 slice 1 (web, #10487) — a finished game's recorded checkpoints.
 *
 * `GET /api/events/{id}/publications` serves the blend probability rows the
 * backend recorded for one event, in `rev` order. Each `t` is the row's
 * `recorded_at`, stamped at INSERT before COMMIT (`time_basis`), so it is a
 * checkpoint and nothing more: not when a reader could first see the value,
 * and not the start of an interval in which the value held. `rev` counts bag
 * commits only, so two neighbouring rows say nothing about what was published
 * between them either (root's A→B→A counterexample, 2026-10-04).
 *
 * So the chart draws each checkpoint as a separate dot and nothing joins two
 * of them; a scrub answers only at a checkpoint, with that checkpoint's own
 * value and clock. Nothing here carries, holds or interpolates a value — the
 * accepted boundary is `4974-UX-READER-SLICE-1-BOUNDARY.md`, section B.
 *
 * PURE: no I/O, no React.
 */

import type { EventPublicationsResponse, PublicationVertex } from "./types";

/** A served vertex with its time already parsed. `rev`, `t` and `p` are never altered. */
export interface CheckpointVertex extends PublicationVertex {
  tMs: number;
}

/** The latest checkpoint by `t`; equal `t` goes to the greatest `rev`. */
export function latestCheckpoint<T extends CheckpointVertex>(vertices: ReadonlyArray<T>): T | null {
  let best: T | null = null;
  for (const v of vertices) {
    if (best === null || v.tMs > best.tMs || (v.tMs === best.tMs && v.rev > best.rev)) best = v;
  }
  return best;
}

/** How far (px) the cursor may be from a checkpoint and still read it. */
export const CHECKPOINT_HIT_RADIUS_PX = 8;

/**
 * The checkpoints a chart may draw, or `null` when it must draw today's chart.
 *
 * `null` unless the game is finished, the response is schema 1, not truncated,
 * every vertex is well-formed, and there are at least two. A malformed vertex
 * refuses the whole response rather than being skipped: the backend omits rows
 * with no blend itself, so a bad one here means the payload is not the
 * contract, and the honest fallback is the chart that does not depend on it.
 * Served (`rev`) order is preserved.
 */
export function eligibleCheckpoints(
  response: EventPublicationsResponse | null | undefined,
  opts: { finished: boolean },
): CheckpointVertex[] | null {
  if (!opts.finished || !response) return null;
  if (response.schema_version !== 1 || response.truncated !== false) return null;
  if (!Array.isArray(response.vertices) || response.vertices.length < 2) return null;
  const out: CheckpointVertex[] = [];
  for (const v of response.vertices) {
    if (!v || !Number.isInteger(v.rev)) return null;
    if (typeof v.p !== "number" || !Number.isFinite(v.p) || v.p < 0 || v.p > 1) return null;
    const tMs = typeof v.t === "string" ? Date.parse(v.t) : NaN;
    if (!Number.isFinite(tMs)) return null;
    out.push({ rev: v.rev, t: v.t, p: v.p, tMs });
  }
  return out;
}

/**
 * The recorded window: [earliest `t`, latest `t`]. Vertices arrive in `rev`
 * order and `t` may be non-monotonic, so this is never the first and last
 * array element's time.
 */
export function recordedWindow(vertices: ReadonlyArray<CheckpointVertex>): { startMs: number; endMs: number } | null {
  if (vertices.length === 0) return null;
  let startMs = Infinity;
  let endMs = -Infinity;
  for (const v of vertices) {
    if (v.tMs < startMs) startMs = v.tMs;
    if (v.tMs > endMs) endMs = v.tMs;
  }
  return { startMs, endMs };
}

/** Inside the recorded window, both ends included. */
export function insideRecordedWindow(ms: number, window: { startMs: number; endMs: number } | null): boolean {
  return window !== null && ms >= window.startMs && ms <= window.endMs;
}

/**
 * Whether the closed span between two instants touches the recorded window.
 *
 * Two legacy points on either side of the window are each outside it, yet the
 * segment, carry or crossing between them would run through it — a window
 * inside one minute (20:15:10–20:15:50 between the 20:15 and 20:16 rows) has
 * no row of its own to break on. So a legacy pair is judged by its span, never
 * by its endpoints alone. A single instant is the span `[ms, ms]`.
 */
export function spanTouchesRecordedWindow(
  aMs: number,
  bMs: number,
  window: { startMs: number; endMs: number } | null,
): boolean {
  if (window === null) return false;
  return Math.min(aMs, bMs) <= window.endMs && Math.max(aMs, bMs) >= window.startMs;
}

/**
 * The checkpoint a cursor at `cursorPx` reads, or `null`.
 *
 * The nearest vertex whose x is within `radiusPx`; beyond it, nothing — never
 * the latest checkpoint at or before the cursor, which would be a held value.
 * Equal distances (including two vertices at the same `t`) go to the greatest
 * `rev`. The chosen vertex is returned as served, never merged or averaged.
 */
export function publicationReadoutAt<T extends CheckpointVertex>(
  vertices: ReadonlyArray<T>,
  cursorPx: number,
  xOf: (vertex: T) => number | null,
  radiusPx: number = CHECKPOINT_HIT_RADIUS_PX,
): T | null {
  if (!Number.isFinite(cursorPx)) return null;
  let best: T | null = null;
  let bestDistance = Infinity;
  for (const vertex of vertices) {
    const x = xOf(vertex);
    if (x === null || !Number.isFinite(x)) continue;
    const distance = Math.abs(x - cursorPx);
    if (distance > radiusPx) continue;
    if (best === null || distance < bestDistance || (distance === bestDistance && vertex.rev > best.rev)) {
      best = vertex;
      bestDistance = distance;
    }
  }
  return best;
}

/** The accepted boundary's clock zone (section B): Pacific, whatever the reader's own zone. */
export const CHECKPOINT_CLOCK_TIME_ZONE = "America/Los_Angeles";

const checkpointClockFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: CHECKPOINT_CLOCK_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/**
 * A checkpoint's clock: `h:mm a` in Pacific time, minutes only, no verb. It is
 * the vertex's own time, never the cursor's.
 */
export function checkpointClockLabel(vertex: Pick<CheckpointVertex, "tMs">): string {
  return checkpointClockFormat.format(new Date(vertex.tMs));
}

/** What a snapped scrub shows: the checkpoint, where the cursor is drawn, and its clock. */
export interface PublicationReadout<T extends CheckpointVertex = CheckpointVertex> {
  vertex: T;
  /** The cursor is drawn here — the checkpoint's own x, not the pointer's. */
  x: number;
  clock: string;
}

export function publicationReadout<T extends CheckpointVertex>(
  vertices: ReadonlyArray<T>,
  cursorPx: number,
  xOf: (vertex: T) => number | null,
): PublicationReadout<T> | null {
  const vertex = publicationReadoutAt(vertices, cursorPx, xOf);
  if (!vertex) return null;
  const x = xOf(vertex);
  if (x === null) return null;
  return { vertex, x, clock: checkpointClockLabel(vertex) };
}

/**
 * The last row at or before `tMs` (rows sorted ascending), or `null` before the
 * first row.
 */
export function rowIndexAt(tMs: number, rowStartMs: ReadonlyArray<number>): number | null {
  const n = rowStartMs.length;
  if (n === 0 || !Number.isFinite(tMs) || tMs < rowStartMs[0]) return null;
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (rowStartMs[mid] <= tMs) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/**
 * Where an instant sits on the chart's minute-category axis.
 *
 * Rows are one per minute, sorted, and the renderer places each at `rowXs[i]`.
 * Between two rows the axis is linear in time, so an instant inside a minute
 * lands between that minute's x and the next one's. Past the last row it may
 * extend at most one minute, at the last step's spacing (a checkpoint stamped
 * at 20:15:30 belongs to the 20:15 column the way every other series' point
 * does). Before the first row, or with no laid-out neighbour, `null`: not drawn
 * and not readable.
 */
export function timeToChartX(
  tMs: number,
  rowStartMs: ReadonlyArray<number>,
  rowXs: ReadonlyArray<number | null>,
): number | null {
  const n = rowStartMs.length;
  const lo = rowIndexAt(tMs, rowStartMs);
  if (lo === null) return null;
  const x0 = rowXs[lo];
  if (x0 === null || x0 === undefined || !Number.isFinite(x0)) return null;
  if (tMs === rowStartMs[lo]) return x0;
  if (lo < n - 1) {
    const x1 = rowXs[lo + 1];
    if (x1 === null || x1 === undefined || !Number.isFinite(x1)) return null;
    return x0 + ((tMs - rowStartMs[lo]) / (rowStartMs[lo + 1] - rowStartMs[lo])) * (x1 - x0);
  }
  if (n < 2 || tMs - rowStartMs[lo] >= 60_000) return null;
  const xp = rowXs[lo - 1];
  if (xp === null || xp === undefined || !Number.isFinite(xp)) return null;
  return x0 + ((tMs - rowStartMs[lo]) / (rowStartMs[lo] - rowStartMs[lo - 1])) * (x0 - xp);
}

/**
 * The instant under a pointer at `x` — `timeToChartX` read backwards.
 *
 * Linear in time between two laid-out rows; past the last row at most one
 * minute, at the last step's spacing; before the first row, or with no
 * laid-out neighbour, `null`. A scrub needs the pointer's own instant: the
 * minute row recharts reports as active can sit outside the recorded window
 * while the pointer is inside it.
 */
export function chartXToTime(
  x: number,
  rowStartMs: ReadonlyArray<number>,
  rowXs: ReadonlyArray<number | null>,
): number | null {
  const n = rowStartMs.length;
  if (!Number.isFinite(x) || n === 0) return null;
  const at = (i: number) => {
    const v = rowXs[i];
    return v === null || v === undefined || !Number.isFinite(v) ? null : v;
  };
  const x0 = at(0);
  if (x0 === null || x < x0) return null;
  for (let i = 0; i < n - 1; i++) {
    const a = at(i);
    const b = at(i + 1);
    if (a === null || b === null) return null;
    if (x <= b) {
      if (b === a) return rowStartMs[i];
      return rowStartMs[i] + ((x - a) / (b - a)) * (rowStartMs[i + 1] - rowStartMs[i]);
    }
  }
  const last = at(n - 1);
  if (last === null) return null;
  if (x === last) return rowStartMs[n - 1];
  if (n < 2) return null;
  const prev = at(n - 2);
  if (prev === null || last === prev) return null;
  const tMs = rowStartMs[n - 1] + ((x - last) / (last - prev)) * (rowStartMs[n - 1] - rowStartMs[n - 2]);
  return tMs - rowStartMs[n - 1] >= 60_000 ? null : tMs;
}

/**
 * What a pointer at `chartX` reads on a chart with recorded checkpoints: the
 * checkpoint within reach (`publicationReadout`), or none — and, with none,
 * whether the blend must read nothing because the pointer's own instant is
 * inside the recorded window. recharts reports the nearest MINUTE row, which
 * can sit outside the window (and hold a legacy value) while the pointer is
 * 30 s inside it; only the pointer's instant answers that.
 */
export function scrubAtPointer<T extends CheckpointVertex>(
  drawable: ReadonlyArray<T>,
  window: { startMs: number; endMs: number } | null,
  chartX: number,
  rowStartMs: ReadonlyArray<number>,
  rowXs: ReadonlyArray<number | null>,
): { readout: PublicationReadout<T> | null; blendWithheld: boolean } {
  const readout =
    drawable.length > 0 ? publicationReadout(drawable, chartX, (v) => timeToChartX(v.tMs, rowStartMs, rowXs)) : null;
  if (readout) return { readout, blendWithheld: false };
  const cursorMs = chartXToTime(chartX, rowStartMs, rowXs);
  return { readout: null, blendWithheld: cursorMs !== null && insideRecordedWindow(cursorMs, window) };
}
