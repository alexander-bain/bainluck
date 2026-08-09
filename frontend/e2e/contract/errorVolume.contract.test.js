"use strict";

/**
 * UX-P029 Item 3 — the console/request error VOLUME policy.
 *
 * The queue names the cases this corpus must contain, and they are all here:
 * #1600's ~2,050 failed requests / 2,175 console errors, one benign isolated
 * third-party error, repeated identical failures, mixed origins, navigation
 * cancellation, and a control page.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ERROR_VOLUME_POLICY_VERSION,
  CONSOLE_ERROR_VOLUME_THRESHOLD,
  REQUEST_FAILURE_VOLUME_THRESHOLD,
  REASON_CONSOLE_VOLUME,
  REASON_REQUEST_VOLUME,
  classifyErrorVolume,
  isNavigationCancellation,
} = require("../helpers/errorVolume");
const { evaluateJourney } = require("../helpers/journey");

const repeat = (n, make) => Array.from({ length: n }, (_, i) => make(i));

/** #1600, as measured by browser-audit run 30864618239 on 2026-08-04. */
const ISSUE_1600 = {
  consoleErrors: repeat(2175, () => "Failed to load resource: the server responded with 429"),
  failedRequests: repeat(2036, (i) => ({
    url: `https://en.wikipedia.org/api/rest_v1/page/summary/Player_${i % 41}`,
    status: 429,
  })),
};

// --------------------------------------------------------------- the case ---

test("#1600's real volumes breach BOTH channels with stable reason codes", () => {
  const v = classifyErrorVolume(ISSUE_1600);

  assert.equal(v.console.total, 2175);
  assert.equal(v.requests.total, 2036);
  assert.equal(v.console.exceeded, true);
  assert.equal(v.requests.exceeded, true);
  assert.equal(v.console.reason_code, REASON_CONSOLE_VOLUME);
  assert.equal(v.requests.reason_code, REASON_REQUEST_VOLUME);
});

test("the reason code carries NO counts — a fingerprint must be stable run to run", () => {
  const a = classifyErrorVolume(ISSUE_1600).requests.reason_code;
  const b = classifyErrorVolume({
    failedRequests: repeat(1500, (i) => ({ url: `https://en.wikipedia.org/x/${i}`, status: 429 })),
  }).requests.reason_code;
  assert.equal(a, b, "two runs of the same defect must fingerprint identically");
  assert.doesNotMatch(a, /\d/, "a reason code with a number in it is not stable");
});

test("a fan-out is distinguishable from a broadly broken page", () => {
  // 41 distinct entities hit ~50 times each — one bug, repeated.
  const fanOut = classifyErrorVolume(ISSUE_1600);
  assert.equal(fanOut.requests.distinct, 41);
  assert.ok(fanOut.requests.total > fanOut.requests.distinct * 10);

  // 200 different broken URLs — a different defect with the same volume.
  const broadlyBroken = classifyErrorVolume({
    failedRequests: repeat(200, (i) => ({ url: `https://api.bainluck.com/x/${i}`, status: 500 })),
  });
  assert.equal(broadlyBroken.requests.distinct, 200);
});

// --------------------------------------------------- benign / control ---

test("ONE benign isolated third-party error is retained as evidence, not a volume breach", () => {
  const v = classifyErrorVolume({
    consoleErrors: ["Failed to load resource: net::ERR_BLOCKED_BY_CLIENT (analytics)"],
    failedRequests: [{ url: "https://plausible.io/api/event", status: 0 }],
  });

  assert.equal(v.console.exceeded, false);
  assert.equal(v.requests.exceeded, false);
  assert.equal(v.console.reason_code, null);
  // Retained: the counts are still reported. Evidence, not silence.
  assert.equal(v.console.total, 1);
  assert.equal(v.requests.total, 1);
  assert.deepEqual(v.requests.by_origin, [{ origin: "https://plausible.io", count: 1 }]);
});

test("a control page — no errors at all — breaches nothing and reports zeroes", () => {
  const v = classifyErrorVolume({ consoleErrors: [], failedRequests: [] });
  assert.equal(v.console.total, 0);
  assert.equal(v.requests.total, 0);
  assert.equal(v.console.exceeded, false);
  assert.equal(v.requests.exceeded, false);
  assert.deepEqual(v.requests.by_origin, []);
});

test("the threshold boundary is exact: at the threshold passes, one over fails", () => {
  const at = classifyErrorVolume({
    failedRequests: repeat(REQUEST_FAILURE_VOLUME_THRESHOLD, (i) => ({ url: `https://x.test/${i}` })),
  });
  const over = classifyErrorVolume({
    failedRequests: repeat(REQUEST_FAILURE_VOLUME_THRESHOLD + 1, (i) => ({ url: `https://x.test/${i}` })),
  });
  assert.equal(at.requests.exceeded, false);
  assert.equal(over.requests.exceeded, true);
});

// ------------------------------------------------------- repeats / origins ---

test("repeated IDENTICAL failures still count toward volume", () => {
  // The defect is the repetition. Deduplicating here would hide exactly the
  // failure mode #1600 is: the same call, over and over.
  const v = classifyErrorVolume({
    failedRequests: repeat(120, () => ({ url: "https://en.wikipedia.org/api/x", status: 429 })),
  });
  assert.equal(v.requests.total, 120);
  assert.equal(v.requests.distinct, 1);
  assert.equal(v.requests.exceeded, true);
});

