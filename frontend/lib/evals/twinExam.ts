/**
 * THE TWIN EXAM, AS ITS SCORER RECORDED IT (#12102 S2).
 *
 * `data/twin-exam-2026-11-05.json` is Builder B's S0a export (#12118): the
 * frozen scorer's own output for run 1, the baseline (Decide 39-A). Gates with
 * their stored verdicts per pass, per-relation counts for the held-out,
 * development and all-120 splits with the scorer's 95% ranges, licences, cost,
 * model and hashes. Nothing in it is typed by hand, and this module never
 * re-grades it: a gate's verdict is the record's, pass by pass, and a gate
 * counts as passed only when every pass passed it (each pass is a separate
 * try at the same bar, ruling 24a).
 *
 * Held-out results are counts only. The record carries no pair, title or
 * reply, and the page shows none.
 */

import EXAM from "@/lib/evals/data/twin-exam-2026-11-05.json";
import type { MeasuredTruth, ResultKind } from "@/lib/evals/truth";

export type Split = "test" | "dev" | "all";
export const SPLITS: readonly Split[] = ["test", "dev", "all"];

export const PASSES = ["1", "2", "3"] as const;
export type PassId = (typeof PASSES)[number];

export const RELATIONS = [
  "twin",
  "same_number",
  "implies",
  "path_step",
  "by_when",
  "same_decision",
  "grouping",
  "related",
  "unrelated",
  "uncheckable",
] as const;
export type Relation = (typeof RELATIONS)[number];

/** Plain words for each relation the exam grades. */
export const RELATION_WORDS: Record<Relation, string> = {
  twin: "Twins",
  same_number: "Same number",
  implies: "One implies the other",
  path_step: "Path and step",
  by_when: "By when",
  same_decision: "Same decision",
  grouping: "Grouping",
  related: "Related",
  unrelated: "Unrelated",
  uncheckable: "Can't check",
};

/**
 * Plain words for each gate: its name, what it checks, and how each of its
 * counts reads. A count named here as a failure count (wrongly combined, cut
 * off, unreadable, not word for word) is a count of failures, as the record's
 * identifiers say.
 */
export const GATE_WORDS: Record<string, { name: string; checks: string; units: Record<string, string> }> = {
  twin_detection: {
    name: "Finds twins",
    checks: "On held-out pairs, it finds the twins and calls nothing else a twin.",
    units: { recall: "twins found", false_twins: "non-twins called twins" },
  },
  same_number_detection: {
    name: "Finds same-number pairs",
    checks: "On held-out pairs, it finds the pairs whose markets measure the same number.",
    units: { count: "found" },
  },
  safe_relation_labels: {
    name: "Related, unrelated or can't check",
    checks: "On held-out pairs that must not be combined, it gives the right one of these three labels.",
    units: { count: "right" },
  },
  wrong_merges: {
    name: "No wrong combining",
    checks: "On held-out pairs, it never treats two markets as one when they must stay apart.",
    units: { count: "wrongly combined" },
  },
  correct_abstention: {
    name: "Says when it can't check",
    checks: "When one side's data cannot settle a held-out pair, it says it cannot check instead of guessing.",
    units: { count: "caught" },
  },
  unreadable_outputs: {
    name: "Every reply readable",
    checks: "Every reply comes back in the format the exam asked for.",
    units: { count: "unreadable" },
  },
  truncated_outputs: {
    name: "No cut-off replies",
    checks: "No reply is cut off before it finishes.",
    units: { count: "cut off" },
  },
  three_pass_stability: {
    name: "Same label every pass",
    checks: "Asked three times, it gives each pair the same label every time.",
    units: { count: "with the same label in all three passes" },
  },
  nonverbatim_quotes: {
    name: "Word-for-word quotes",
    checks: "Every rule it quotes appears word for word on the side it says it came from.",
    units: { count: "replies with a quote that was not word for word" },
  },
};

export interface Count {
  k: number;
  n: number;
  wilson95: [number, number] | null;
}

export interface RelationCounts {
  recall: Count;
  precision: Count;
}

export interface GateCell {
  result: "pass" | "fail";
  counts: { key: string; k: number; n: number }[];
}

export interface Gate {
  id: string;
  /** "test" = held-out pairs; "all" = every reply in all three passes. */
  scope: string;
  /** One cell per pass, or null for a gate measured across the passes. */
  perPass: Record<PassId, GateCell> | null;
  /** The one spanning cell of a gate measured across the passes. */
  observed: GateCell | null;
  /** PASS only when every pass passed. */
  result: "pass" | "fail";
}

export interface SplitRecord {
  expected: number;
  wrongMerges: number;
  falseTwins: Count;
  perRelation: Record<Relation, RelationCounts>;
}

export interface TwinExam {
  runId: string;
  result: ResultKind;
  recordedAt: string;
  receipt: string;
  model: string;
  gates: Gate[];
  licences: Record<Relation, ResultKind>;
  perPass: Record<PassId, Record<Split, SplitRecord>>;
}

const LICENSE_KIND: Record<string, ResultKind> = {
  PASS: "pass",
  FAIL: "fail",
  HELD: "held",
  NOT_ELIGIBLE: "not_eligible",
};

const isCount = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0;

function countProblem(c: unknown): boolean {
  const o = c as { k?: unknown; n?: unknown; wilson95?: unknown } | undefined;
  if (!o || !isCount(o.k) || !isCount(o.n) || (o.k as number) > (o.n as number)) return true;
  if (o.wilson95 === null || o.wilson95 === undefined) return false;
  return !(Array.isArray(o.wilson95) && o.wilson95.length === 2 && o.wilson95.every((x) => typeof x === "number"));
}

