/**
 * THE AI CODE REVIEWER'S STUDY, AS DESIGNED (#12102 S4).
 *
 * Ten real bugs from the site's past, planted again, and five healthy changes
 * that should pass, after Builder B's 4:36 PM receipt on #11951 (one more bug
 * was dropped by Fable's 4:46 PM answer, and is filed as #12096). The labels
 * are our own words; the receipt's stay in `data/reviewer-study-2026-11-05.receipts.json`,
 * which only the test reads.
 *
 * The reviewer column is a result read from the record, as of the receipt's
 * time (4:36 PM PT Nov 5). No review had run by then, so every cell is NOT RUN:
 * never a zero, never a blank that could read as a miss. Reviews started that
 * night; `full_study` points at the first full-study result, so the page never
 * implies the squares are newer than their receipt.
 */

import STUDY from "@/lib/evals/data/reviewer-study-2026-11-05.json";
import type { ResultKind } from "@/lib/evals/truth";
import { RESULT_KINDS } from "@/lib/evals/truth";

export type CaseKind = "defect" | "control";

export interface ReviewerCase {
  id: string;
  kind: CaseKind;
  label: string;
  text: string;
  /** What our own tests did: caught the planted bug, or passed the healthy change. */
  ourTests: "caught" | "pass";
  reviewer: ResultKind;
}

export interface ReviewerStudy {
  /** The receipt's time: the squares are as of this instant. */
  asOf: string;
  receipt: { label: string; href: string };
  /** The full study's first result, posted after the squares' receipt, when there is one. */
  fullStudy: { firstResultAt: string; receipt: { label: string; href: string } } | null;
  dropped: { issue: number; decided: string } | null;
  cases: ReviewerCase[];
}

/** Why a row cannot be shown, or null when it can. */
export function caseProblem(raw: unknown): string | null {
  const c = raw as Record<string, unknown> | null;
  if (!c || typeof c !== "object") return "not an object";
  if (typeof c.id !== "string" || !c.id) return "no id";
  if (c.kind !== "defect" && c.kind !== "control") return `${c.id}: kind is not defect or control`;
  if (typeof c.label !== "string" || !c.label.trim()) return `${c.id}: no label`;
  if (typeof c.text !== "string" || !c.text.trim()) return `${c.id}: no text`;
  const expected = c.kind === "defect" ? "caught" : "pass";
  if (c.our_tests !== expected) return `${c.id}: our_tests must be "${expected}" for a ${c.kind}`;
  if (!RESULT_KINDS.includes(c.reviewer as ResultKind)) return `${c.id}: reviewer result is not a known kind`;
  return null;
}

/**
 * The study, or null when it cannot be read. A malformed row drops the whole
 * grid rather than a square: a grid with a square missing would miscount the
 * study.
 */
export function loadReviewerStudy(raw: unknown = STUDY): ReviewerStudy | null {
  const s = raw as {
    as_of?: unknown;
    receipt?: { label?: unknown; href?: unknown };
    full_study?: { first_result_at?: unknown; receipt?: { label?: unknown; href?: unknown } } | null;
    dropped?: { issue?: unknown; decided?: unknown } | null;
    cases?: unknown[];
  } | null;
  // An instant, never a bare date: the squares are as of their receipt's time.
  if (!s || typeof s.as_of !== "string" || !/T\d{2}:\d{2}/.test(s.as_of) || Number.isNaN(Date.parse(s.as_of))) return null;
  if (typeof s.receipt?.label !== "string" || typeof s.receipt?.href !== "string") return null;
  if (!s.receipt.href.startsWith("https://")) return null;
  if (!Array.isArray(s.cases) || s.cases.length === 0) return null;
  if (s.cases.some((c) => caseProblem(c) !== null)) return null;
  const dropped =
    s.dropped && Number.isInteger(s.dropped.issue) && typeof s.dropped.decided === "string"
      ? { issue: s.dropped.issue as number, decided: s.dropped.decided }
      : null;
  const full = s.full_study;
  let fullStudy: ReviewerStudy["fullStudy"] = null;
  if (full) {
    const at = full.first_result_at;
    if (typeof at !== "string" || Number.isNaN(Date.parse(at)) || Date.parse(at) <= Date.parse(s.as_of)) return null;
    if (typeof full.receipt?.label !== "string" || typeof full.receipt?.href !== "string") return null;
    if (!full.receipt.href.startsWith("https://")) return null;
    fullStudy = { firstResultAt: at, receipt: { label: full.receipt.label, href: full.receipt.href } };
  }
  return {
    asOf: s.as_of,
    receipt: { label: s.receipt.label, href: s.receipt.href },
    fullStudy,
    dropped,
    cases: (s.cases as Record<string, string>[]).map((c) => ({
      id: c.id,
      kind: c.kind as CaseKind,
      label: c.label,
      text: c.text,
      ourTests: c.our_tests as "caught" | "pass",
      reviewer: c.reviewer as ResultKind,
    })),
  };
}
