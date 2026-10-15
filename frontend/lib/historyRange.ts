/**
 * "FULL" ASKS THE SERVER FOR THE QUESTION'S WHOLE HISTORY (#683, Root ruling B).
 *
 * THE DEFECT. EvolutionView's "Full" asked for a fixed `hours=4320`. On a
 * settled question whose recovered archive intervals are 189 days old, that
 * window ends before the archive begins, so the chart drew none of it. Root's
 * control: the same import serves the archive at 4800h and nothing at 4320h. A
 * bigger constant just moves the cliff. Deriving from the market's `created_at`
 * (what `/futures/[id]` "All" does, #7545) still misses intervals the venue
 * recorded before we first ingested the market. Only the server knows where its
 * archive begins.
 *
 * THE CONTRACT. A full reader adds `range=full` to the request it already makes.
 * It keeps sending `hours`, and the server treats it as a floor:
 *
 *  - a server that does not know the option ignores it and serves exactly
 *    today's `hours` window, so shipping this first loses nothing;
 *  - a server that knows it starts reading at the earliest of `now − hours`,
 *    the market's own open and the first stored archive interval. It answers
 *    with a `history_range` block saying where it began, why, the archive plan's
 *    own coverage word, and which lines it had to thin to stay bounded.
 *
 * WHAT THE CLIENT DOES WITH THE BLOCK. Nothing on the page body (notice 34).
 * The archive caption (`lib/archiveHistory.ts`) already names only the span
 * actually drawn, so a chart never claims to start at the question's open. Two
 * reads only:
 *
 *  - `servedFullRange` turns off the "too few prices — showing N days" note,
 *    which reads a wider served window as a sparse-data fallback (#7545);
 *  - `historyRangeDataAttributes` puts basis, coverage and thinning on the chart
 *    card as `data-*` attributes, so a probe can tell a complete archive from a
 *    partial one without the reader being told about our plumbing.
 */

import type { FuturesHistoryRange, FuturesHistoryResponse } from "@/lib/types";

/** The one value this option takes. */
export const FULL_HISTORY_RANGE = "full" as const;
export type HistoryRangeRequest = typeof FULL_HISTORY_RANGE;

/** The block, only when the server says it served a full read. */
export function readHistoryRange(
  response: Pick<FuturesHistoryResponse, "history_range"> | null | undefined,
): FuturesHistoryRange | null {
  const block = response?.history_range;
  if (!block || typeof block !== "object") return null;
  if (block.requested !== FULL_HISTORY_RANGE) return null;
  return block;
}

/** True only when the server answered `range=full` as full. */
export function servedFullRange(
  response: Pick<FuturesHistoryResponse, "history_range"> | null | undefined,
): boolean {
  return readHistoryRange(response) !== null;
}

/** Probe attributes for the chart card. `{}` when the read was not full. */
export function historyRangeDataAttributes(
  response: Pick<FuturesHistoryResponse, "history_range"> | null | undefined,
): Record<string, string> {
  const block = readHistoryRange(response);
  if (!block) return {};
  const attrs: Record<string, string> = { "data-history-range": FULL_HISTORY_RANGE };
  if (block.window_start) attrs["data-history-range-start"] = block.window_start;
  if (block.window_start_basis) attrs["data-history-range-basis"] = block.window_start_basis;
  // Absent ≠ complete: a missing coverage word is written as "unknown", so a
  // probe can never read silence as a whole lifetime.
  attrs["data-archive-coverage"] = block.archive_coverage || "unknown";
  const thinned = Array.isArray(block.thinned_outcomes) ? block.thinned_outcomes.length : 0;
  attrs["data-history-range-thinned"] = String(thinned);
  return attrs;
}

/**
 * The range option a chart's selected rung sends: `{ range: "full" }` for the
 * whole-history rung ("full" on EvolutionView, "all" on `/futures/[id]`),
 * otherwise `undefined` so every shorter request stays byte-identical.
 */
export function historyRangeOption(
  rung: string | null | undefined,
): { range: HistoryRangeRequest } | undefined {
  return rung === "full" || rung === "all" ? { range: FULL_HISTORY_RANGE } : undefined;
}
