/**
 * Non-overlapping engagement accounting (L2-218, Item 1 / #1453).
 *
 * BEFORE: `useEngagementTime` emitted the FULL cumulative duration on every
 * trigger — visibility→hidden, `beforeunload`, effect cleanup, and route
 * change. A single hide/show/unload cycle therefore produced several
 * overlapping cumulative observations for one page, inflating both event counts
 * and every duration-derived aggregate (C90 P2).
 *
 * NOW: a page keeps a ledger of what it has ALREADY reported. Each observation
 * emits only the delta since the last one, so repeated triggers are harmless
 * and the emitted values sum to the true time on page exactly once.
 *
 * This module is pure and clock-free (elapsed values are passed in) so the
 * contract is unit-testable without a DOM or fake timers.
 */

/** What a page has already reported. A fresh page starts at zero. */
export interface EngagementLedger {
  reportedTotalMs: number;
  reportedActiveMs: number;
}

export const EMPTY_ENGAGEMENT_LEDGER: EngagementLedger = {
  reportedTotalMs: 0,
  reportedActiveMs: 0,
};

export interface EngagementObservation {
  /** Seconds of wall-clock time on page NOT covered by a previous emission. */
  seconds: number;
  /** Seconds of visible/active time NOT covered by a previous emission. */
  activeSeconds: number;
  /** The ledger to store after emitting this observation. */
  ledger: EngagementLedger;
}

export interface EngagementInput {
  /** Total wall-clock ms since arriving on this page. */
  elapsedTotalMs: number;
  /** Accumulated ms the tab was visible on this page. */
  elapsedActiveMs: number;
  /** What has already been emitted for this page. */
  ledger: EngagementLedger;
  /**
   * Cumulative seconds a page must reach before its FIRST observation is worth
   * emitting (`GA_CONFIG.ENGAGEMENT.MIN_ENGAGED_TIME`). Once a page has
   * reported once, later deltas only need to be non-trivial.
   */
  minFirstSeconds: number;
  /**
   * Minimum delta (seconds) for a follow-up observation. Stops a rapid
   * hide/show/unload burst from emitting a spray of ~0s events.
   */
  minDeltaSeconds?: number;
}

const DEFAULT_MIN_DELTA_SECONDS = 1;

/**
 * Compute the next non-overlapping observation, or `null` when there is
 * nothing new worth reporting (which is the normal outcome for the second and
 * third trigger of one hide→unload→cleanup burst).
 */
export function nextEngagementObservation(
  input: EngagementInput,
): EngagementObservation | null {
  const {
    elapsedTotalMs,
    elapsedActiveMs,
    ledger,
    minFirstSeconds,
    minDeltaSeconds = DEFAULT_MIN_DELTA_SECONDS,
  } = input;

  // Clamp: elapsed values are monotonic in practice, but a clock adjustment or
  // a caller bug must never produce a negative "delta" that rewinds the ledger.
  const totalMs = Math.max(elapsedTotalMs, ledger.reportedTotalMs);
  const activeMs = Math.max(elapsedActiveMs, ledger.reportedActiveMs);

  const deltaTotalSeconds = Math.round((totalMs - ledger.reportedTotalMs) / 1000);
  const deltaActiveSeconds = Math.round((activeMs - ledger.reportedActiveMs) / 1000);

  const isFirst = ledger.reportedTotalMs === 0;
  if (isFirst) {
    // First observation for this page: honor the engagement floor so a bounce
    // still produces nothing at all. FLOOR, not round — the page must genuinely
    // reach the threshold; rounding would admit a 9.5s bounce as "10 seconds".
    if (Math.floor(totalMs / 1000) < minFirstSeconds) return null;
  } else if (deltaTotalSeconds < minDeltaSeconds) {
    return null;
  }

  return {
    seconds: deltaTotalSeconds,
    activeSeconds: deltaActiveSeconds,
    ledger: { reportedTotalMs: totalMs, reportedActiveMs: activeMs },
  };
}
