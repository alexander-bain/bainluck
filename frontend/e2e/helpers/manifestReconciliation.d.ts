/** #1915 — see `manifestReconciliation.js`. */

import type { JourneyRecord } from "./manifest";
import type { JourneyResult } from "./journey";

export interface JourneyOutcome {
  /** `result.status !== test.expectedStatus`. */
  attemptFailed: boolean;
  /** Playwright's status string, carried into the assertion detail. */
  status: string;
  /** The test's first error message, if any. Redacted by the helper. */
  errorMessage?: string;
}

/** Downgrade-only reconciliation of one journey record against its test outcome. */
export function reconcileJourneyVerdict(
  record: JourneyRecord,
  outcome: JourneyOutcome,
): JourneyRecord;

/** Run-level reconciliation of the manifest's failure count against the runner's. */
export function reconcileRunCounts(input: {
  journeys: Array<{ result?: string }>;
  runnerFailures: number;
}): { forcedResult: JourneyResult | undefined; notes: string[]; manifestFailures: number };
