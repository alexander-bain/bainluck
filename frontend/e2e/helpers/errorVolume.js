"use strict";

/**
 * UX-P029 Item 3 — console/request error VOLUME policy.
 *
 * #1600: one load of the tennis tournament page produced ~2,036 failed requests
 * and ~2,175 console errors. Every one of those errors originated at a third
 * party (Wikipedia), and every one of them was OUR fault — an unbounded per-row
 * fan-out we initiated. That case is the reason this module exists, and it fixes
 * the shape of the rule:
 *
 *   1. **A third-party origin never exempts an error.** There is no origin-based
 *      filter here, deliberately. Who serves the 404 says nothing about who
 *      caused it; the request was ours to make or not make.
 *   2. **Volume is the signal, not origin.** A handful of errors is a fact worth
 *      RETAINING AS EVIDENCE. Thousands is a defect, and a different one — a
 *      loop, not a bug on one row.
 *   3. **A volume breach cannot be waived.** This is the load-bearing bit. The
 *      per-error assertions (`console.no_errors`, `network.no_unexpected_failures`)
 *      can be silenced per journey via `allowedConsoleErrors` / `allowedFailures`.
 *      Volume is computed BEFORE allowances and ignores them, so nobody can
 *      allowlist their way out of #1600 by declaring `en.wikipedia.org` once.
 *      An allowance is for a known benign error; it is not a licence to make two
 *      thousand requests.
 *
 * Pure: no Playwright, no network, no clock. Graded by contract fixtures.
 */

/**
 * Versioned so a threshold change is visible in the manifest and in any filed
 * issue, rather than silently re-grading history.
 */
const ERROR_VOLUME_POLICY_VERSION = "error-volume/v1";

/**
 * Threshold derivation (v1), stated rather than assumed:
 *
 *   * #1600 measured ~2,036 failed requests and ~2,175 console errors on one
 *     load. Any threshold that catches it must sit far below ~2,000.
 *   * A healthy page legitimately emits a small number: a blocked analytics
 *     beacon, one 404 favicon, a third-party widget that fails once. Those are
 *     single-digit, and they must stay EVIDENCE rather than becoming failures —
 *     the per-error assertions already grade them individually.
 *   * The gap between "a few" and "a loop" is wide and empty. 50 sits inside
 *     that gap: ~40x the benign case, ~40x below #1600. Nothing real is
 *     expected to land between 10 and 500, so the exact number is not delicate.
 *
 * Chosen at 50 for both channels. A per-row fan-out over a tennis draw (41
 * entrants) exceeds it on the SECOND pass, which is the point — the defect is
 * the repetition, and repetition is what we want caught early.
 */
const CONSOLE_ERROR_VOLUME_THRESHOLD = 50;
const REQUEST_FAILURE_VOLUME_THRESHOLD = 50;

/**
 * Stable reason codes. These are what the filer fingerprints on, so they must
 * NOT embed counts — a fingerprint containing "2036" files a fresh issue every
 * run as the number drifts, which is how a rail turns into a spammer.
 */
const REASON_CONSOLE_VOLUME = "CONSOLE_ERROR_VOLUME_EXCEEDED";
const REASON_REQUEST_VOLUME = "REQUEST_FAILURE_VOLUME_EXCEEDED";

/**
 * UX-P047 (#1648 P1) — the navigation-abort predicate MOVED to
 * `helpers/navigationAborts.js` and is re-exported here for existing callers.
 *
 * It used to live in this file, and `journey.js` imported it — which was not
 * enough: the two graders still owned separate DECISIONS built from one
 * predicate, and they disagreed 0 vs 1 on the same input. The shared unit is
 * now the whole decision, in one module both graders import.
 */
const {
  NAVIGATION_CANCEL_FAILURES,
  isNavigationCancellation,
  isFeedRequest,
  isInstrumentInduced,
  aftermathIsGraded,
} = require("./navigationAborts");

