"use strict";

/**
 * UX-P047 (#1648 P1, Fable ruling 2026-08-10) — ONE home for "is this aborted
 * request excusable, and what excuses it".
 *
 * THE DEFECT THIS EXISTS TO MAKE IMPOSSIBLE. Two graders read the same
 * `failed_requests` array and disagreed **0 vs 1 in the same manifest**:
 *
 *   "checked_clean": [ "network.failure_volume_within_policy (0 failed request(s) ...)" ]
 *   "assertions":    [ { "assertion_id": "network.no_unexpected_failures", "ok": false,
 *                        "detail": "1 failed request(s): ...?_rsc=... net::ERR_ABORTED" } ]
 *
 * `errorVolume` excluded navigation cancellations unconditionally; `journey`
 * consulted the same predicate only behind a declared allowance. #1649 imported
 * the predicate to stop exactly this drift, and the drift survived anyway —
 * because the two graders still owned separate DECISIONS built from it.
 *
 * So the shared unit is no longer the predicate. It is the whole decision:
 * both graders import `isNavigationCancellation`, `isFeedRequest` AND
 * `abortAllowanceMatches` from here, and neither restates any of them.
 *
 * SHAPE A IS NEVER EXCUSABLE, IN EITHER GRADER. An aborted `/api/feed` is a real
 * open defect (#1525) that is invisible to the backend's own metrics — this rail
 * is the only place it surfaces. `isFeedRequest` is checked inside
 * `abortAllowanceMatches` and again by the volume grader, and both directions
 * are asserted in the contract suite.
 *
 * PURE: no I/O, no clock.
 */

/**
 * The Next.js RSC prefetch marker. Shared rather than restated per spec — two
 * specs declaring the same allowance from two string literals is the same drift
 * this module exists to end, one level up.
 */
const RSC_PREFETCH = "_rsc=";

/**
 * Failures caused by tearing down a navigation are not product defects: the
 * browser cancels in-flight requests when the page navigates away, and Next
 * prefetches links on hover and in viewport then abandons what it no longer
 * needs. Counting them makes a threshold a function of how much the spec
 * navigates and how fast the runner is — #1600 saw the same build produce
 * 2036 -> 611 -> 208 failed requests for exactly this reason.
 *
 * Matched narrowly and case-insensitively — an abort code, not a substring of
 * an arbitrary message.
 */
const NAVIGATION_CANCEL_FAILURES = new Set([
  "net::err_aborted",
  "net::err_blocked_by_client",
  "aborted",
  "interrupted",
  "context or browser has been closed",
]);

function isNavigationCancellation(failure) {
  if (!failure) return false;
  if (failure.navigationCancelled === true) return true;
  const text = String(failure.failure || "").trim().toLowerCase();
  if (!text) return false;
  return NAVIGATION_CANCEL_FAILURES.has(text);
}

/**
 * Shape A — the one thing no allowance may ever cover.
 *
 * Both wire shapes are honoured: `describeAbort` writes the flag under `abort`,
 * while a caller constructing an observation by hand may set it at the top
 * level. Reading only one of them is how this guard would silently stop working.
 */
function isFeedRequest(failure) {
  if (!failure) return false;
  if (failure.isFeedRequest === true) return true;
  return !!(failure.abort && failure.abort.is_feed_request === true);
}

/**
 * An allowance is either a bare substring (STRICT — it must fire somewhere in
 * the run) or `{ match, intermittent: true, issue }` for a phenomenon MEASURED
 * to be racy (INT-034). These two readers live here so the graders and the
 * run-level expiry check cannot disagree about what a declaration MEANS, which
 * is the same class of drift as disagreeing about what it matches.
 */
function allowanceMatch(a) {
  return typeof a === "string" ? a : String((a && a.match) || "");
}

function allowanceIsIntermittent(a) {
  return typeof a === "object" && a !== null && a.intermittent === true;
}

/**
 * Does one DECLARED allowance excuse one failed request?
 *
 * Three conditions, all required: it really is a navigation cancellation, it is
 * not a feed request, and its URL contains the declared token. Anything that is
 * not an abort — a 4xx, a 5xx, a DNS failure — is untouched by a declaration
 * and still fails on a declared URL.
 */
function abortAllowanceMatches(failure, allowance) {
  if (!isNavigationCancellation(failure)) return false;
  if (isFeedRequest(failure)) return false;
  const needle = allowanceMatch(allowance);
  if (!needle) return false;
  return String((failure && failure.url) || "").includes(needle);
}

/** The declared allowances that actually matched something in this journey. */
function firedAllowances(failedRequests, allowances) {
  const failures = Array.isArray(failedRequests) ? failedRequests : [];
  const declared = Array.isArray(allowances) ? allowances : [];
  return declared.filter((allowance) =>
    failures.some((f) => abortAllowanceMatches(f, allowance))
  );
}

/**
 * RUN-LEVEL EXPIRY (the Fable ruling), for STRICT allowances only.
 *
 * An allowance nobody can see expire outlives its reason and quietly covers the
 * next failure that happens to match. #1525 is right about that, and the
 * per-journey version of the check was still wrong: a Next viewport prefetch is
 * RACY. `discover-smoke` never clicks — desktop saw one cancelled prefetch and
 * mobile saw none, in the same run — so a mandatory-fire-per-journey allowance
 * converts a flaky red into a different flaky red.
 *
 * Firing is therefore a property of the RUN, not of a journey: an allowance must
 * fire SOMEWHERE, and one that fires nowhere across the whole run is red. The
 * expiry property is preserved exactly; only its scope moves.
 */
function unfiredAllowances(journeys) {
  const list = Array.isArray(journeys) ? journeys : [];
  const declared = new Set();
  const fired = new Set();
  for (const j of list) {
    for (const a of (j && j.declared_navigation_allowances) || []) declared.add(a);
    for (const a of (j && j.fired_navigation_allowances) || []) fired.add(a);
  }
  return [...declared].filter((a) => !fired.has(a)).sort();
}

module.exports = {
  RSC_PREFETCH,
  allowanceMatch,
  allowanceIsIntermittent,
  NAVIGATION_CANCEL_FAILURES,
  isNavigationCancellation,
  isFeedRequest,
  abortAllowanceMatches,
  firedAllowances,
  unfiredAllowances,
};
