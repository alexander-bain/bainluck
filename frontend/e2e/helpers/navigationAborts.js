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
 * The RSC prefetch allowance in its MEASURED-INTERMITTENT form, declared once
 * for every spec that has not measured its own base rate.
 *
 * UX-P057. `discover-smoke` owned a local copy of this object and eight specs
 * owned nothing at all — the allowance was opt-in, so the nightly pack filed
 * twelve issues describing Next.js cancelling its own prefetches. Eleven specs
 * assembling eleven copies of one token from one string literal is the drift
 * this module exists to end, one level up; so the whole DECLARATION is shared,
 * not just the token.
 *
 * WHY INTERMITTENT AND NOT STRICT, for the specs adopting it here. A strict
 * allowance must fire somewhere in the run or the run is red, and that property
 * is only safe once you have measured that it does. UX-P047 measured
 * `discover-smoke` at 2 runs in 3 — one clean run in three would have gone red
 * on `network.declared_allowances_fired`, trading a false red for a different
 * false red. None of the eight specs adopting this has a measured base rate, so
 * strict could only manufacture reds. Intermittent is exempt from run-level
 * expiry and therefore cannot.
 *
 * `event-page` deliberately keeps the bare-string STRICT form: it measured 7-12
 * aborts per journey across 8 of 8 journeys and two dispatches, so it has earned
 * the expiry property. Do not downgrade a measured allowance to silence a red.
 *
 * Expiry has not been abandoned, only relocated: `issue` ties every intermittent
 * declaration to #1525, and it retires when #1525 does — or sooner, for any spec
 * whose base rate someone measures.
 *
 * Shape A is untouched. `abortAllowanceMatches` refuses a feed request before it
 * ever consults this token, so an aborted `/api/feed` still fails everywhere.
 */
const RSC_PREFETCH_ABORT = Object.freeze({
  match: RSC_PREFETCH,
  issue: 1525,
  intermittent: true,
});

/**
 * THE INSTRUMENT-INDUCED CARVE-OUT (ruling 021 clause 3, amended 2026-08-18,
 * resolving #1908 M2 — owners #1662, #1668, #1783, #1667).
 *
 * The deadlock, which is why this is a ruling and not a patch: the consent
 * pack's METHOD is to navigate mid-load — grant, revoke, reload, open a second
 * tab — so cancelled in-flight requests are its exhaust. The rail's RULE is that
 * a cancelled `/api/feed` stays graded (#1525 Shape A), because it is invisible
 * to the backend's own metrics. Apply either alone and the other breaks: #1667
 * is a first-party aborted `/api/feed` in a journey whose own navigation aborted
 * it, which is a permanent red no product change can clear.
 *
 * The amendment resolves it by moving the guard off the PROXY and onto the
 * OUTCOME. Clause 3 was never about the request record; it is about #1909 — a
 * blank main region a user actually sees, produced by a feed fetch that failed
 * where the backend cannot see it. When the harness caused the navigation the
 * abort carries no information about the product; the blank region, one step
 * later, still carries all of it.
 *
 * So: **the abort is excusable; the aftermath is graded.** Four conditions, all
 * required, and all enforced below rather than trusted:
 *
 *   1. ATTRIBUTABLE — the failed request carries `abort.instrument_action`,
 *      stamped by the collector with the harness action in flight when it fired.
 *   2. DECLARED — the journey declares this allowance, so it stays visible and
 *      retirable like every other.
 *   3. AFTERMATH GRADED — the caller passes `{ aftermathGraded: true }`, which
 *      `journey.finish` sets only when `content.main_region_nonblank` was
 *      computed from MEASUREMENTS. Absent context is falsy, so a grader that
 *      forgets to pass it excuses nothing: this fails CLOSED, and Shape A
 *      survives a caller's oversight.
 *   4. SETTLED — the measurement branch polls until the region stops loading
 *      (UX-P094), so the aftermath is not a photograph of a skeleton.
 *
 * An abort NOBODY instrumented is untouched: never excusable, asserted in both
 * graders, exactly as ruled on 2026-08-10.
 */
const INSTRUMENT_NAVIGATION_ABORT = Object.freeze({
  match: "",
  issue: 1908,
  instrumentInduced: true,
  intermittent: true,
});

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
 * Is this failure THIRD-PARTY — an origin that is not ours?
 *
 * UX-P095. The collector stamps it, because origin membership is its knowledge
 * (`firstPartyOrigins`), and the decision to grade or not grade lives here,
 * because two graders read it. The flag is the ledger's, not a URL heuristic
 * re-derived per grader — that re-derivation is exactly the drift this module
 * exists to end.
 */
