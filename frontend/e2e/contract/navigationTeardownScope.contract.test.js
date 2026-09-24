"use strict";

/**
 * #1679 P1 (C244) — the navigation-teardown allowance must be abort-only.
 *
 * `isNavigationCancellation` admitted `net::err_blocked_by_client`,
 * `interrupted`, and `context or browser has been closed` with no navigation
 * proof — no timing, no frame, no resource type. The collector stamps an abort
 * packet ONLY for ERR_ABORTED/aborted, so those three carried no teardown
 * evidence at all, yet a blocked request on a declared-allowance URL (e.g.
 * event-page's `_rsc=`) vanished from `network.no_unexpected_failures`, and
 * from the volume count unconditionally. The false-negative sequel to #1648.
 *
 * These tests pin the narrowed contract at both levels: the predicate, and
 * both graders end to end. The measured teardown phenomenon
 * (`net::ERR_ABORTED` on RSC prefetches) stays excused throughout.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  NAVIGATION_CANCEL_FAILURES,
  isNavigationCancellation,
  abortAllowanceMatches,
} = require("../helpers/navigationAborts");
const { classifyErrorVolume } = require("../helpers/errorVolume");
const { evaluateJourney } = require("../helpers/journey");

const RSC_URL = "https://bainluck.com/sports?_rsc=9f3k2";

const NON_ABORTS = [
  "net::ERR_BLOCKED_BY_CLIENT",
  "interrupted",
  "context or browser has been closed",
];

const ABORTS = ["net::ERR_ABORTED", "aborted", "  NET::err_aborted  "];

test("#1679 P1: blocked, interrupted and browser-closed are NOT navigation cancellations", () => {
  for (const failure of NON_ABORTS) {
    assert.equal(
      isNavigationCancellation({ url: RSC_URL, failure }),
      false,
      `${failure} must stay graded`
    );
  }
  assert.ok(!NAVIGATION_CANCEL_FAILURES.has("net::err_blocked_by_client"));
  assert.ok(!NAVIGATION_CANCEL_FAILURES.has("interrupted"));
  assert.ok(!NAVIGATION_CANCEL_FAILURES.has("context or browser has been closed"));
});

test("#1679 P1: genuine aborts still are", () => {
  for (const failure of ABORTS) {
    assert.equal(
      isNavigationCancellation({ url: RSC_URL, failure }),
      true,
      `${failure} must stay excusable`
    );
  }
});

test("#1679 P1: a declared allowance cannot excuse a non-abort on its own URL", () => {
  for (const failure of NON_ABORTS) {
    assert.equal(
      abortAllowanceMatches({ url: RSC_URL, failure }, "_rsc=", {}),
      false,
      `${failure} on ${RSC_URL} must not match the allowance`
    );
  }
  assert.equal(
    abortAllowanceMatches({ url: RSC_URL, failure: "net::ERR_ABORTED" }, "_rsc=", {}),
    true,
    "the measured teardown abort must still match"
  );
});

function journeyWith(failedRequests, allowedNavigationAborts) {
  return evaluateJourney({
    realCardFound: true,
    firstCardMs: 100,
    mainRegion: { state: "ready", nonBlank: true, charCount: 6000 },
    consoleErrors: [],
    consoleResourceErrors: [],
    pageErrors: [],
    failedRequests,
    allowedFailures: [],
    allowedConsoleErrors: [],
    allowedNavigationAborts,
    surfaceMarkers: [],
    surfaceText: null,
    artifacts: [{ name: "t.png", sha256: "abc" }],
    contentMode: "card",
    telemetry: [],
    telemetryExpectation: null,
  });
}

function networkVerdict(verdict) {
  return verdict.assertions.find((a) => a.assertion_id === "network.no_unexpected_failures");
}

test("#1679 P1 end to end: blocked/interrupted/closed fail network.no_unexpected_failures even on an allowance URL", () => {
  for (const failure of NON_ABORTS) {
    const verdict = journeyWith(
      [{ url: RSC_URL, method: "GET", status: null, failure }],
      ["_rsc="]
    );
    assert.equal(
      networkVerdict(verdict).ok,
      false,
      `${failure} on an allowance URL must fail the per-error grader`
    );
  }
  const control = journeyWith(
    [{ url: RSC_URL, method: "GET", status: null, failure: "net::ERR_ABORTED" }],
    ["_rsc="]
  );
  assert.equal(networkVerdict(control).ok, true, "the measured abort stays excused");
});

test("#1679 P1 end to end: non-aborts count toward request volume", () => {
  const volume = classifyErrorVolume(
    {
      consoleErrors: [],
      failedRequests: NON_ABORTS.map((failure) => ({
        url: RSC_URL,
        method: "GET",
        status: null,
        failure,
      })),
    },
    {}
  );
  assert.equal(volume.requests.total, 3, "all three non-aborts must be counted");
  assert.equal(volume.requests.navigation_cancelled_excluded, 0);
});
