"use strict";

/**
 * #1908 M1 — the rail's self-inflicted 429s are classified, and #1909 survives it.
 *
 * The census (cycle 82) found 13 open issues that were 3 mechanisms and 0 product
 * defects in the consent claim — with ONE real bug buried inside them. The
 * dominant mechanism was the rail rate-limiting itself: 52 × 429 from
 * `api.bainluck.com` in a 107-second run, one runner IP, 60/min anonymous budget.
 *
 * The dangerous fix is the obvious one. "Stop filing on 429" reads as a
 * one-liner, and every one-liner shaped like it would ALSO have deleted
 * `consent.two_tabs [desktop]`'s `content.main_region_nonblank` failure — the
 * blank main region under rate limiting, #1909, the only finding in all thirteen
 * issues describing something a user could see. It failed on the SAME journey,
 * in the SAME run, wearing the same "consent audit" label.
 *
 * So the property under test is not "429s stop filing". It is:
 *
 *     429s stop filing AND the product assertion beside them still does.
 *
 * `test_the_real_defect_still_files` is the load-bearing test in this file.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const { evaluateJourney, RESULTS } = require("../helpers/journey");
const {
  consoleErrorsAreRateLimitEcho,
  isFirstPartyHost,
  isRateLimitEcho,
  isSelfInflictedRateLimit,
  networkFailuresAreSelfInflicted,
} = require("../helpers/rateLimit");
const { findingsFromManifest } = require("../helpers/sweepFiling");

const RL = (url = "https://api.bainluck.com/api/feed") => ({ url, status: 429 });

/** A journey observation that passes everything not under test. */
function observation(extra = {}) {
  return {
    journey_id: "consent.two_tabs",
    project: "desktop",
    url: "https://bainluck.com/discover",
    shaMatch: true,
    artifacts: [{ name: "screenshot.png", sha256: "a".repeat(64) }],
    failedRequests: [],
    consoleErrors: [],
    // A healthy page, so the ONLY thing these tests vary is the channel under
    // test. Without this the fixture fails on content assertions and every
    // verdict below would be a `fail` for reasons unrelated to rate limiting.
    realCardFound: true,
    mainRegion: { textLength: 4200, skeletonTextLength: 0, visibleSkeletonCount: 0 },
    firstCardMs: 1450,
    ...extra,
  };
}

/** The #1909 shape: the main region rendered blank. */
const BLANK_MAIN_REGION = {
  textLength: 0,
  skeletonTextLength: 0,
  visibleSkeletonCount: 0,
};

function find(journey, id) {
  return journey.assertions.find((a) => a.assertion_id === id);
}

test("a first-party 429 is self-inflicted", () => {
  assert.equal(isSelfInflictedRateLimit(RL()), true);
  assert.equal(isSelfInflictedRateLimit(RL("https://bainluck.com/discover")), true);
});

test("a 429 from a third party is a real finding", () => {
  // Somebody else's budget, which we do not control and must hear about.
  assert.equal(isSelfInflictedRateLimit({ url: "https://api.kalshi.com/x", status: 429 }), false);
  assert.equal(isFirstPartyHost("https://api.kalshi.com/x"), false);
  // And the suffix match must not be fooled by a lookalike domain.
  assert.equal(isFirstPartyHost("https://notbainluck.com/x"), false);
  assert.equal(isFirstPartyHost("https://bainluck.com.evil.test/x"), false);
});

test("a non-429 failure is never self-inflicted, however heavy the load", () => {
  // A 500 under load is a real defect. Load is not an excuse for one.
  for (const status of [400, 404, 500, 502, 503]) {
    assert.equal(isSelfInflictedRateLimit({ url: "https://api.bainluck.com/api/feed", status }), false);
  }
  assert.equal(isSelfInflictedRateLimit({ url: "https://api.bainluck.com/api/feed" }), false);
});

test("network.no_unexpected_failures is INFRA when every failure is a self-inflicted 429", () => {
  const journey = evaluateJourney(
    observation({ failedRequests: [RL(), RL("https://api.bainluck.com/api/calibration"), RL()] })
  );
  const network = find(journey, "network.no_unexpected_failures");
  assert.equal(network.ok, false, "still a non-pass — this classifies, it does not suppress");
  assert.equal(network.infra, true);
  assert.match(network.detail, /self-inflicted 429/);
  assert.equal(journey.result, RESULTS.INFRA_ERROR);
});