function isThirdParty(failure) {
  return !!(failure && failure.third_party === true);
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

function allowanceIsInstrumentInduced(a) {
  return typeof a === "object" && a !== null && a.instrumentInduced === true;
}

/**
 * Condition 1 — is this abort ATTRIBUTABLE to an action the harness issued?
 *
 * The collector stamps `abort.instrument_action` at the moment of the abort with
 * whatever harness action was in flight. An abort that fired while the harness
 * was doing nothing has no stamp and is therefore organic, whatever journey it
 * happened in. That distinction is the whole safety of the carve-out: without
 * it, "the consent pack navigates a lot" would excuse every abort in the pack.
 */
function isInstrumentInduced(failure) {
  if (!failure) return false;
  const action = failure.abort && failure.abort.instrument_action;
  if (typeof action === "string" && action.trim()) return true;
  return typeof failure.instrumentAction === "string" && !!failure.instrumentAction.trim();
}

/**
 * Condition 3 — has the caller PROVEN the aftermath is graded?
 *
 * Fails closed by construction: `undefined` context, a context without the flag,
 * or anything other than a literal `true` all mean "not proven", which means no
 * excuse. A carve-out whose safety condition defaults to satisfied is a
 * deletion with extra words.
 */
function aftermathIsGraded(context) {
  return !!(context && context.aftermathGraded === true);
}

/**
 * Does one DECLARED allowance excuse one failed request?
 *
 * ORDINARY allowances — three conditions, all required: it really is a
 * navigation cancellation, it is not a feed request, and its URL contains the
 * declared token. Anything that is not an abort — a 4xx, a 5xx, a DNS failure —
 * is untouched by a declaration and still fails on a declared URL.
 *
 * INSTRUMENT-INDUCED allowances — the ruling 021 amendment, and the ONLY route
 * by which a feed abort can be excused. It swaps the Shape A refusal for two
 * stricter conditions (attribution + a graded aftermath) rather than dropping
 * it, and every one of them is checked here, in the shared decision, so the two
 * graders cannot hold different views of what the carve-out means. `context` is
 * optional and its absence is a REFUSAL, not a default-allow.
 */
function abortAllowanceMatches(failure, allowance, context) {
  if (!isNavigationCancellation(failure)) return false;

  if (allowanceIsInstrumentInduced(allowance)) {
    if (!isInstrumentInduced(failure)) return false;
    if (!aftermathIsGraded(context)) return false;
    const scope = allowanceMatch(allowance);
    // An empty `match` means "any URL this harness action aborted". A non-empty
    // one narrows it, so a pack can carve out one endpoint without carving out
    // the rest.
    return scope ? String((failure && failure.url) || "").includes(scope) : true;
  }

  if (isFeedRequest(failure)) return false;
  const needle = allowanceMatch(allowance);
  if (!needle) return false;
  return String((failure && failure.url) || "").includes(needle);
}

/** The declared allowances that actually matched something in this journey. */
function firedAllowances(failedRequests, allowances, context) {
  const failures = Array.isArray(failedRequests) ? failedRequests : [];
  const declared = Array.isArray(allowances) ? allowances : [];
  return declared.filter((allowance) =>
    failures.some((f) => abortAllowanceMatches(f, allowance, context))
  );
}

/**
 * The non-vacuity guard, stated as a question the journey grader must answer.
 *
 * An instrument-induced allowance declared by a journey that produces no graded
 * aftermath is exactly the deletion condition 3 forbids: it would excuse the
 * abort and grade nothing in its place. Returns the offending declarations so
 * the grader can name them, rather than a bare boolean.
 */
function instrumentAllowancesMissingAftermath(allowances, context) {
  if (aftermathIsGraded(context)) return [];
  const declared = Array.isArray(allowances) ? allowances : [];
  return declared.filter(allowanceIsInstrumentInduced);
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
  RSC_PREFETCH_ABORT,
  INSTRUMENT_NAVIGATION_ABORT,
  allowanceMatch,
  allowanceIsIntermittent,
  allowanceIsInstrumentInduced,
  isInstrumentInduced,
  aftermathIsGraded,
  instrumentAllowancesMissingAftermath,
  NAVIGATION_CANCEL_FAILURES,
  isNavigationCancellation,
  isFeedRequest,
  isThirdParty,
  abortAllowanceMatches,
  firedAllowances,
  unfiredAllowances,
};
