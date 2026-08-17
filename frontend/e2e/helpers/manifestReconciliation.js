"use strict";

/**
 * #1915 [P1] — the manifest's verdict is DERIVED from the spec's outcome.
 *
 * ── THE DEFECT ──
 *
 * `journey.finish()` seals its record and attaches it BEFORE the spec's own
 * `expect()` calls run. It has to: it takes the terminal screenshot, and the
 * evaluator's verdict is the thing it throws on. So a spec's domain assertions
 * land AFTER the record already exists, and nothing reconciled the two.
 *
 * Measured on run 32055873206 (pack `league-cards`, the first run of that pack
 * that ever reached the page): `league.cards.one_system` was stamped
 *
 *     ✓ league.cards.one_system [desktop] → pass
 *     ✓ league.cards.one_system [mobile]  → pass
 *
 * while the assertion that grades them — ruling 047's binary row count — failed
 * on BOTH viewports. Playwright reported 4 failed; the manifest reported
 * `failed=2`, counting only the network journey. The defect appeared nowhere in
 * the artifact downstream consumers read.
 *
 * The run survived on luck. `result=fail` came from a DIFFERENT check. Had the
 * network journey been clean, this rail would have published a GREEN manifest
 * over a real page defect — not a missing red, a false green.
 *
 * That is ruling 072's class — an instrument reporting confidently about
 * something it never measured — reproduced inside the grader itself, which is
 * the worst place for it: every consumer of this rail inherits it. It is also
 * gotcha #53 (the emptier reading taken as a fact) and gotcha #54 (a gate that
 * never ran reporting success).
 *
 * ── WHY THIS IS A PURE HELPER AND NOT INLINE IN THE REPORTER ──
 *
 * Same reason `evaluateJourney` is: the false-green cases have to be provable
 * mechanically, with no browser and no Playwright install. The reporter imports
 * `@playwright/test/reporter` and the audit fixture, so a contract test cannot
 * require it — and a guard that only runs when a package install succeeds is a
 * guard that will be skipped on the day it matters.
 */

const { redactText } = require("./redaction");

/**
 * Reconcile ONE journey record against the outcome of the test that produced it.
 *
 * Downgrade-only, deliberately. A record that graded itself non-pass keeps that
 * verdict even when the test went green, because `finish()` throws on a non-pass
 * verdict — a green test over a failed record means a spec CAUGHT that throw,
 * and the honest response is to make the swallowing visible, not to believe the
 * quieter of two disagreeing signals.
 *
 * @param {object} record          the journey record as `finish()` sealed it
 * @param {object} outcome
 * @param {boolean} outcome.attemptFailed  `result.status !== test.expectedStatus`
 * @param {string}  outcome.status         Playwright's status string, for the detail
 * @param {string=} outcome.errorMessage   the test's first error, if any
 * @returns {object} the same record, reconciled in place
 */
function reconcileJourneyVerdict(record, outcome) {
  if (!record) return record;
  const attemptFailed = Boolean(outcome && outcome.attemptFailed);
  const status = String((outcome && outcome.status) || "unknown");

  if (attemptFailed && record.result === "pass") {
    record.result = "fail";
    record.assertions = [
      ...(record.assertions || []),
      {
        assertion_id: "spec.assertions_passed",
        ok: false,
        detail:
          `the evaluator graded this journey 'pass', but the test ended "${status}" — ` +
          `the spec's own assertions run AFTER journey.finish() seals the record. ` +
          `First error: ` +
          redactText((outcome && outcome.errorMessage) || "no error message recorded"),
      },
    ];
    return record;
  }

  if (!attemptFailed && record.result && record.result !== "pass") {
    record.assertions = [
      ...(record.assertions || []),
      {
        assertion_id: "spec.assertions_passed",
        ok: false,
        detail:
          `the test ended "${status}" while the journey graded '${record.result}' — ` +
          `journey.finish() throws on a non-pass verdict, so something in the spec ` +
          `caught it. The journey verdict stands.`,
      },
    ];
  }

  return record;
}

/**
 * Reconcile the RUN's two failure counts (#1915 acceptance 2).
 *
 * Per-journey derivation makes these agree by construction. "By construction" is
 * exactly the kind of claim that rots the first time somebody adds a branch, so
 * it is checked rather than trusted — and a mismatch forces the run non-green,
 * because a manifest whose own two readings disagree cannot be authority for
 * anything, which is a worse state to publish than a known red.
 *
 * @param {{journeys: Array<{result?: string}>, runnerFailures: number}} input
 * @returns {{forcedResult: string|undefined, notes: string[], manifestFailures: number}}
 */
function reconcileRunCounts(input) {
  const journeys = Array.isArray(input && input.journeys) ? input.journeys : [];
  const runnerFailures = Number((input && input.runnerFailures) || 0);
  const manifestFailures = journeys.filter((j) => j && j.result !== "pass").length;
  const notes = [];
  let forcedResult;

  if (manifestFailures !== runnerFailures) {
    forcedResult = "fail";
    notes.push(
      `RECONCILIATION FAILURE (#1915): the manifest records ${manifestFailures} non-pass ` +
        `journey(s) but the runner reported ${runnerFailures} failing test slot(s). These are ` +
        `two readings of the same run and they must agree. Do not read this manifest as ` +
        `authority for any journey until the divergence is explained.`
    );
  }

  return { forcedResult, notes, manifestFailures };
}

module.exports = { reconcileJourneyVerdict, reconcileRunCounts };
