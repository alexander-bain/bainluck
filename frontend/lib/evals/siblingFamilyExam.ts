/**
 * THE SIBLING-FAMILY EXAM, AS ITS SCORER RECORDED IT (#12374, #12221 §3).
 *
 * `data/sibling-family-exam-2026-11.json` is the frozen scorer's output across
 * the three passes over the 12 `dev` and 20 set-aside `test` sibling-family
 * cards. Every gate verdict (`PASS` or `FAIL`) and the `sibling_family`
 * auto-publish status (`PASS`, `FAIL`, or `HELD`) are read directly from the
 * committed record, never recomputed in the browser.
 *
 * Set-aside results are counts and 95% Wilson intervals only; the record
 * carries no private card IDs, market IDs, titles or model quotes.
 */

import SIBLING_EXAM_RAW from "@/lib/evals/data/sibling-family-exam-2026-11.json";
import type { MeasuredTruth, ResultKind } from "@/lib/evals/truth";

export const SIBLING_EXAM_PASSES = ["1", "2", "3"] as const;
export type SiblingExamPassId = (typeof SIBLING_EXAM_PASSES)[number];

export const SIBLING_EXAM_SPLITS = ["test", "dev", "all"] as const;
export type SiblingExamSplit = (typeof SIBLING_EXAM_SPLITS)[number];

export const SIBLING_EXAM_GATE_IDS = [
  "card_vs_single_member",
  "relation_truth",
  "freshness_and_count",
  "run_to_run_stability",
] as const;
export type SiblingExamGateId = (typeof SIBLING_EXAM_GATE_IDS)[number];

/** Plain words for each gate in the sibling-family exam (zero internal jargon). */
export const SIBLING_EXAM_GATE_WORDS: Record<
  SiblingExamGateId,
  { name: string; checks: string; unitLabel: string }
> = {
  card_vs_single_member: {
    name: "Better than a single market",
    checks:
      "On set-aside cards never used for tuning, people rate the grouped card better than its strongest single market at least eighty-five percent of the time, and worse at most ten percent of the time.",
    unitLabel: "rated better on set-aside cards",
  },
  relation_truth: {
    name: "Same parent and clear axis",
    checks:
      "Every member row on a set-aside card shares the stated parent event or topic, varies on the stated axis, and has no duplicate member.",
    unitLabel: "set-aside cards with valid members",
  },
  freshness_and_count: {
    name: "Three to six live members",
    checks:
      "Every set-aside card has between three and six active, unsettled member markets.",
    unitLabel: "set-aside cards with live members",
  },
  run_to_run_stability: {
    name: "Same member set across tries",
    checks:
      "Across three separate runs, at least ninety percent of proposed cards agree on their exact member set.",
    unitLabel: "cards agreeing across all three tries",
  },
};

export interface SiblingGateCell {
  k: number;
  n: number;
  result: "pass" | "fail" | "held";
  wilson95?: [number, number];
  betterK?: number;
  worseK?: number;
  gradedK?: number;
  ungradedK?: number;
  betterPct?: number | null;
}

export interface SiblingExamGate {
  id: SiblingExamGateId;
  bar: string;
  scope: "test" | "all";
  perPass: Record<SiblingExamPassId, SiblingGateCell> | null;
  observed: SiblingGateCell | null;
  result: "pass" | "fail" | "held";
}

export interface SiblingSplitMetric {
  k: number;
  n: number;
  ungraded?: number;
  pct: number | null;
  wilson95: [number, number] | null;
}

export interface SiblingSplitRecord {
  expected: number;
  graded: number;
  ungraded: number;
  better: SiblingSplitMetric;
  same: SiblingSplitMetric;
  worse: SiblingSplitMetric;
  relationTruth: SiblingSplitMetric;
  duplicateFree: SiblingSplitMetric;
  freshnessAndCount: SiblingSplitMetric;
}

