// L2-241 Item 2 — the foreground failure terminal, as pure, testable logic.
//
// The defect this rail closes (C132 `current-three-attempt-skeleton-retention`
// → RETRIES_HOLD_SKELETON): a slow or aborted INITIAL feed request keeps the
// loading skeleton on screen while a generic retry sequence runs, so the reader
// stares at placeholders with no honest terminal and no retry action of their
// own. The other feed terminals already exist on the page — an errored request
// shows a retry message, an unavailable page shows the retry notice, a complete
// empty feed says "all caught up", and `keepPreviousData` preserves last-good.
// The one missing state is the SLOW request that has neither errored nor
// resolved: today it is skeletons forever.
//
// Reaching an honest terminal for a slow-but-not-failed request requires a
// number — how long is too long — and that number is a PRODUCT decision, not a
// thing this code may invent. So `budgetMs` is an input:
//
//   • budgetMs = null  — no approved foreground budget. A slow request stays in
//     `loading` (the current behavior); only an abort or an outright failure can
//     terminate the foreground. This mirrors C132's FOREGROUND_BUDGET_NEEDS_
//     APPROVAL: a foreground terminal that FORCES itself on a slow request
//     without an approved budget is refused, so we do not force one.
//   • budgetMs = <n>   — once the request has been pending for n ms, the
//     foreground terminates honestly (last-good if present, otherwise a retry),
//     and only THEN may a background retry run (never owning the foreground).
//
// This file is deliberately pure so its conformance to C132 is unit-testable
// without a browser, the same way lib/discover/feedAvailability.ts is.

/**
 * The single approved foreground budget for the initial feed request, in ms.
 *
 * `null` until Alex approves a value: the rail below is wired and inert, and
 * flipping this to a number activates the slow-request terminal with no other
 * code change. Do NOT invent a value here — an unapproved timeout is exactly
 * what C132 refuses.
 */
export const FOREGROUND_FEED_BUDGET_MS: number | null = null;

export type ForegroundState = "loading" | "terminal-retry" | "terminal-last-good";

export interface ForegroundTerminalInput {
  /** ms the initial request has been pending (0 before it starts). */
  elapsedMs: number;
  /** The APPROVED foreground budget, or null when none is approved. */
  budgetMs: number | null;
  /** The initial request aborted (teardown or client timeout). */
  aborted: boolean;
  /** The initial request failed outright (network/5xx surfaced as an error). */
  failed?: boolean;
  /** Whether last-good cards are currently on screen. */
  hasLastGood: boolean;
}

export interface ForegroundDecision {
  /** The honest foreground state. */
  state: ForegroundState;
  /** Show the loading skeleton? Only ever true in `loading`. */
  showSkeleton: boolean;
  /**
   * May a background retry run now? Only once the foreground has terminated —
   * a retry that runs while the skeleton is still up would OWN the foreground,
   * which C132 refuses (BACKGROUND_RETRY_OWNS_FOREGROUND).
   */
  allowBackgroundRetry: boolean;
  /** Bounded, identity-free reason token for telemetry/tests. */
  reason: string;
}

/**
 * Decide what the foreground shows for the initial feed request.
 *
 * An abort or an outright failure ALWAYS terminates honestly — that needs no
 * budget, and is the RETRIES_HOLD_SKELETON fix. A slow-but-pending request
 * terminates only when an approved budget has been exceeded; with no approved
 * budget it stays `loading` rather than inventing a timeout.
 */
export function decideForegroundTerminal(input: ForegroundTerminalInput): ForegroundDecision {
  const { elapsedMs, budgetMs, aborted, failed = false, hasLastGood } = input;
  const budgetExceeded =
    typeof budgetMs === "number" && Number.isFinite(budgetMs) && budgetMs > 0 && elapsedMs >= budgetMs;

  if (!aborted && !failed && !budgetExceeded) {
    return {
      state: "loading",
      showSkeleton: true,
      allowBackgroundRetry: false,
      reason: budgetMs == null ? "no-approved-budget:waiting" : "within-budget",
    };
  }

  const cause = aborted ? "aborted" : failed ? "failed" : "budget-exceeded";

  // Terminated honestly. Preserve last-good when present; otherwise offer retry.
  // Either way the skeleton is gone and a background retry may now run WITHOUT
  // owning the foreground.
  if (hasLastGood) {
    return {
      state: "terminal-last-good",
      showSkeleton: false,
      allowBackgroundRetry: true,
      reason: `${cause}:last-good`,
    };
  }
  return {
    state: "terminal-retry",
    showSkeleton: false,
    allowBackgroundRetry: true,
    reason: `${cause}:retry`,
  };
}

export interface ResponsePrincipal {
  /** Monotonic generation of the request this response answers. */
  responseGeneration: number;
  /** The generation currently rendered. */
  currentGeneration: number;
  /** The principal (user id or "anon") the response was fetched for. */
  responsePrincipal: string;
  /** The principal currently rendered. */
  currentPrincipal: string;
}

/**
 * Guard against a late/stale response overwriting a newer generation or a
 * different principal (C132 STALE_PRINCIPAL_OVERWRITE). A late anonymous
 * response must never land on a signed-in generation, and a superseded
 * generation must never replace the current one.
 *
 * On the Sports page this is already enforced structurally — anon and signed-in
 * reads live under DISTINCT SWR keys (see lib/sports/feedKey.ts) so SWR cannot
 * cross them — but the rule is expressed here too so any manual page merge can
 * check it and the invariant is testable in one place.
 */
export function shouldApplyResponse(input: ResponsePrincipal): boolean {
  return (
    input.responseGeneration === input.currentGeneration &&
    input.responsePrincipal === input.currentPrincipal
  );
}
