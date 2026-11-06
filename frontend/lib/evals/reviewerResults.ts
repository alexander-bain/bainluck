/**
 * THE AI REVIEWER'S PLANTED-MISTAKE STUDY, AS FAR AS IT HAS GOT (#12102, top screen).
 *
 * A list kept by hand from Builder B's posts on #11951: how many reviews the
 * study plans, the count recorded so far, and every result recorded, each with
 * the post it comes from. `reviewer-results-2026-11-06.receipts.json` (test-only)
 * quotes those posts word for word, and `__tests__/reviewerResults.test.ts`
 * holds this file to them.
 *
 * Which cases are planted mistakes and which are harmless changes comes from
 * the reviewer study record (`reviewer-study-2026-11-05.json`), so the two files
 * cannot disagree about a case. A result must fit its case: a planted mistake is
 * caught or missed, a harmless change is passed or flagged (a false alarm).
 */

import RESULTS from "@/lib/evals/data/reviewer-results-2026-11-06.json";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";

export type ReviewOutcome = "caught" | "missed" | "passed" | "flagged";

const DEFECT_OUTCOMES: readonly ReviewOutcome[] = ["caught", "missed"];
const CONTROL_OUTCOMES: readonly ReviewOutcome[] = ["passed", "flagged"];

export interface ReviewResult {
  case: string;
  /** Which try: each case is reviewed more than once, to see whether the answer holds. */
  pass: number;
  outcome: ReviewOutcome;
  at: string;
  receipt: { label: string; href: string };
}

export interface ReviewerResults {
  /** When the count was read: the time of the post that gives it. */
  asOf: string;
  receipt: { label: string; href: string };
  /** Reviews the study plans: every case, the same number of tries each. */
  planned: number;
  planReceipt: { label: string; href: string };
  results: ReviewResult[];
}

/** One kind of case: how many reviews it plans, how many are in, and how they went. */
export interface TallyRow {
  planned: number;
  reviewed: number;
  /** Planted mistakes caught, or harmless changes passed: the right call. */
  right: number;
  /** Planted mistakes missed, or harmless changes flagged: the wrong call. */
  wrong: number;
}

export interface ReviewerTally {
  mistakes: TallyRow;
  harmless: TallyRow;
}

const instant = (v: unknown): v is string =>
  typeof v === "string" && /T\d{2}:\d{2}/.test(v) && !Number.isNaN(Date.parse(v));

const link = (v: unknown): v is { label: string; href: string } => {
  const l = v as { label?: unknown; href?: unknown } | null;
  return !!l && typeof l.label === "string" && !!l.label.trim() && typeof l.href === "string" && l.href.startsWith("https://");
};

/** Why the list cannot be shown against this study, or null when it can. */
export function resultsProblem(raw: unknown, study: ReviewerStudy): string | null {
  const r = raw as Record<string, unknown> | null;
  if (!r || typeof r !== "object") return "not an object";
  if (!instant(r.as_of)) return "as_of is not an instant";
  if (!link(r.receipt)) return "no receipt";
  if (!link(r.plan_receipt)) return "no plan receipt";
  const planned = r.planned;
  if (!Number.isInteger(planned) || (planned as number) <= 0) return "planned is not a positive whole number";
  // Every case gets the same number of tries, so the plan divides evenly.
  if ((planned as number) % study.cases.length !== 0) return "planned does not split evenly across the study's cases";
  const passes = (planned as number) / study.cases.length;
  if (!Array.isArray(r.results)) return "results is not a list";
  if (r.results.length > (planned as number)) return "more results than planned reviews";
  const seen = new Set<string>();
  let last = -Infinity;
  for (const row of r.results as Record<string, unknown>[]) {
    if (!row || typeof row !== "object") return "a result is not an object";
    const c = study.cases.find((x) => x.id === row.case);
    if (!c) return `${String(row.case)}: not a case in the study`;
    if (!Number.isInteger(row.pass) || (row.pass as number) < 1 || (row.pass as number) > passes) {
      return `${c.id}: pass is not a try the plan has`;
    }
    const key = `${c.id}/${row.pass}`;
    if (seen.has(key)) return `${key}: recorded twice`;
    seen.add(key);
    const fits = c.kind === "defect" ? DEFECT_OUTCOMES : CONTROL_OUTCOMES;
    if (!fits.includes(row.outcome as ReviewOutcome)) return `${key}: "${String(row.outcome)}" does not fit a ${c.kind}`;
    if (!instant(row.at)) return `${key}: at is not an instant`;
    if (Date.parse(row.at as string) < last) return `${key}: results are out of time order`;
    last = Date.parse(row.at as string);
    if (Date.parse(row.at as string) > Date.parse(r.as_of as string)) return `${key}: recorded after the count it is part of`;
    if (!link(row.receipt)) return `${key}: no receipt`;
  }
  return null;
}

/** The list, or null when it cannot be read: a malformed row drops the picture, never a square of it. */
export function loadReviewerResults(study: ReviewerStudy | null, raw: unknown = RESULTS): ReviewerResults | null {
  if (!study || resultsProblem(raw, study) !== null) return null;
  const r = raw as {
    as_of: string;
    receipt: { label: string; href: string };
    planned: number;
    plan_receipt: { label: string; href: string };
    results: ReviewResult[];
  };
  return {
    asOf: r.as_of,
    receipt: { label: r.receipt.label, href: r.receipt.href },
    planned: r.planned,
    planReceipt: { label: r.plan_receipt.label, href: r.plan_receipt.href },
    results: r.results.map((x) => ({
      case: x.case,
      pass: x.pass,
      outcome: x.outcome,
      at: x.at,
      receipt: { label: x.receipt.label, href: x.receipt.href },
    })),
  };
}

/** Planned and recorded reviews for each kind of case, counted from the two records. */
export function reviewerTally(results: ReviewerResults, study: ReviewerStudy): ReviewerTally {
  const passes = results.planned / study.cases.length;
  const kindOf = new Map(study.cases.map((c) => [c.id, c.kind]));
  const row = (kind: "defect" | "control", right: ReviewOutcome): TallyRow => {
    const mine = results.results.filter((x) => kindOf.get(x.case) === kind);
    return {
      planned: study.cases.filter((c) => c.kind === kind).length * passes,
      reviewed: mine.length,
      right: mine.filter((x) => x.outcome === right).length,
      wrong: mine.filter((x) => x.outcome !== right).length,
    };
  };
  return { mistakes: row("defect", "caught"), harmless: row("control", "passed") };
}
