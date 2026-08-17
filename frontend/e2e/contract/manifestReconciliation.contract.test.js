"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  reconcileJourneyVerdict,
  reconcileRunCounts,
} = require("../helpers/manifestReconciliation");

/**
 * #1915 [P1] — the false GREEN inside the grader.
 *
 * These drive the same reconciliation the reporter drives, with no browser and
 * no Playwright install, so a fixture proven to fail here cannot pass in a real
 * run. Per #1791 / C-SA-1, each one is written to FAIL against the pre-fix code
 * — a reporter that recorded `verdict.result` and never looked at the test's
 * outcome passes none of these.
 *
 * The specimen: run 32055873206 stamped `league.cards.one_system` → `pass` on
 * both viewports while the ruling-047 assertion that grades them failed on both.
 * Playwright said 4 failed; the manifest said `failed=2`. The defect appeared
 * nowhere in the artifact downstream consumers read, and the run was only red at
 * all because a DIFFERENT check happened to fail.
 */

/** A record exactly as `journey.finish()` seals it on a clean evaluation. */
function sealedPass(overrides = {}) {
  return {
    journey_id: "league.cards.one_system",
    project: "desktop",
    result: "pass",
    assertions: [
      { assertion_id: "infra.browser_alive", ok: true, detail: null },
      { assertion_id: "content.main_region_nonblank", ok: true, detail: null },
    ],
    ...overrides,
  };
}

describe("#1915 — a journey verdict is DERIVED from the spec's outcome", () => {
  it("THE SPECIMEN: a sealed 'pass' whose spec assertion failed is downgraded", () => {
    const record = reconcileJourneyVerdict(sealedPass(), {
      attemptFailed: true,
      status: "failed",
      errorMessage:
        "Error: 15 binary/ies must occupy at most 15 rows; 16 rows means the two-row " +
        "(Yes AND No) presentation is back.",
    });

    assert.equal(record.result, "fail", "a failing spec must not publish a 'pass' journey");
    const added = record.assertions.find((a) => a.assertion_id === "spec.assertions_passed");
    assert.ok(added, "the downgrade must be VISIBLE as an assertion, not a silent flip");
    assert.equal(added.ok, false);
    assert.match(added.detail, /journey\.finish\(\) seals the record/);
  });

  it("carries the spec's own error into the manifest — the reader must not need the log", () => {
    const record = reconcileJourneyVerdict(sealedPass(), {
      attemptFailed: true,
      status: "failed",
      errorMessage: "Expected: <= 15  Received: 16",
    });
    const added = record.assertions.find((a) => a.assertion_id === "spec.assertions_passed");
    assert.match(added.detail, /Received: 16/);
  });

  it("a missing error message does not silently become a pass", () => {
    const record = reconcileJourneyVerdict(sealedPass(), {
      attemptFailed: true,
      status: "timedOut",
    });
    assert.equal(record.result, "fail");
    const added = record.assertions.find((a) => a.assertion_id === "spec.assertions_passed");
    assert.match(added.detail, /timedOut/);
    assert.match(added.detail, /no error message recorded/);
  });

  it("leaves a genuinely green journey completely alone", () => {
    // The other direction (gotcha #43). A reconciliation that failed everything
    // would satisfy every fixture above and destroy the rail.
    const record = reconcileJourneyVerdict(sealedPass(), {
      attemptFailed: false,
      status: "passed",
    });
    assert.equal(record.result, "pass");
    assert.equal(record.assertions.length, 2, "no assertion may be added to a clean journey");
  });

  it("NEVER upgrades: a green test over a failed record keeps the failure, annotated", () => {
    // `finish()` throws on a non-pass verdict, so this combination means a spec
    // CAUGHT the throw. Believing the quieter of two disagreeing signals is the
    // whole defect; the swallowing is surfaced instead.
    const record = reconcileJourneyVerdict(sealedPass({ result: "fail" }), {
      attemptFailed: false,
      status: "passed",
    });
    assert.equal(record.result, "fail", "a verdict must never be upgraded by the reporter");
    const added = record.assertions.find((a) => a.assertion_id === "spec.assertions_passed");
    assert.match(added.detail, /caught it/);
  });

  it("does not resurrect an infra_error as a fail", () => {
    const record = reconcileJourneyVerdict(sealedPass({ result: "infra_error" }), {
      attemptFailed: true,
      status: "failed",
    });
    assert.equal(record.result, "infra_error", "infra_error is terminal and outranks a spec failure");
  });
});

describe("#1915 acceptance 2 — the two failure counts must reconcile", () => {
  it("agreement produces no note and forces nothing", () => {
    const out = reconcileRunCounts({
      journeys: [{ result: "pass" }, { result: "fail" }],
      runnerFailures: 1,
    });
    assert.equal(out.forcedResult, undefined);
    assert.deepEqual(out.notes, []);
    assert.equal(out.manifestFailures, 1);
  });

  it("THE RUN 32055873206 SHAPE: manifest 2, runner 4 — hard error, run forced non-green", () => {
    const out = reconcileRunCounts({
      journeys: [
        { result: "pass" }, // one_system desktop — stamped pass over a failed assertion
        { result: "pass" }, // one_system mobile  — same
        { result: "fail" }, // adjacent_sports_feed desktop
        { result: "fail" }, // adjacent_sports_feed mobile
      ],
      runnerFailures: 4,
    });
    assert.equal(out.forcedResult, "fail");
    assert.equal(out.notes.length, 1);
    assert.match(out.notes[0], /RECONCILIATION FAILURE \(#1915\)/);
    assert.match(out.notes[0], /records 2 non-pass journey\(s\).*reported 4 failing/s);
    assert.match(out.notes[0], /not read this manifest as authority/);
  });

  it("a mismatch in the OTHER direction is equally hard", () => {
    // More manifest failures than runner failures is just as incoherent, and a
    // one-sided check would let the inverse drift through unnoticed.
    const out = reconcileRunCounts({
      journeys: [{ result: "fail" }, { result: "fail" }],
      runnerFailures: 0,
    });
    assert.equal(out.forcedResult, "fail");
    assert.match(out.notes[0], /records 2 non-pass journey\(s\).*reported 0 failing/s);
  });
});

describe("#1915 — the reporter actually routes through the reconciliation", () => {
  // The helper being correct proves nothing if the reporter stops calling it.
  const reporter = fs.readFileSync(
    path.join(__dirname, "..", "reporters", "auditReporter.ts"),
    "utf8",
  );

  it("calls both reconcilers", () => {
    assert.ok(reporter.includes("reconcileJourneyVerdict("), "per-journey derivation must be wired");
    assert.ok(reporter.includes("reconcileRunCounts("), "run-count reconciliation must be wired");
  });

  it("compares the attempt against the test's EXPECTED status, not a hardcoded 'passed'", () => {
    // `test.fail()` marks a test as expected-to-fail. Hardcoding "passed" would
    // downgrade those journeys forever and teach the next reader to delete the
    // check rather than fix it.
    assert.ok(
      reporter.includes("result.status !== test.expectedStatus"),
      "attemptFailed must be measured against test.expectedStatus",
    );
  });

  it("feeds the reconciled notes and forced result into the manifest", () => {
    assert.ok(reporter.includes("result: forcedResult"), "a reconciliation failure must reach run.result");
    assert.ok(reporter.includes("reconciliationNotes"), "the note must reach run.notes");
  });
});
