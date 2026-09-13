import { isAdminAuthError } from "@/lib/adminFetch";

/**
 * #6024 — WHAT A FAILED ADMIN FETCH IS ALLOWED TO SAY ABOUT THE SYSTEM.
 *
 * Alex's 9/13 screenshot: under "Is the system healthy?", a red **Critical**
 * badge whose summary read `Admin API error 403: Invalid admin secret`. The
 * API was fine — the same endpoints answered 200 to a valid token in the same
 * minute. The page had turned "you are not authorized to ask" into "the answer
 * is: broken".
 *
 * Three admin pages mapped `error → "critical"` with no look at the status.
 * This is the one place that decides, so they cannot drift apart again.
 *
 * The rule: a 401/403 is a statement about the CREDENTIAL and earns the
 * `unauthorized` state. Every other failure is still unknown-and-possibly-bad
 * and keeps reading `critical` — this narrows what a 403 may claim, it does not
 * soften anything else.
 */
export type AdminHeaderStatus =
  | "good"
  | "warning"
  | "critical"
  | "loading"
  | "unauthorized";

/**
 * The status a page header shows for a failed admin fetch.
 * Callers pass the error only — the healthy/loading branches stay theirs.
 */
export function adminErrorStatus(err: unknown): AdminHeaderStatus {
  return isAdminAuthError(err) ? "unauthorized" : "critical";
}

/**
 * The summary line for a failed admin fetch.
 *
 * For an auth failure this replaces the raw `Admin API error 403: Invalid admin
 * secret` with a sentence that says whose problem it is and what to do — the
 * recovery control sits directly beneath it (`AdminAuthNotice`). For anything
 * else the underlying message is still the most useful thing we can print, so
 * it is passed through unchanged.
 */
export function adminErrorSummary(err: unknown): string {
  if (isAdminAuthError(err)) {
    return "This tab's admin secret was rejected — the system's health is unknown, not bad.";
  }
  return err instanceof Error ? err.message : String(err);
}
