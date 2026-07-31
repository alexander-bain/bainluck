"use strict";

/**
 * L2-222 Item 3 (#1453) — the consent pack's network ledger, proven without a
 * browser.
 *
 * The pack's central claim is a NEGATIVE: after a Decline, zero analytics
 * requests leave the page. A negative is the easiest thing in this whole rail
 * to fake — a run that never gave the page time to send anything observes zero
 * and reports success — so the ledger refuses to believe an absence without a
 * declared, non-trivial observation window, and it treats any destination no
 * rule mentions as a failure.
 *
 * These fixtures drive `evaluateJourney` directly: the SAME function the live
 * specs call. A shape proven to fail here cannot pass in production.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const { evaluateJourney, telemetryRuleMatches } = require("../helpers/journey");

/** A journey that is otherwise entirely healthy, so only the ledger decides. */
function healthy(overrides) {
  return {
    infra: null,
    shaMatch: true,
    shaDetail: "exact match",
    expectedPath: "/",
    urlPath: "/",
    realCardFound: true,
    firstCardMs: 900,
    mainRegionNonBlank: true,
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    artifacts: [{ name: "shot.png", sha256: "a".repeat(64), bytes: 10 }],
    ...overrides,
  };
}

const GA = { host: "www.googletagmanager.com", path: "/gtag/js", count: 1 };
const GA_COLLECT = { host: "www.google-analytics.com", path: "/g/collect", count: 1 };
const VERCEL = { host: "www.bainluck.com", path: "/_vercel/insights/view", count: 1 };

const DENY_EVERYTHING = {
  minWindowMs: 1000,
  rules: [
    { id: "google_tag_manager", hostSuffix: "googletagmanager.com", expect: "absent" },
    { id: "google_analytics", hostSuffix: "google-analytics.com", expect: "absent" },
    { id: "vercel_insights", pathPrefix: "/_vercel/insights", expect: "absent" },
    { id: "vercel_speed", pathPrefix: "/_vercel/speed-insights", expect: "absent" },
  ],
};

const find = (v, id) => v.assertions.find((a) => a.assertion_id === id);

// ---------------------------------------------------------------------------
// Absence must be earned
// ---------------------------------------------------------------------------

test("a clean Decline with a real window passes", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [],
      telemetryWindowMs: 6000,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "pass");
  assert.equal(find(v, "telemetry.observation_window").ok, true);
  assert.equal(find(v, "telemetry.google_analytics").ok, true);
});

test("zero requests with NO observation window is a FAIL, not a pass", () => {
  // The exact false green this guard exists for.
  const v = evaluateJourney(
    healthy({
      telemetry: [],
      telemetryWindowMs: null,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  const a = find(v, "telemetry.observation_window");
  assert.equal(a.ok, false);
  assert.match(a.detail, /absence cannot be proven/);
});

test("zero requests inside a trivially short window is a FAIL", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [],
      telemetryWindowMs: 12,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  assert.match(find(v, "telemetry.observation_window").detail, /below the 1000ms floor/);
});

test("a single GA request after a Decline fails the journey", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [GA],
      telemetryWindowMs: 6000,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  assert.equal(find(v, "telemetry.google_tag_manager").ok, false);
});

test("a Vercel insights beacon after a Decline fails the journey", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [VERCEL],
      telemetryWindowMs: 6000,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  assert.equal(find(v, "telemetry.vercel_insights").ok, false);
});

// ---------------------------------------------------------------------------
// Presence and count
// ---------------------------------------------------------------------------

test("exactly-one page view passes at 1 and fails at 2", () => {
  const expectation = {
    minWindowMs: 1000,
    rules: [
      { id: "ga_collect_once", hostSuffix: "google-analytics.com", expect: "exact", count: 1 },
      { id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 },
      { id: "vercel_insights", pathPrefix: "/_vercel/insights", expect: "at_least", count: 0 },
      { id: "vercel_speed", pathPrefix: "/_vercel/speed-insights", expect: "at_least", count: 0 },
    ],
  };

  const one = evaluateJourney(
    healthy({ telemetry: [GA, GA_COLLECT], telemetryWindowMs: 6000, telemetryExpectation: expectation })
  );
  assert.equal(one.result, "pass");

  // The double-count regression (C90 P3's inverse) must be visible.
  const two = evaluateJourney(
    healthy({
      telemetry: [GA, { ...GA_COLLECT, count: 2 }],
      telemetryWindowMs: 6000,
      telemetryExpectation: expectation,
    })
  );
  assert.equal(two.result, "fail");
  assert.match(find(two, "telemetry.ga_collect_once").detail, /2 request\(s\), expected exactly 1/);
});