/** Origin of a redacted URL, or "unknown" when it cannot be parsed. */
function originOf(url) {
  const text = String(url || "");
  const match = /^([a-z][a-z0-9+.-]*:\/\/[^/?#]+)/i.exec(text);
  return match ? match[1].toLowerCase() : "unknown";
}

function summarizeOrigins(items, toUrl) {
  const counts = new Map();
  for (const item of items) {
    const origin = originOf(toUrl(item));
    counts.set(origin, (counts.get(origin) || 0) + 1);
  }
  // Descending by count, then origin, so the summary is deterministic.
  return [...counts.entries()]
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
    .map(([origin, count]) => ({ origin, count }));
}

/**
 * Classify one journey's error volume.
 *
 * `consoleErrors`: string[]  ·  `failedRequests`: {url, status?, failure?}[]
 *
 * Returns a plain object recorded in the manifest whether or not anything
 * breached — below the threshold the counts ARE the evidence.
 */
function classifyErrorVolume(observation, context) {
  const o = observation || {};
  const consoleErrors = Array.isArray(o.consoleErrors) ? o.consoleErrors : [];
  const rawFailures = Array.isArray(o.failedRequests) ? o.failedRequests : [];

  // Navigation teardown is excluded from the COUNT but kept visible, so an
  // exclusion can never be mistaken for an absence.
  //
  // UX-P047 (#1648 P1, Fable ruling): Shape A is never excusable HERE EITHER.
  // This grader previously excluded every navigation cancellation with no feed
  // guard at all, so an aborted `/api/feed` — the one abort that is a real
  // defect — was silently dropped from the volume count. The per-error grader
  // guarded it and this one did not, which is the same drift in its other
  // direction. One rule, both graders.
  // UX-P095 — ruling 021's instrument-induced carve-out, applied HERE TOO.
  //
  // Applying it in only one grader would recreate the 0-vs-1 disagreement this
  // module was split out to end: the per-error grader would excuse a
  // harness-caused feed abort while the volume grader still counted it, one
  // input, two verdicts. So the carve-out is part of the shared decision, with
  // the SAME two load-bearing conditions — attributable to a named harness
  // action, and an aftermath that was actually graded. Absent context is a
  // refusal, so an un-updated caller keeps the old, stricter behaviour.
  const carveOut = (f) =>
    isFeedRequest(f) && isInstrumentInduced(f) && aftermathIsGraded(context);
  const excusable = (f) =>
    isNavigationCancellation(f) && (!isFeedRequest(f) || carveOut(f));
  const cancelled = rawFailures.filter(excusable);
  const failures = rawFailures.filter((f) => !excusable(f));

  const consoleTotal = consoleErrors.length;
  const requestTotal = failures.length;

  // Distinct counts separate "one broken thing, hit N times" (a fan-out) from
  // "N different broken things" (a broken page). Both are defects; they are not
  // the same defect, and the filer benefits from being able to tell.
  const consoleDistinct = new Set(consoleErrors.map((t) => String(t))).size;
  const requestDistinct = new Set(failures.map((f) => String((f && f.url) || ""))).size;

  const consoleExceeded = consoleTotal > CONSOLE_ERROR_VOLUME_THRESHOLD;
  const requestExceeded = requestTotal > REQUEST_FAILURE_VOLUME_THRESHOLD;

  return {
    policy_version: ERROR_VOLUME_POLICY_VERSION,
    console: {
      total: consoleTotal,
      distinct: consoleDistinct,
      threshold: CONSOLE_ERROR_VOLUME_THRESHOLD,
      exceeded: consoleExceeded,
      reason_code: consoleExceeded ? REASON_CONSOLE_VOLUME : null,
    },
    requests: {
      total: requestTotal,
      distinct: requestDistinct,
      threshold: REQUEST_FAILURE_VOLUME_THRESHOLD,
      exceeded: requestExceeded,
      reason_code: requestExceeded ? REASON_REQUEST_VOLUME : null,
      navigation_cancelled_excluded: cancelled.length,
      by_origin: summarizeOrigins(failures, (f) => (f && f.url) || ""),
    },
  };
}

module.exports = {
  ERROR_VOLUME_POLICY_VERSION,
  CONSOLE_ERROR_VOLUME_THRESHOLD,
  REQUEST_FAILURE_VOLUME_THRESHOLD,
  REASON_CONSOLE_VOLUME,
  REASON_REQUEST_VOLUME,
  classifyErrorVolume,
  isNavigationCancellation,
};