export interface SiblingFamilyExam {
  schema: string;
  asOf: string;
  ruling: string;
  receipt: string;
  model: string;
  result: ResultKind;
  licences: {
    sibling_family: ResultKind;
  };
  splitCounts: {
    test: number;
    dev: number;
    all: number;
  };
  cost: {
    estimatedUsd: number;
    actualUsd: number;
    replies: number;
    inputTokens: number;
    outputTokens: number;
    perRunCapUsd: number;
    monthlyCapUsd: number;
  };
  hashes: {
    datasetSha256: string;
    scorerSha256: string;
  };
  gates: SiblingExamGate[];
  perPass: Record<SiblingExamPassId, Record<SiblingExamSplit, SiblingSplitRecord>>;
}

const RESULT_MAP: Record<string, ResultKind> = {
  PASS: "pass",
  FAIL: "fail",
  HELD: "held",
};

const isNonNegInt = (v: unknown): v is number =>
  Number.isInteger(v) && (v as number) >= 0;

function parseCell(raw: unknown): SiblingGateCell | null {
  if (!raw || typeof raw !== "object") return null;
  const c = raw as Record<string, unknown>;
  if (c.result !== "PASS" && c.result !== "FAIL" && c.result !== "HELD") return null;
  if (!isNonNegInt(c.k) || !isNonNegInt(c.n) || (c.k as number) > (c.n as number)) {
    return null;
  }
  const wilson = Array.isArray(c.wilson95)
    ? (c.wilson95 as [number, number])
    : Array.isArray(c.better_wilson95)
      ? (c.better_wilson95 as [number, number])
      : undefined;
  return {
    k: c.k as number,
    n: c.n as number,
    result:
      c.result === "PASS" ? "pass" : c.result === "HELD" ? "held" : "fail",
    wilson95: wilson,
    betterK: isNonNegInt(c.better_k) ? (c.better_k as number) : undefined,
    worseK: isNonNegInt(c.worse_k) ? (c.worse_k as number) : undefined,
    gradedK: isNonNegInt(c.graded_k) ? (c.graded_k as number) : undefined,
    ungradedK: isNonNegInt(c.ungraded_k) ? (c.ungraded_k as number) : undefined,
    betterPct: typeof c.better_pct === "number" ? (c.better_pct as number) : null,
  };
}

/** Validate the committed sibling-family exam JSON record. Returns a reason on error, or null. */
export function siblingFamilyExamProblem(raw: unknown): string | null {
  if (!raw || typeof raw !== "object") return "not an object";
  const e = raw as Record<string, unknown>;
  if (e.schema !== "sibling-family-exam/1") return "schema is not sibling-family-exam/1";
  if (e.result !== "PASS" && e.result !== "FAIL" && e.result !== "HELD") {
    return "result is not PASS, FAIL, or HELD";
  }
  if (typeof e.as_of !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(e.as_of)) {
    return "as_of is unreadable";
  }
  if (typeof e.receipt !== "string" || !e.receipt.startsWith("https://")) {
    return "no receipt link";
  }
  if (typeof e.ruling !== "string" || !e.ruling.startsWith("https://")) {
    return "no ruling link";
  }
  if (typeof e.model !== "string" || !e.model) return "no model";

  const splitCounts = e.split_counts as Record<string, unknown> | undefined;
  if (
    !splitCounts ||
    !isNonNegInt(splitCounts.test) ||
    (splitCounts.test as number) < 20 ||
    !isNonNegInt(splitCounts.dev) ||
    !isNonNegInt(splitCounts.all)
  ) {
    return "split_counts requires test >= 20";
  }

  const licences = e.licences as Record<string, unknown> | undefined;
  if (!licences || !(String(licences.sibling_family) in RESULT_MAP)) {
    return "licences.sibling_family is unreadable";
  }

  const cost = e.cost as Record<string, unknown> | undefined;
  if (
    !cost ||
    typeof cost.estimated_usd !== "number" ||
    typeof cost.actual_usd !== "number" ||
    !isNonNegInt(cost.replies)
  ) {
    return "cost is unreadable";
  }

  const gates = e.gate_results as unknown[];
  if (!Array.isArray(gates) || gates.length !== SIBLING_EXAM_GATE_IDS.length) {
    return "gate_results must have all 4 gates";
  }
  for (const g of gates as Record<string, unknown>[]) {
    if (!SIBLING_EXAM_GATE_IDS.includes(g?.id as SiblingExamGateId)) {
      return `unknown gate id: ${String(g?.id)}`;
    }
    if (g.result !== "PASS" && g.result !== "FAIL" && g.result !== "HELD") {
      return `${String(g.id)}: gate result is not PASS, FAIL, or HELD`;
    }
    if (g.by_pass) {
      for (const p of SIBLING_EXAM_PASSES) {
        if (!parseCell((g.by_pass as Record<string, unknown>)[p])) {
          return `${String(g.id)}: pass ${p} is unreadable`;
        }
      }
    } else if (!parseCell(g.observed)) {
      return `${String(g.id)}: observed cell is unreadable`;
    }
  }
  return null;
}