test("a missing expected request fails — presence is proven too", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [],
      telemetryWindowMs: 6000,
      telemetryExpectation: {
        rules: [{ id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 }],
      },
    })
  );
  assert.equal(v.result, "fail");
});

// ---------------------------------------------------------------------------
// Exhaustiveness: a NEW provider must not slip past the existing rules
// ---------------------------------------------------------------------------

test("an unlisted destination fails even when every rule is satisfied", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [{ host: "cdn.some-new-analytics.io", path: "/beacon", count: 3 }],
      telemetryWindowMs: 6000,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  const a = find(v, "telemetry.no_unlisted_destinations");
  assert.equal(a.ok, false);
  assert.match(a.detail, /cdn\.some-new-analytics\.io/);
});

test("unlisted destinations can be allowed, but only explicitly", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [{ host: "cdn.some-new-analytics.io", path: "/beacon", count: 1 }],
      telemetryWindowMs: 6000,
      telemetryExpectation: { ...DENY_EVERYTHING, allowUnlisted: true },
    })
  );
  assert.equal(v.result, "pass");
  assert.ok(
    v.checked_clean.some((c) => c.startsWith("telemetry.no_unlisted_destinations")),
    "the waiver must be recorded, not silent"
  );
});

test("a journey with no expectation records the ledger as not evaluated", () => {
  const v = evaluateJourney(healthy({}));
  assert.equal(v.result, "pass");
  assert.ok(v.checked_clean.some((c) => c.startsWith("telemetry.ledger")));
});

test("an unknown expectation keyword fails closed", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [],
      telemetryWindowMs: 6000,
      telemetryExpectation: { rules: [{ id: "typo", hostSuffix: "x.com", expect: "maybe" }] },
    })
  );
  assert.equal(v.result, "fail");
});

// ---------------------------------------------------------------------------
// Matching
// ---------------------------------------------------------------------------

test("hostSuffix matches the host and its subdomains, not a lookalike", () => {
  const rule = { id: "ga", hostSuffix: "google-analytics.com", expect: "absent" };
  assert.equal(telemetryRuleMatches(rule, { host: "google-analytics.com", path: "/" }), true);
  assert.equal(telemetryRuleMatches(rule, { host: "www.google-analytics.com", path: "/" }), true);
  assert.equal(
    telemetryRuleMatches(rule, { host: "notgoogle-analytics.com", path: "/" }),
    false,
    "a suffix match must respect the dot boundary"
  );
});

test("a rule with neither host nor path matches nothing", () => {
  // A typo must not silently become a wildcard that swallows every request.
  assert.equal(telemetryRuleMatches({ id: "oops", expect: "absent" }, GA), false);
});

// ---------------------------------------------------------------------------
// contentMode
// ---------------------------------------------------------------------------

test('contentMode "none" waives the card check but NOT the blank-page check', () => {
  const waived = evaluateJourney(
    healthy({ contentMode: "none", realCardFound: false, firstCardMs: null })
  );
  assert.equal(waived.result, "pass");
  assert.ok(
    waived.checked_clean.some((c) => c.startsWith("content.real_card_or_named_empty"))
  );

  const blank = evaluateJourney(
    healthy({
      contentMode: "none",
      realCardFound: false,
      firstCardMs: null,
      mainRegionNonBlank: false,
    })
  );
  assert.equal(blank.result, "fail", "an opted-out journey on a blank page still fails");
});

test('contentMode defaults to "card" — a feed journey cannot quietly opt out', () => {
  const v = evaluateJourney(healthy({ realCardFound: false, firstCardMs: null }));
  assert.equal(v.result, "fail");
  assert.equal(find(v, "content.real_card_or_named_empty").ok, false);
});
