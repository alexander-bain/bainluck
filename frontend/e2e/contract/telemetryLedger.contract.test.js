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

// ---------------------------------------------------------------------------
// #1658 — an assertion may only count the population its ID names
//
// `page_view_exactly_once` matched on HOST and therefore counted every GA4
// `/g/collect` beacon. A fresh grant sends four — `page_view`, GA4's automatic
// `session_start` and `first_visit`, and the app's own `scroll_depth` /
// `time_on_page` (CLAUDE.md mandates all three hooks on every page). So the rail
// filed "4 request(s), expected exactly 1" against a page that had done nothing
// wrong, and #1908's census recorded it as "none of the three mechanisms" and
// left it there. It is the FOURTH mechanism, and it is the #1860 oracle class:
// the instrument was wrong, not the product.
// ---------------------------------------------------------------------------

/** The four beacons a real fresh grant produces, as the recorder now stores them. */
const GRANT_BEACONS = [
  { host: "www.google-analytics.com", path: "/g/collect", event: "page_view", count: 1 },
  { host: "www.google-analytics.com", path: "/g/collect", event: "session_start", count: 1 },
  { host: "www.google-analytics.com", path: "/g/collect", event: "first_visit", count: 1 },
  { host: "www.google-analytics.com", path: "/g/collect", event: "scroll_depth", count: 1 },
];

/** The grant journey's real ledger, as `consent.spec.ts` declares it. */
const GRANT_LEDGER = {
  minWindowMs: 1000,
  rules: [
    { id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 },
    {
      id: "page_view_exactly_once",
      hostSuffix: "google-analytics.com",
      eventName: "page_view",
      expect: "exact",
      count: 1,
    },
    { id: "ga4_other_events_allowed", hostSuffix: "google-analytics.com", expect: "at_least", count: 0 },
  ],
};

test("#1658 — the four beacons of a real grant are ONE page view, and pass", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [GA, ...GRANT_BEACONS],
      telemetryWindowMs: 6000,
      telemetryExpectation: GRANT_LEDGER,
    })
  );
  assert.equal(v.result, "pass", JSON.stringify(v.assertions, null, 2));
  assert.equal(find(v, "telemetry.page_view_exactly_once").ok, true);
});

test("#1658 — the OLD host-only rule reads those same four as four page views", () => {
  // The bug, pinned as a control (ruling 067): reproduce the shipped-broken rule
  // verbatim beside the fix, so the diff between the two IS the behaviour change
  // and a reviewer reads a behaviour instead of auditing a matcher.
  const legacy = {
    minWindowMs: 1000,
    rules: [
      { id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 },
      { id: "page_view_exactly_once", hostSuffix: "google-analytics.com", expect: "exact", count: 1 },
    ],
  };
  const v = evaluateJourney(
    healthy({
      telemetry: [GA, ...GRANT_BEACONS],
      telemetryWindowMs: 6000,
      telemetryExpectation: legacy,
    })
  );
  assert.equal(v.result, "fail");
  assert.equal(
    find(v, "telemetry.page_view_exactly_once").detail,
    "4 request(s), expected exactly 1",
    "this is #1658's filed text, reproduced from the rule that produced it"
  );
});

test("#1658 THE LOAD-BEARING ONE — a genuine double page view still fails", () => {
  // The guard this narrowing must not delete. Every one-liner shaped like "stop
  // failing on GA noise" would have passed the test above AND this one — which
  // is exactly the trap #1908's M1 walked around, and the reason the fix counts
  // the right population instead of loosening the count.
  const v = evaluateJourney(
    healthy({
      telemetry: [
        GA,
        { host: "www.google-analytics.com", path: "/g/collect", event: "page_view", count: 2 },
        { host: "www.google-analytics.com", path: "/g/collect", event: "session_start", count: 1 },
      ],
      telemetryWindowMs: 6000,
      telemetryExpectation: GRANT_LEDGER,
    })
  );
  assert.equal(v.result, "fail", "the gtag('config') double-count must still be caught");
  assert.equal(find(v, "telemetry.page_view_exactly_once").detail, "2 request(s), expected exactly 1");
});

test("#1658 — a grant that sends NO page view fails, so the rule is not vacuous", () => {
  const v = evaluateJourney(
    healthy({
      telemetry: [GA, { host: "www.google-analytics.com", path: "/g/collect", event: "session_start", count: 1 }],
      telemetryWindowMs: 6000,
      telemetryExpectation: GRANT_LEDGER,
    })
  );
  assert.equal(v.result, "fail");
  assert.equal(find(v, "telemetry.page_view_exactly_once").detail, "0 request(s), expected exactly 1");
});

test("#1658 — an event-scoped rule never matches an eventless observation", () => {
  // Narrowing a rule must not silently widen it. A gtag.js script load and a
  // Vercel beacon carry no `en`, and must not satisfy an event-scoped rule just
  // because the host happens to line up.
  assert.equal(
    telemetryRuleMatches(
      { hostSuffix: "google-analytics.com", eventName: "page_view" },
      { host: "www.google-analytics.com", path: "/g/collect", count: 1 }
    ),
    false
  );
  assert.equal(
    telemetryRuleMatches(
      { hostSuffix: "google-analytics.com", eventName: "page_view" },
      { host: "www.google-analytics.com", path: "/g/collect", event: "other", count: 1 }
    ),
    false
  );
  assert.equal(
    telemetryRuleMatches(
      { hostSuffix: "google-analytics.com", eventName: "page_view" },
      { host: "www.google-analytics.com", path: "/g/collect", event: "page_view", count: 1 }
    ),
    true
  );
});

test("#1658 — an UNKNOWN GA4 event is still counted, as `other`, never dropped", () => {
  // The privacy allowlist collapses an unrecognised `en` to `other`. That must
  // keep it VISIBLE to the exhaustiveness check rather than vanishing it — a
  // beacon the ledger cannot see is the one shape a consent pack must never
  // permit (gotcha #53: absent and unreported are different facts).
  const v = evaluateJourney(
    healthy({
      telemetry: [
        GA,
        { host: "www.google-analytics.com", path: "/g/collect", event: "page_view", count: 1 },
        { host: "www.google-analytics.com", path: "/g/collect", event: "other", count: 1 },
      ],
      telemetryWindowMs: 6000,
      telemetryExpectation: {
        minWindowMs: 1000,
        rules: [
          { id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 },
          {
            id: "page_view_exactly_once",
            hostSuffix: "google-analytics.com",
            eventName: "page_view",
            expect: "exact",
            count: 1,
          },
        ],
      },
    })
  );
  // No host-wide companion rule here, so the `other` beacon is unlisted — and
  // that is the designed outcome: it surfaces as a named failure instead of
  // quietly inflating the page-view count the way it used to.
  assert.equal(v.result, "fail");
  assert.equal(find(v, "telemetry.no_unlisted_destinations").ok, false);
});

test("#1658 — a DECLINE still denies every GA4 event, whatever it is named", () => {
  // The narrowing must not open a hole in the pack's central negative. `absent`
  // rules stay host-scoped, so an event name cannot be used to smuggle a beacon
  // past a Decline.
  const v = evaluateJourney(
    healthy({
      telemetry: [{ host: "www.google-analytics.com", path: "/g/collect", event: "scroll_depth", count: 1 }],
      telemetryWindowMs: 6000,
      telemetryExpectation: DENY_EVERYTHING,
    })
  );
  assert.equal(v.result, "fail");
  assert.equal(find(v, "telemetry.google_analytics").ok, false);
});