test("ONE genuine failure alongside the burst keeps the assertion graded", () => {
  // The conservative direction. A missed product defect is unrecoverable; an
  // extra filed issue is a nuisance.
  const journey = evaluateJourney(
    observation({
      failedRequests: [RL(), RL(), { url: "https://api.bainluck.com/api/events", status: 500 }],
    })
  );
  const network = find(journey, "network.no_unexpected_failures");
  assert.equal(network.ok, false);
  assert.equal(network.infra, undefined, "a 500 in the batch means the whole assertion is real");
  assert.equal(journey.result, RESULTS.FAIL);
});

test("a clean journey is still a PASS, not an infra_error", () => {
  // Non-vacuity: every assertion above is satisfied by a grader that returns
  // infra_error for everything.
  const journey = evaluateJourney(observation());
  assert.equal(journey.result, RESULTS.PASS);
  assert.equal(find(journey, "network.no_unexpected_failures").ok, true);
});

test("the console echo is classified only when a 429 was actually observed", () => {
  const echo = "Failed to fetch RSC payload for https://bainluck.com/discover. TypeError: Failed to fetch";
  assert.equal(isRateLimitEcho(echo), true);

  // Gated: the same console text with NO 429 on the network channel is a real
  // finding — a genuinely broken endpoint logs exactly this.
  assert.equal(consoleErrorsAreRateLimitEcho([echo], []), false);
  const ungated = evaluateJourney(observation({ consoleErrors: [echo] }));
  assert.equal(find(ungated, "console.no_errors").infra, undefined);
  assert.equal(ungated.result, RESULTS.FAIL);

  // With the burst present, it is the echo the census identified.
  const gated = evaluateJourney(observation({ consoleErrors: [echo], failedRequests: [RL()] }));
  assert.equal(find(gated, "console.no_errors").infra, true);
  assert.equal(gated.result, RESULTS.INFRA_ERROR);
});

test("an unrelated console error is never the echo", () => {
  const journey = evaluateJourney(
    observation({
      consoleErrors: ["Uncaught TypeError: Cannot read properties of undefined (reading 'map')"],
      failedRequests: [RL()],
    })
  );
  assert.equal(find(journey, "console.no_errors").infra, undefined);
  assert.equal(journey.result, RESULTS.FAIL);
});

test("infra-classified findings do not become product issues", () => {
  const journey = evaluateJourney(observation({ failedRequests: [RL(), RL()] }));
  const manifest = {
    run: { base_url: "https://bainluck.com" },
    journeys: [{ ...journey, journey_id: "consent.two_tabs", project: "desktop", url: "https://bainluck.com/discover" }],
  };
  const findings = findingsFromManifest(manifest);
  const network = findings.find((f) => f.assertion_id === "network.no_unexpected_failures");
  assert.ok(network, "the finding is still produced — the manifest keeps the whole reading");
  assert.equal(network.infra, true, "but it is infra, so the filer will not mint a product issue");
});

test("THE LOAD-BEARING ONE — #1909 still files through a 12 × 429 burst", () => {
  // `consent.two_tabs [desktop]`, reproduced from the census: a blank main
  // region *and* twelve self-inflicted 429s, on one journey, in one run. Any
  // fix that mutes the journey buries this, which is the whole reason the flag
  // rides on the assertion instead.
  const journey = evaluateJourney(
    observation({
      failedRequests: Array.from({ length: 12 }, () => RL()),
      consoleErrors: ["Failed to fetch RSC payload for /discover. TypeError: Failed to fetch"],
      mainRegion: BLANK_MAIN_REGION,
    })
  );

  const blank = find(journey, "content.main_region_nonblank");
  assert.ok(blank, "the journey must still grade the main region");
  assert.equal(blank.ok, false, "the page WAS blank — that is #1909");
  assert.equal(blank.infra, undefined, "and it is a PRODUCT defect, not runner noise");

  assert.equal(journey.result, RESULTS.FAIL, "one real defect makes the journey a real fail");

  const findings = findingsFromManifest({
    run: { base_url: "https://bainluck.com" },
    journeys: [{ ...journey, journey_id: "consent.two_tabs", project: "desktop", url: "https://bainluck.com/discover" }],
  });

  const productFindings = findings.filter((f) => !f.infra);
  assert.deepEqual(
    productFindings.map((f) => f.assertion_id),
    ["content.main_region_nonblank"],
    "exactly one product issue files: the real bug, with the twelve pieces of noise stripped"
  );
});
