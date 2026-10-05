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

import { format } from "date-fns";

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

/**
 * A checkpoint's clock: `h:mm a`, minutes only, no verb — the same format the
 * readout under the chart prints for every other point (`GamePlayCard`). It is
 * the vertex's own time, never the cursor's.
 */
export function checkpointClockLabel(vertex: Pick<CheckpointVertex, "tMs">): string {
  return format(new Date(vertex.tMs), "h:mm a");
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