test("mixed origins are counted together and reported per origin, biggest first", () => {
  const v = classifyErrorVolume({
    failedRequests: [
      ...repeat(60, (i) => ({ url: `https://en.wikipedia.org/api/${i}` })),
      ...repeat(5, (i) => ({ url: `https://api.bainluck.com/api/${i}` })),
      { url: "not-a-url" },
    ],
  });
  assert.equal(v.requests.total, 66);
  assert.equal(v.requests.exceeded, true);
  assert.deepEqual(v.requests.by_origin, [
    { origin: "https://en.wikipedia.org", count: 60 },
    { origin: "https://api.bainluck.com", count: 5 },
    { origin: "unknown", count: 1 },
  ]);
});

test("a third-party origin never exempts an error — same volume, same verdict", () => {
  const thirdParty = classifyErrorVolume({
    failedRequests: repeat(80, (i) => ({ url: `https://en.wikipedia.org/api/${i}` })),
  });
  const firstParty = classifyErrorVolume({
    failedRequests: repeat(80, (i) => ({ url: `https://api.bainluck.com/api/${i}` })),
  });
  assert.equal(thirdParty.requests.exceeded, firstParty.requests.exceeded);
  assert.equal(thirdParty.requests.reason_code, firstParty.requests.reason_code);
});

// ------------------------------------------------- navigation cancellation ---

test("navigation cancellation is excluded from the count but stays visible", () => {
  const v = classifyErrorVolume({
    failedRequests: [
      ...repeat(200, () => ({ url: "https://www.bainluck.com/x", failure: "net::ERR_ABORTED" })),
      { url: "https://api.bainluck.com/api/feed", status: 500 },
    ],
  });
  assert.equal(v.requests.total, 1, "aborted-by-navigation requests are not product defects");
  assert.equal(v.requests.exceeded, false);
  assert.equal(v.requests.navigation_cancelled_excluded, 200, "the exclusion is reported, never silent");
});

test("cancellation matching is narrow — it must not swallow a real failure", () => {
  assert.equal(isNavigationCancellation({ failure: "net::ERR_ABORTED" }), true);
  assert.equal(isNavigationCancellation({ failure: "NET::ERR_ABORTED" }), true);
  assert.equal(isNavigationCancellation({ navigationCancelled: true }), true);
  assert.equal(isNavigationCancellation({ failure: "net::ERR_CONNECTION_REFUSED" }), false);
  assert.equal(isNavigationCancellation({ failure: "aborted the transaction" }), false);
  assert.equal(isNavigationCancellation({ status: 500 }), false);
  assert.equal(isNavigationCancellation(null), false);
});

// ------------------------------------------------------------- unwaivable ---

test("a volume breach CANNOT be waived by an allowance — the load-bearing rule", () => {
  // Declaring the origin silences the per-error assertion...
  const evaluated = evaluateJourney({
    journeyId: "volume.unwaivable",
    project: "desktop",
    startedAt: "2026-08-09T00:00:00.000Z",
    finishedAt: "2026-08-09T00:00:10.000Z",
    contentMode: "none",
    failedRequests: ISSUE_1600.failedRequests,
    allowedFailures: ISSUE_1600.failedRequests.map((f) => f.url),
    consoleErrors: ISSUE_1600.consoleErrors,
    allowedConsoleErrors: ["Failed to load resource"],
  });

  const byId = new Map(evaluated.assertions.map((a) => [a.assertion_id, a]));
  assert.equal(byId.get("network.no_unexpected_failures").ok, true, "allowance silences the per-error check");
  assert.equal(byId.get("console.no_errors").ok, true, "allowance silences the per-error check");

  // ...but the journey still FAILS on volume, with the stable reason codes.
  assert.equal(byId.get("network.failure_volume_within_policy").ok, false);
  assert.equal(byId.get("network.failure_volume_within_policy").reason_code, REASON_REQUEST_VOLUME);
  assert.equal(byId.get("console.error_volume_within_policy").ok, false);
  assert.equal(byId.get("console.error_volume_within_policy").reason_code, REASON_CONSOLE_VOLUME);
  assert.equal(evaluated.result, "fail");
});

test("a clean journey records volume as checked-clean, not as another green assertion", () => {
  const evaluated = evaluateJourney({
    journeyId: "volume.control",
    project: "desktop",
    startedAt: "2026-08-09T00:00:00.000Z",
    finishedAt: "2026-08-09T00:00:01.000Z",
    contentMode: "none",
    failedRequests: [],
    consoleErrors: [],
  });

  const ids = evaluated.assertions.map((a) => a.assertion_id);
  assert.ok(!ids.includes("network.failure_volume_within_policy"));
  assert.ok(
    evaluated.checked_clean.some((c) => c.startsWith("network.failure_volume_within_policy")),
    "under threshold the numbers are retained as evidence"
  );
});

test("the policy is versioned so a threshold change cannot silently re-grade history", () => {
  assert.equal(classifyErrorVolume({}).policy_version, ERROR_VOLUME_POLICY_VERSION);
  assert.match(ERROR_VOLUME_POLICY_VERSION, /\/v\d+$/);
  // Both thresholds must sit strictly between the benign case and #1600.
  for (const t of [CONSOLE_ERROR_VOLUME_THRESHOLD, REQUEST_FAILURE_VOLUME_THRESHOLD]) {
    assert.ok(t > 10, "must not fire on a handful of benign errors");
    assert.ok(t < 2000, "must catch #1600");
  }
});
