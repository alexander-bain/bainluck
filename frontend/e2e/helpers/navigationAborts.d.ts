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

export declare const NAVIGATION_CANCEL_FAILURES: ReadonlySet<string>;

/** Is this failure a cancelled navigation/prefetch rather than a real failure? */
export declare function isNavigationCancellation(failure: FailedRequestLike | null): boolean;

/** Shape A — an aborted feed request, which no allowance may ever excuse. */
export declare function isFeedRequest(failure: FailedRequestLike | null): boolean;

/** A declaration is a bare substring (strict) or a measured-racy object form. */
export type NavigationAbortAllowanceLike =
  | string
  | { match: string; issue?: number; intermittent?: boolean };

/** The substring an allowance matches on, whichever form it took. */
export declare function allowanceMatch(a: NavigationAbortAllowanceLike): string;

/** Measured-racy: exempt from expiry, nothing else relaxed. */
export declare function allowanceIsIntermittent(a: NavigationAbortAllowanceLike): boolean;

/** Does one declared allowance excuse one failed request? */
export declare function abortAllowanceMatches(
  failure: FailedRequestLike | null,
  allowance: NavigationAbortAllowanceLike,
): boolean;

/** Which declared allowances actually matched something in this journey. */
export declare function firedAllowances(
  failedRequests: FailedRequestLike[] | null | undefined,
  allowances: NavigationAbortAllowanceLike[] | null | undefined,
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