export function loadSiblingFamilyExam(
  raw: unknown = SIBLING_EXAM_RAW
): SiblingFamilyExam | null {
  if (siblingFamilyExamProblem(raw)) return null;
  const e = raw as Record<string, unknown>;
  const rawGates = e.gate_results as Record<string, unknown>[];
  const gates: SiblingExamGate[] = rawGates.map((g) => {
    const perPass = g.by_pass
      ? (Object.fromEntries(
          SIBLING_EXAM_PASSES.map((p) => [
            p,
            parseCell((g.by_pass as Record<string, unknown>)[p]) as SiblingGateCell,
          ])
        ) as Record<SiblingExamPassId, SiblingGateCell>)
      : null;
    const observed = g.by_pass ? null : parseCell(g.observed);
    return {
      id: g.id as SiblingExamGateId,
      bar: String(g.bar ?? ""),
      scope: (g.scope as "test" | "all") ?? "test",
      perPass,
      observed,
      result:
        g.result === "PASS" ? "pass" : g.result === "HELD" ? "held" : "fail",
    };
  });

  const rawPerPass = e.per_pass as Record<
    string,
    Record<string, Record<string, unknown>>
  >;
  const perPass = Object.fromEntries(
    SIBLING_EXAM_PASSES.map((p) => [
      p,
      Object.fromEntries(
        SIBLING_EXAM_SPLITS.map((s) => {
          const sp = rawPerPass[p][s];
          return [
            s,
            {
              expected: sp.expected as number,
              graded: sp.graded as number,
              ungraded: sp.ungraded as number,
              better: sp.better as SiblingSplitMetric,
              same: sp.same as SiblingSplitMetric,
              worse: sp.worse as SiblingSplitMetric,
              relationTruth: sp.relation_truth as SiblingSplitMetric,
              duplicateFree: sp.duplicate_free as SiblingSplitMetric,
              freshnessAndCount: sp.freshness_and_count as SiblingSplitMetric,
            },
          ];
        })
      ),
    ])
  ) as Record<SiblingExamPassId, Record<SiblingExamSplit, SiblingSplitRecord>>;

  const licences = e.licences as Record<string, string>;
  const splitCounts = e.split_counts as Record<string, number>;
  const cost = e.cost as Record<string, number>;
  const hashes = e.hashes as Record<string, string>;

  return {
    schema: String(e.schema),
    asOf: String(e.as_of),
    ruling: String(e.ruling),
    receipt: String(e.receipt),
    model: String(e.model),
    result: RESULT_MAP[String(e.result)],
    licences: {
      sibling_family: RESULT_MAP[String(licences.sibling_family)],
    },
    splitCounts: {
      test: splitCounts.test,
      dev: splitCounts.dev,
      all: splitCounts.all,
    },
    cost: {
      estimatedUsd: cost.estimated_usd,
      actualUsd: cost.actual_usd,
      replies: cost.replies,
      inputTokens: cost.input_tokens,
      outputTokens: cost.output_tokens,
      perRunCapUsd: cost.per_run_cap_usd,
      monthlyCapUsd: cost.monthly_cap_usd,
    },
    hashes: {
      datasetSha256: hashes.dataset_sha256,
      scorerSha256: hashes.scorer_sha256,
    },
    gates,
    perPass,
  };
}

export function siblingFamilyExamTruth(exam: SiblingFamilyExam): MeasuredTruth {
  return {
    kind: "last_run",
    asOf: exam.asOf,
    source: {
      label: "Sibling-market card exam results",
      href: exam.receipt,
    },
  };
}
