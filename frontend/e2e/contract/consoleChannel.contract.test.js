"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  isResourceLoadConsoleError,
  partitionConsoleErrors,
} = require("../helpers/consoleChannel");
const { evaluateJourney } = require("../helpers/journey");

/**
 * UX-P058 (#1610/#1612/#1614) — the console channel stops grading third-party
 * noise, and STILL grades everything it was the only witness to.
 *
 * Both directions are pinned deliberately (gotcha #43). A suppression proved only
 * in the quiet direction is how a mute button ships: the tests that matter most
 * here are the ones asserting a real error STILL REDS.
 */

const CHROMIUM_404 = "Failed to load resource: the server responded with a status of 404 ()";
const CHROMIUM_500 = "Failed to load resource: the server responded with a status of 500 ()";
const CHROMIUM_NET = "Failed to load resource: net::ERR_CONNECTION_REFUSED";
const REAL_JS_ERROR = "TypeError: Cannot read properties of undefined (reading 'threshold')";

test("the browser's resource-load complaint is recognised in BOTH its forms", () => {
  assert.equal(isResourceLoadConsoleError(CHROMIUM_404), true);
  assert.equal(isResourceLoadConsoleError(CHROMIUM_500), true);
  assert.equal(isResourceLoadConsoleError(CHROMIUM_NET), true);
});

test("a genuine JS error is NOT a resource-load message", () => {
  assert.equal(isResourceLoadConsoleError(REAL_JS_ERROR), false);
  assert.equal(isResourceLoadConsoleError("Warning: validateDOMNesting"), false);
});

test("the match is ANCHORED — an app error that QUOTES the phrase is not swallowed", () => {
  // The anchor is the whole reason this is a regex constant and not `includes()`.
  // An app throwing its own message about loading a resource is a real defect.
  assert.equal(
    isResourceLoadConsoleError("ChartError: failed to load resource for /api/feed"),
    false
  );
  assert.equal(
    isResourceLoadConsoleError("Uncaught Error: Failed to load resource bundle"),
    false
  );
});

test("non-string input never counts as a resource message", () => {
  for (const value of [null, undefined, 42, {}, []]) {
    assert.equal(isResourceLoadConsoleError(value), false);
  }
});

test("partition routes each message to the channel that can grade it", () => {
  const { scriptErrors, resourceErrors } = partitionConsoleErrors([
    CHROMIUM_404,
    REAL_JS_ERROR,
    CHROMIUM_NET,
  ]);
  assert.deepEqual(scriptErrors, [REAL_JS_ERROR]);
  assert.deepEqual(resourceErrors, [CHROMIUM_404, CHROMIUM_NET]);
});

test("partition tolerates a missing/!array observation", () => {
  assert.deepEqual(partitionConsoleErrors(undefined), { scriptErrors: [], resourceErrors: [] });
});

// --- The grader half: what the split means for a journey's verdict. ---

/** A journey observation that is healthy apart from what a test injects. */
function healthy(overrides) {
  return {
    journeyId: "contract.console",
    urlPath: "/",
    finalOrigin: "https://www.bainluck.com",
    canonicalOrigins: ["https://www.bainluck.com"],
    redirectChain: [],
    shaMatch: true,
    infra: null,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: true,
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    artifacts: [{ name: "a.png", path: "artifacts/a.png", sha256: "x".repeat(64), bytes: 1 }],
    ...overrides,
  };
}

const idsOf = (verdict, ok) =>
  verdict.assertions.filter((a) => a.ok === ok).map((a) => a.assertion_id);

test("a page whose ONLY console noise is a third-party 404 is GREEN on the console channel", () => {
  // This is #1610/#1612/#1614: election, tennis and combat all RENDER CORRECTLY.
  const { scriptErrors, resourceErrors } = partitionConsoleErrors([CHROMIUM_404, CHROMIUM_404]);
  const verdict = evaluateJourney(
    healthy({ consoleErrors: scriptErrors, consoleResourceErrors: resourceErrors })
  );
  assert.ok(!idsOf(verdict, false).includes("console.no_errors"));
});

test("a REAL JS error still reds console.no_errors — the non-vacuous direction", () => {
  const { scriptErrors, resourceErrors } = partitionConsoleErrors([CHROMIUM_404, REAL_JS_ERROR]);
  const verdict = evaluateJourney(
    healthy({ consoleErrors: scriptErrors, consoleResourceErrors: resourceErrors })
  );
  assert.ok(idsOf(verdict, false).includes("console.no_errors"));
});

test("a FIRST-PARTY 404 still reds, on the channel that can name it", () => {
  // Coverage is preserved: the console channel yields the fact, it does not lose it.
  const verdict = evaluateJourney(
    healthy({
      consoleErrors: [],
      consoleResourceErrors: [CHROMIUM_404],
      failedRequests: [
        {
          url: "https://api.bainluck.com/api/event/event%3Acycling%3Atour-de-france-2026",
          method: "GET",
          status: 404,
          failure: null,
        },
      ],
    })
  );
  assert.ok(idsOf(verdict, false).includes("network.no_unexpected_failures"));
});

test("the manifest SAYS how many resource messages were set aside", () => {
  // A check that quietly grades less than its name suggests is how a mute button
  // hides. The count is recorded, so a reader can see what was not graded here.
  const verdict = evaluateJourney(
    healthy({ consoleErrors: [], consoleResourceErrors: [CHROMIUM_404, CHROMIUM_NET] })
  );
  const line = verdict.checked_clean.find((c) =>
    c.startsWith("console.resource_errors_graded_on_network")
  );
  assert.ok(line, "the set-aside count must be recorded in checked_clean");
  assert.match(line, /2 resource-load message\(s\)/);
});