/** The counts inside one gate cell: either the cell's own k/n, or each named k/n inside it. */
function cellCounts(cell: Record<string, unknown>): { key: string; k: number; n: number }[] {
  if (isCount(cell.k) && isCount(cell.n)) return [{ key: "count", k: cell.k as number, n: cell.n as number }];
  return Object.entries(cell)
    .filter(([key, v]) => key !== "result" && v && typeof v === "object" && !countProblem(v))
    .map(([key, v]) => ({ key, k: (v as Count).k, n: (v as Count).n }));
}

function cellOf(raw: unknown): GateCell | null {
  const cell = raw as Record<string, unknown> | undefined;
  if (!cell || (cell.result !== "PASS" && cell.result !== "FAIL")) return null;
  const counts = cellCounts(cell);
  if (counts.length === 0) return null;
  return { result: cell.result === "PASS" ? "pass" : "fail", counts };
}

/** Why the record cannot be shown, or null when it can. The sections are absent on any problem. */
export function examProblem(raw: unknown): string | null {
  const e = raw as Record<string, unknown> | null;
  if (!e || typeof e !== "object") return "not an object";
  if (e.schema_version !== 1) return "schema_version is not 1";
  if (e.result !== "PASS" && e.result !== "FAIL") return "result is not PASS or FAIL";
  if (typeof e.recorded_at_pt !== "string" || Number.isNaN(Date.parse(e.recorded_at_pt))) return "recorded_at_pt is unreadable";
  if (typeof e.receipt_url !== "string" || !e.receipt_url.startsWith("https://")) return "no receipt link";
  if (typeof e.model !== "string" || !e.model) return "no model";
  const gates = e.gate_results as unknown[];
  if (!Array.isArray(gates) || gates.length === 0) return "no gates";
  for (const g of gates as Record<string, unknown>[]) {
    if (typeof g?.id !== "string") return "a gate has no id";
    if (g.by_pass) {
      for (const p of PASSES) {
        if (!cellOf((g.by_pass as Record<string, unknown>)[p])) return `${g.id}: pass ${p} is unreadable`;
      }
    } else if (!cellOf(g.observed)) {
      return `${g.id}: no readable verdict`;
    }
  }
  const licences = e.licences as Record<string, unknown> | undefined;
  for (const r of RELATIONS) {
    if (!licences || !(String(licences[r]) in LICENSE_KIND)) return `licence for ${r} is unreadable`;
  }
  const perPass = e.per_pass as Record<string, Record<string, Record<string, unknown>>> | undefined;
  for (const p of PASSES) {
    for (const s of SPLITS) {
      const split = perPass?.[p]?.[s];
      if (!split || !isCount(split.expected) || !isCount(split.wrong_merges) || countProblem(split.false_twins)) {
        return `pass ${p}, ${s}: unreadable`;
      }
      const rel = split.per_relation as Record<string, { recall?: unknown; precision?: unknown }> | undefined;
      for (const r of RELATIONS) {
        if (!rel?.[r] || countProblem(rel[r].recall) || countProblem(rel[r].precision)) {
          return `pass ${p}, ${s}, ${r}: unreadable counts`;
        }
      }
    }
  }
  return null;
}

export function loadExam(raw: unknown = EXAM): TwinExam | null {
  if (examProblem(raw)) return null;
  const e = raw as {
    run_id: string;
    result: "PASS" | "FAIL";
    recorded_at_pt: string;
    receipt_url: string;
    model: string;
    gate_results: { id: string; scope: string; by_pass?: Record<string, unknown>; observed?: unknown }[];
    licences: Record<string, string>;
    per_pass: Record<string, Record<string, Record<string, unknown>>>;
  };
  const gates: Gate[] = e.gate_results.map((g) => {
    const perPass = g.by_pass
      ? (Object.fromEntries(PASSES.map((p) => [p, cellOf(g.by_pass?.[p]) as GateCell])) as Record<PassId, GateCell>)
      : null;
    const observed = g.by_pass ? null : cellOf(g.observed);
    const cells = perPass ? PASSES.map((p) => perPass[p]) : [observed as GateCell];
    return {
      id: g.id,
      scope: g.scope,
      perPass,
      observed,
      result: cells.every((c) => c.result === "pass") ? "pass" : "fail",
    };
  });
  const perPass = Object.fromEntries(
    PASSES.map((p) => [
      p,
      Object.fromEntries(
        SPLITS.map((s) => {
          const split = e.per_pass[p][s];
          return [
            s,
            {
              expected: split.expected as number,
              wrongMerges: split.wrong_merges as number,
              falseTwins: split.false_twins as Count,
              perRelation: split.per_relation as Record<Relation, RelationCounts>,
            },
          ];
        })
      ),
    ])
  ) as Record<PassId, Record<Split, SplitRecord>>;
  return {
    runId: e.run_id,
    result: e.result === "PASS" ? "pass" : "fail",
    recordedAt: e.recorded_at_pt,
    receipt: e.receipt_url,
    model: e.model,
    gates,
    licences: Object.fromEntries(RELATIONS.map((r) => [r, LICENSE_KIND[e.licences[r]]])) as Record<Relation, ResultKind>,
    perPass,
  };
}

export function examTruth(exam: TwinExam): MeasuredTruth {
  return { kind: "last_run", asOf: exam.recordedAt, source: { label: "Twin exam receipt", href: exam.receipt } };
}

/** The lowest and highest of a figure across the three passes. */
export function acrossPasses(exam: TwinExam, pick: (pass: Record<Split, SplitRecord>) => number): [number, number] {
  const values = PASSES.map((p) => pick(exam.perPass[p]));
  return [Math.min(...values), Math.max(...values)];
}
