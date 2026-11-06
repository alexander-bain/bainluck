/**
 * "EXAMS ON THE RECORD" — the /evals timeline (#12102, S3).
 *
 * The rows come from `data/runs-2026-11.json`, a committed record. Every figure
 * in it is copied from the public receipt on its row, and the receipt's own
 * words for it sit beside it in `data/runs-2026-11.receipts.json` (test-only,
 * so receipt wording never ships). `__tests__/runs.test.ts` holds each value to
 * its quote, so a slip between the two fails the build rather than the page.
 *
 * Verdicts are the record's own: FAIL where the receipt says it failed, NOT
 * ELIGIBLE where it says there was too little to measure. Nothing here grades a
 * run. Model spend is usage-rated — computed from each reply's token usage at
 * the provider's published rate, not an invoice — and says so; a run done by
 * hand has no model spend and shows none.
 */

import RUNS from "@/lib/evals/data/runs-2026-11.json";
import type { ResultKind } from "@/lib/evals/truth";

export type RunBy = "ai_model" | "by_hand";

export interface RunFigure {
  value: number;
  format: "count";
}

export interface RunCost {
  value: number;
  basis: "usage_rated";
  /** The exam's cost includes its pilot; the row says so. */
  includes?: "pilot";
}

export interface Run {
  id: string;
  /** Pacific calendar date of the run. */
  date: string;
  title: string;
  by: RunBy;
  /** The provider's model id, e.g. "claude-sonnet-5-5". */
  model?: string;
  result: ResultKind;
  /** Words, with `{name}` where a figure from `figures` goes. */
  note: string;
  figures: Record<string, RunFigure>;
  cost: RunCost | null;
  receipt: { label: string; href: string };
}

const RESULTS: readonly ResultKind[] = ["pass", "fail", "held", "not_run", "not_eligible", "unknown"];

/** Shape-check one row. Returns why it is unusable, or null. */
export function runProblem(row: unknown): string | null {
  if (!row || typeof row !== "object") return "not an object";
  const r = row as Record<string, unknown>;
  if (typeof r.id !== "string" || !r.id) return "no id";
  if (typeof r.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(r.date)) return `${r.id}: no date`;
  if (typeof r.title !== "string" || !r.title) return `${r.id}: no title`;
  if (r.by !== "ai_model" && r.by !== "by_hand") return `${r.id}: unknown "by"`;
  if (r.by === "ai_model" && (typeof r.model !== "string" || !r.model)) return `${r.id}: an AI run names its model`;
  if (!RESULTS.includes(r.result as ResultKind)) return `${r.id}: unknown result`;
  if (typeof r.note !== "string") return `${r.id}: no note`;
  const receipt = r.receipt as Record<string, unknown> | undefined;
  if (!receipt || typeof receipt.href !== "string" || !/^https:\/\//.test(receipt.href)) {
    return `${r.id}: no receipt link`;
  }
  const figures = (r.figures ?? {}) as Record<string, { value?: unknown }>;
  for (const slot of noteSlots(r.note)) {
    if (typeof figures[slot]?.value !== "number") return `${r.id}: {${slot}} has no figure`;
  }
  if (r.by === "ai_model" && typeof figures.replies?.value !== "number") {
    return `${r.id}: an AI run states its number of replies`;
  }
  if (r.cost !== null) {
    const cost = r.cost as Record<string, unknown> | undefined;
    if (!cost || typeof cost.value !== "number" || cost.basis !== "usage_rated") {
      return `${r.id}: a cost carries its value and its basis`;
    }
  }
  return null;
}

/** The `{name}` slots in a note, in order. */
export function noteSlots(note: string): string[] {
  return Array.from(note.matchAll(/\{(\w+)\}/g), (m) => m[1]);
}

/** A note split into words and figure slots, for the renderer. */
export function notePieces(note: string): Array<{ text: string } | { slot: string }> {
  return note
    .split(/\{(\w+)\}/)
    .map((piece, i) => (i % 2 === 1 ? { slot: piece } : { text: piece }))
    .filter((p) => !("text" in p) || p.text !== "");
}

/** The rows, oldest first. A malformed row is dropped, never half-shown. */
export function loadRuns(raw: unknown = RUNS): Run[] {
  const rows = (raw as { runs?: unknown[] })?.runs ?? [];
  return rows
    .filter((row) => runProblem(row) === null)
    .map((row) => row as Run)
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** Dollars to the cent: 0.177876 → "$0.18". The raw value travels as data. */
export function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

/** The provider's model id as a reader sees it: "claude-sonnet-5-5" → "Claude Sonnet 5.5". */
export function modelName(id: string): string {
  const m = /^claude-(opus|sonnet|haiku|fable)-(\d+)-(\d+)$/.exec(id);
  if (!m) return id;
  return `Claude ${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`;
}
