/**
 * UX-P047 (#1648 P1, Fable ruling) — the ONE home for the navigation-abort
 * decision, imported by both graders so they cannot disagree on one input.
 */

import type { FailedRequestLike } from "./errorVolume";

/** The Next.js RSC prefetch marker, shared so two specs cannot restate it. */
export declare const RSC_PREFETCH: string;

/**
 * The same allowance in its measured-intermittent form, for specs with no
 * measured base rate of their own. Exempt from run-level expiry, so declaring
 * it cannot manufacture a red; tied to #1525 so it still has an end.
 */
export declare const RSC_PREFETCH_ABORT: Readonly<{
  match: string;
  issue: number;
  intermittent: true;
}>;

/**
 * Ruling 021 clause 3, amended 2026-08-18 (#1908 M2): the abort is excusable
 * when the INSTRUMENT caused it; the aftermath is graded, always. The only
 * allowance form that can cover a feed abort, and only behind attribution plus
 * a graded aftermath — both checked in `abortAllowanceMatches`, both fail-closed.
 */
export declare const INSTRUMENT_NAVIGATION_ABORT: Readonly<{
  match: string;
  issue: number;
  instrumentInduced: true;
  intermittent: true;
}>;

export declare const NAVIGATION_CANCEL_FAILURES: ReadonlySet<string>;

/** Is this failure a cancelled navigation/prefetch rather than a real failure? */
export declare function isNavigationCancellation(failure: FailedRequestLike | null): boolean;

/**
 * Third-party — an origin that is not ours. Stamped by the collector (which
 * owns the origin list) and read here, so the two graders cannot re-derive it
 * differently. Excluded from the per-error grader, deliberately NOT from the
 * volume grader (#1600 was a third-party fan-out).
 */
export declare function isThirdParty(failure: FailedRequestLike | null): boolean;

/** Shape A — an aborted feed request, which no allowance may ever excuse. */
export declare function isFeedRequest(failure: FailedRequestLike | null): boolean;

/** A declaration is a bare substring (strict) or a measured-racy object form. */
export type NavigationAbortAllowanceLike =
  | string
  | { match: string; issue?: number; intermittent?: boolean; instrumentInduced?: boolean };

/**
 * What a grader must PROVE before an instrument-induced excuse applies. Optional
 * everywhere so existing callers compile — and refused everywhere it is absent,
 * so an un-updated caller excuses nothing.
 */
export interface AbortGradingContext {
  aftermathGraded?: boolean;
}

/** The substring an allowance matches on, whichever form it took. */
export declare function allowanceMatch(a: NavigationAbortAllowanceLike): string;

/** Measured-racy: exempt from expiry, nothing else relaxed. */
export declare function allowanceIsIntermittent(a: NavigationAbortAllowanceLike): boolean;

/** The carve-out form. */
export declare function allowanceIsInstrumentInduced(a: NavigationAbortAllowanceLike): boolean;

/** Condition 1 — did a harness action cause this abort, by name? */
export declare function isInstrumentInduced(failure: FailedRequestLike | null): boolean;

/** Condition 3 — has the caller proven the aftermath is graded? */
export declare function aftermathIsGraded(context?: AbortGradingContext | null): boolean;

/**
 * The non-vacuity guard: instrument-induced allowances declared by a journey
 * that grades no aftermath. Non-empty means the journey is red — an excused
 * abort with nothing graded in its place is a deletion, not a carve-out.
 */
export declare function instrumentAllowancesMissingAftermath(
  allowances: NavigationAbortAllowanceLike[] | null | undefined,
  context?: AbortGradingContext | null,
): NavigationAbortAllowanceLike[];

/** Does one declared allowance excuse one failed request? */
export declare function abortAllowanceMatches(
  failure: FailedRequestLike | null,
  allowance: NavigationAbortAllowanceLike,
  context?: AbortGradingContext | null,
): boolean;

/** Which declared allowances actually matched something in this journey. */
export declare function firedAllowances(
  failedRequests: FailedRequestLike[] | null | undefined,
  allowances: NavigationAbortAllowanceLike[] | null | undefined,
  context?: AbortGradingContext | null,
): NavigationAbortAllowanceLike[];

/**
 * Declared across the run but fired in no journey — an excuse that has outlived
 * its reason. Non-empty means the RUN is red, even when every journey passed.
 */
export declare function unfiredAllowances(
  journeys: Array<{
    declared_navigation_allowances?: string[];
    fired_navigation_allowances?: string[];
  }> | null | undefined,
): string[];
