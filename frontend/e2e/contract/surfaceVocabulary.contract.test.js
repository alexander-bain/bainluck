"use strict";

/**
 * UX-P057 — `content.surface_vocabulary`: which surface rendered, not how much.
 *
 * WHAT THE RAIL COULD NOT ASK BEFORE. `route.expected_path` proves the URL and
 * `content.main_region_nonblank` proves a character count. A route that 200s
 * with the wrong surface, a generic error body, or a shell that never hydrated
 * its subject satisfies both of them — enough characters at the right address.
 *
 * #1650 is the standing example: `settled_props_verdict` grades a char count,
 * so "does the settled page speak the settled vocabulary" has been unanswerable
 * in this rail for six cycles.
 *
 * The two edges this suite exists to hold:
 *   - ONE marker suffices. Requiring all of them makes the assertion a copy of
 *     today's wording, which reds on any honest copy edit. A guard nobody
 *     believes is worse than no guard (UX-P053).
 *   - Declared markers with NO text is a FAILURE, never a skip. An unobserved
 *     surface is not a proven one.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { evaluateJourney } = require("../helpers/journey");
const { buildRunManifest } = require("../helpers/manifest");

/** A journey that passes everything else, so only the marker rule is in play. */
function observation(extra) {
  return {
    shaMatch: true,
    expectedPath: "/events/1",
    urlPath: "/events/1",
    realCardFound: true,
    firstCardMs: 100,
    mainRegionNonBlank: true,
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    ...extra,
  };
}

function findAssertion(result, id) {
  return result.assertions.find((a) => a.assertion_id === id) || null;
}

describe("content.surface_vocabulary", () => {
  it("is explicitly skipped, and SAID to be skipped, when no markers are declared", () => {
    const r = evaluateJourney(observation({}));
    assert.equal(findAssertion(r, "content.surface_vocabulary"), null);
    assert.ok(
      r.checked_clean.some((c) => c.includes("content.surface_vocabulary")),
      "an absent check must be recorded, never silently missing",
    );
  });

  it("passes when one declared marker appears", () => {
    const r = evaluateJourney(
      observation({
        surfaceMarkers: ["Player Props", "Final"],
        surfaceText: "Cleveland at Chicago — Final · Player Props",
      }),
    );
    assert.equal(findAssertion(r, "content.surface_vocabulary").ok, true);
  });

  it("passes on ONE of several — markers are alternatives, not a checklist", () => {
    // The copy-edit edge. "Final" alone is enough; demanding every marker would
    // make this assertion break the next time a heading is reworded.
    const r = evaluateJourney(
      observation({
        surfaceMarkers: ["Player Props", "Final", "What hit"],
        surfaceText: "…the game ended. Final.",
      }),
    );
    assert.equal(findAssertion(r, "content.surface_vocabulary").ok, true);
  });

  it("matches case-insensitively", () => {
    const r = evaluateJourney(
      observation({ surfaceMarkers: ["PLAYER PROPS"], surfaceText: "player props" }),
    );
    assert.equal(findAssertion(r, "content.surface_vocabulary").ok, true);
  });

  it("FAILS when the right amount of text says the wrong thing", () => {
    // The whole point: this text is long, non-blank, and served at the expected
    // path. Every other content check is green on it.
    const r = evaluateJourney(
      observation({
        surfaceMarkers: ["Player Props"],
        surfaceText: "Something went wrong. Please try again later.",
      }),
    );
    const a = findAssertion(r, "content.surface_vocabulary");
    assert.equal(a.ok, false);
    assert.match(a.detail, /none of 1 declared marker/);
    assert.equal(findAssertion(r, "content.main_region_nonblank").ok, true);
    assert.equal(findAssertion(r, "route.expected_path").ok, true);
  });

  it("FAILS when markers are declared but no text was observed", () => {
    const r = evaluateJourney(observation({ surfaceMarkers: ["Player Props"] }));
    const a = findAssertion(r, "content.surface_vocabulary");
    assert.equal(a.ok, false);
    assert.match(a.detail, /no surface text was observed/);
  });

  it("FAILS on empty observed text rather than treating it as a skip", () => {
    const r = evaluateJourney(
      observation({ surfaceMarkers: ["Player Props"], surfaceText: "   " }),
    );
    assert.equal(findAssertion(r, "content.surface_vocabulary").ok, false);
  });

  it("ignores blank entries in the declaration", () => {
    const r = evaluateJourney(observation({ surfaceMarkers: ["", "  "] }));
    assert.equal(findAssertion(r, "content.surface_vocabulary"), null);
  });

  it("a failed marker fails the journey, not merely the assertion", () => {
    const r = evaluateJourney(
      observation({ surfaceMarkers: ["Player Props"], surfaceText: "wrong page" }),
    );
    assert.notEqual(r.result, "pass");
  });
});

describe("surface-vocabulary coverage is a NUMBER in the manifest", () => {
  /**
   * This queue exists because an opt-in mechanism reached 3 of 11 specs and
   * nobody noticed — adoption was not recorded anywhere. A new opt-in check
   * that hides its own coverage would repeat exactly that, so the manifest
   * counts it.
   */
  function manifestOf(observations) {
    return buildRunManifest({
      runId: "1",
      runUrl: "https://github.com/alexander-bain/bainluck/actions/runs/1",
      pack: "deploy-smoke",
      trigger: "workflow_dispatch",
      startedAt: "2026-08-11T00:00:00.000Z",
      finishedAt: "2026-08-11T00:01:00.000Z",
      runnerStatus: "passed",
      baseUrl: "https://www.bainluck.com",
      apiBaseUrl: "https://api.bainluck.com",
      runtime: { node: "v20.11.0", playwright: "1.48.2", browser: "chromium-1140", os: "linux-x64" },
      journeys: observations.map((o, i) => {
        const r = evaluateJourney(o);
        return {
          journey_id: `j${i}`,
          project: "desktop",
          result: r.result,
          assertions: r.assertions,
          checked_clean: r.checked_clean,
        };
      }),
    });
  }

  it("counts journeys that assert their surface", () => {
    const m = manifestOf([
      observation({ surfaceMarkers: ["Final"], surfaceText: "Final" }),
      observation({}),
      observation({}),
    ]);
    assert.deepEqual(m.run.surface_vocabulary_coverage, { asserted: 1, total: 3 });
  });

  it("reports zero rather than omitting the field when nothing declares it", () => {
    const m = manifestOf([observation({}), observation({})]);
    assert.deepEqual(m.run.surface_vocabulary_coverage, { asserted: 0, total: 2 });
  });
});
