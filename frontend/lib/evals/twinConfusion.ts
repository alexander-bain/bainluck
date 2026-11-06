/**
 * WHAT THE JUDGE ANSWERED, KIND BY KIND (#12102 S7).
 *
 * `data/twin-confusion-2026-11-05.json` is Builder B's S0b export (#12121):
 * for run 1, per pass and per split (held-out and development), a row per true
 * kind of pair with how many times the judge gave each answer. Counts only:
 * no pair, title or reply. Every row sums to its kind's count, which this
 * module checks, and the "all pairs" view is the two splits added together,
 * because they are the two halves of the same 120 pairs.
 */

import CONFUSION from "@/lib/evals/data/twin-confusion-2026-11-05.json";
import { PASSES, RELATIONS, RELATION_WORDS, type PassId, type Relation, type Split } from "@/lib/evals/twinExam";

export const INVALID_ANSWER = "INVALID_OR_MISSING";
export type Answer = Relation | typeof INVALID_ANSWER;
export const ANSWERS: readonly Answer[] = [...RELATIONS, INVALID_ANSWER];

export const ANSWER_WORDS: Record<Answer, string> = { ...RELATION_WORDS, [INVALID_ANSWER]: "No readable answer" };

export interface AnswerRow {
  n: number;
  counts: Record<Answer, number>;
}

export type ConfusionSplit = "test" | "dev";

export interface TwinConfusion {
  runId: string;
  recordedAt: string;
  receipt: string;
  perPass: Record<PassId, Record<ConfusionSplit, { n: number; rows: Record<Relation, AnswerRow> }>>;
}

const isCount = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0;

/** Why the record cannot be shown, or null when it can. */
export function confusionProblem(raw: unknown): string | null {
  const c = raw as Record<string, unknown> | null;
  if (!c || typeof c !== "object") return "not an object";
  if (c.schema_version !== 1) return "schema_version is not 1";
  if (typeof c.recorded_at_pt !== "string" || Number.isNaN(Date.parse(c.recorded_at_pt))) return "recorded_at_pt is unreadable";
  if (typeof c.receipt_url !== "string" || !c.receipt_url.startsWith("https://")) return "no receipt link";
  const perPass = c.per_pass as Record<string, Record<string, { n?: unknown; rows?: Record<string, { n?: unknown; counts?: Record<string, unknown> }> }>> | undefined;
  for (const p of PASSES) {
    for (const s of ["test", "dev"] as const) {
      const split = perPass?.[p]?.[s];
      if (!split || !isCount(split.n)) return `pass ${p}, ${s}: unreadable`;
      let total = 0;
      for (const r of RELATIONS) {
        const row = split.rows?.[r];
        if (!row || !isCount(row.n) || !row.counts) return `pass ${p}, ${s}, ${r}: unreadable`;
        let sum = 0;
        for (const a of ANSWERS) {
          if (!isCount(row.counts[a])) return `pass ${p}, ${s}, ${r}: no count for ${a}`;
          sum += row.counts[a] as number;
        }
        if (sum !== row.n) return `pass ${p}, ${s}, ${r}: answers sum to ${sum}, not ${row.n}`;
        total += row.n as number;
      }
      if (total !== split.n) return `pass ${p}, ${s}: rows sum to ${total}, not ${split.n}`;
    }
  }
  return null;
}

export function loadConfusion(raw: unknown = CONFUSION): TwinConfusion | null {
  if (confusionProblem(raw)) return null;
  const c = raw as {
    run_id: string;
    recorded_at_pt: string;
    receipt_url: string;
    per_pass: TwinConfusion["perPass"];
  };
  return { runId: c.run_id, recordedAt: c.recorded_at_pt, receipt: c.receipt_url, perPass: c.per_pass };
}

/** One kind's answers in a split; "all" is held-out and development added together. */
export function answersFor(confusion: TwinConfusion, pass: PassId, split: Split, relation: Relation): AnswerRow {
  if (split !== "all") return confusion.perPass[pass][split].rows[relation];
  const a = confusion.perPass[pass].test.rows[relation];
  const b = confusion.perPass[pass].dev.rows[relation];
  const counts = Object.fromEntries(ANSWERS.map((x) => [x, a.counts[x] + b.counts[x]])) as Record<Answer, number>;
  return { n: a.n + b.n, counts };
}
