"use strict";

/**
 * #1908 M2 — the instrument-induced carve-out (ruling 021 clause 3, amended
 * 2026-08-18).
 *
 * THE DEADLOCK THESE TESTS ARE THE RESOLUTION OF. The consent pack's METHOD is
 * to navigate mid-load; cancelled in-flight requests are its exhaust. The
 * rail's RULE is that a cancelled `/api/feed` stays graded, because that abort
 * is invisible to the backend's own metrics (#1525 Shape A). #1667 is a
 * first-party aborted `/api/feed` in a journey whose own navigation aborted it,
 * so under clause 3 as written it is a permanent red no product change can
 * clear — and under a naive loosening, the one abort class worth watching stops
 * being watched.
 *
 * The amendment moves the guard off the PROXY and onto the OUTCOME: the abort
 * is excusable when the instrument caused it, and the AFTERMATH — did the main
 * region reach a rendered, non-blank state once the harness's own navigation
 * settled — is graded, always.
 *
 * That trade is only safe if all four conditions are ENFORCED rather than
 * documented, so every one of them has a test here, in both directions:
 *
 *   1. attributable   — no `instrument_action`, no excuse
 *   2. declared       — no declaration, no excuse
 *   3. graded aftermath — no measured main region, no excuse (fail-CLOSED)
 *   4. one decision   — both graders reach the same verdict on one input
 *
 * Plus the non-vacuity guard: a journey that declares the carve-out and grades
 * no aftermath must FAIL, because an excused abort with nothing graded in its
 * place is a deletion wearing a carve-out's clothes.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  INSTRUMENT_NAVIGATION_ABORT,
  RSC_PREFETCH_ABORT,
  abortAllowanceMatches,
  aftermathIsGraded,
  allowanceIsInstrumentInduced,
  firedAllowances,
  instrumentAllowancesMissingAftermath,
  isInstrumentInduced,
} = require("../helpers/navigationAborts");
const { classifyErrorVolume } = require("../helpers/errorVolume");
const { describeAbort } = require("../helpers/abortRecord");
const { evaluateJourney } = require("../helpers/journey");

const GRADED = { aftermathGraded: true };
/** Real `measureMainRegion` output shape: counts, not text. */
const RENDERED_REGION = Object.freeze({
  textLength: 4000,
  skeletonTextLength: 0,
  visibleSkeletonCount: 0,
});
const BLANK_REGION = Object.freeze({
  textLength: 0,
  skeletonTextLength: 0,
  visibleSkeletonCount: 0,
});
const UNGRADED = { aftermathGraded: false };

/** A first-party aborted `/api/feed` — Shape A, the whole subject. */
function feedAbort({ instrumentAction = null } = {}) {
  return {
    url: "https://api.bainluck.com/api/feed",
    method: "GET",
    status: null,
    failure: "net::ERR_ABORTED",
    abort: describeAbort({
      failureText: "net::ERR_ABORTED",
      resourceType: "fetch",
      timing: { requestStart: 3 },
      frameUrl: "https://www.bainluck.com/",
      isFeed: true,
      instrumentAction,
    }),
  };
}

test("the abort packet carries the harness action that caused it", () => {
  const stamped = feedAbort({ instrumentAction: "goto /preferences#telemetry" }).abort;
  assert.equal(stamped.instrument_action, "goto /preferences#telemetry");
  assert.equal(stamped.is_feed_request, true);

  const organic = feedAbort().abort;
  assert.equal(organic.instrument_action, null, "no action in flight, no attribution");
});

test("condition 1 — an UNATTRIBUTED feed abort is never excused", () => {
  // This is the pre-amendment behaviour, and it must survive intact: an abort
  // that fired while the harness was doing nothing is organic, whatever journey
  // it happened in.
  const f = feedAbort();
  assert.equal(isInstrumentInduced(f), false);
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, GRADED), false);
});

test("condition 2 — an attributed feed abort is not excused without a declaration", () => {
  const f = feedAbort({ instrumentAction: "goto /" });
  // The RSC prefetch allowance is NOT the carve-out and may not act as one.
  assert.equal(abortAllowanceMatches(f, RSC_PREFETCH_ABORT, GRADED), false);
  assert.equal(allowanceIsInstrumentInduced(RSC_PREFETCH_ABORT), false);
  assert.equal(allowanceIsInstrumentInduced(INSTRUMENT_NAVIGATION_ABORT), true);
});

test("condition 3 — the excuse FAILS CLOSED when the aftermath is not graded", () => {
  const f = feedAbort({ instrumentAction: "goto /" });
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, UNGRADED), false);
  // And, the case that actually happens: a grader that forgets to pass context
  // at all. Absent must mean refused, or the carve-out silently becomes global.
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT), false);
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, null), false);
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, {}), false);
  assert.equal(aftermathIsGraded({ aftermathGraded: "yes" }), false, "truthy is not true");
});

test("all four conditions together — the excuse applies, and only then", () => {
  const f = feedAbort({ instrumentAction: "two-tab revoke → tab A reloads" });
  assert.equal(abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, GRADED), true);
  assert.deepEqual(
    firedAllowances([f], [INSTRUMENT_NAVIGATION_ABORT], GRADED),
    [INSTRUMENT_NAVIGATION_ABORT]
  );
  assert.deepEqual(firedAllowances([f], [INSTRUMENT_NAVIGATION_ABORT], UNGRADED), []);
});

test("a NON-abort is untouched by the carve-out", () => {
  // A 500 on /api/feed during a harness navigation is a product defect, and no
  // amount of attribution makes it exhaust.
  const five00 = {
    url: "https://api.bainluck.com/api/feed",
    status: 500,
    failure: null,
    abort: undefined,
    instrumentAction: "goto /",
  };
  assert.equal(abortAllowanceMatches(five00, INSTRUMENT_NAVIGATION_ABORT, GRADED), false);
});

test("condition 4 — BOTH graders reach the same verdict on one input", () => {
  // The 0-vs-1 disagreement is the defect `navigationAborts` was extracted to
  // end. Applying the carve-out in the per-error grader alone would recreate it
  // exactly, so the volume grader is driven with the same input here.
  const f = feedAbort({ instrumentAction: "goto /" });

  const excusedByPerError = abortAllowanceMatches(f, INSTRUMENT_NAVIGATION_ABORT, GRADED);
  const volumeGraded = classifyErrorVolume({ failedRequests: [f] }, GRADED);
  assert.equal(excusedByPerError, true);
  assert.equal(
    volumeGraded.requests.total,
    0,
    "the volume grader must exclude what the per-error grader excused"
  );
  assert.equal(volumeGraded.requests.navigation_cancelled_excluded, 1);

  const volumeUngraded = classifyErrorVolume({ failedRequests: [f] }, UNGRADED);
  assert.equal(
    volumeUngraded.requests.total,
    1,
    "and must COUNT it when the aftermath was not graded — same rule, both graders"
  );

  const volumeNoContext = classifyErrorVolume({ failedRequests: [f] });
  assert.equal(volumeNoContext.requests.total, 1, "absent context refuses here too");
});

// ---------------------------------------------------------------------------
// End to end through the real evaluator
// ---------------------------------------------------------------------------

function baseObservation(extra) {
  return {
    journeyId: "consent.two_tabs",
    result: "pass",
    expectedPath: "/",
    observedPath: "/",
    realCardFound: false,
    contentMode: "none",
    failedRequests: [],
    consoleErrors: [],
    ...extra,
  };
}

function assertionsOf(observation) {
  const out = evaluateJourney(observation);
  const list = (out && (out.assertions || out.record?.assertions)) || [];
  const byId = new Map();
  for (const a of list) byId.set(a.assertion_id, a);
  return byId;
}

test("the journey grader excuses an instrument abort ONLY beside a measured region", () => {
  const abortRecord = feedAbort({ instrumentAction: "two-tab revoke → tab A reloads" });

  // WITH measurements: the aftermath exists, so the abort is excused and the
  // aftermath is the thing that decides.
  const withRegion = assertionsOf(
    baseObservation({
      failedRequests: [abortRecord],
      allowedNavigationAborts: [INSTRUMENT_NAVIGATION_ABORT],
      mainRegion: RENDERED_REGION,
    })
  );
  assert.equal(
    withRegion.get("network.no_unexpected_failures").ok,
    true,
    "an attributed abort beside a graded aftermath is excused"
  );
  assert.ok(withRegion.has("content.main_region_nonblank"), "the aftermath IS graded");

  // WITHOUT: the pre-computed boolean cannot tell loading from blank, so it is
  // not an aftermath and the abort stays graded.
  const withBoolean = assertionsOf(
    baseObservation({
      failedRequests: [abortRecord],
      allowedNavigationAborts: [INSTRUMENT_NAVIGATION_ABORT],
      mainRegionNonBlank: true,
    })
  );
  assert.equal(
    withBoolean.get("network.no_unexpected_failures").ok,
    false,
    "a boolean is not an aftermath — the abort must stay graded"
  );
});

test("NON-VACUITY — declaring the carve-out without an aftermath is a FAILURE", () => {
  const withBoolean = assertionsOf(
    baseObservation({
      failedRequests: [],
      allowedNavigationAborts: [INSTRUMENT_NAVIGATION_ABORT],
      mainRegionNonBlank: true,
    })
  );
  const guard = withBoolean.get("network.instrument_allowance_has_aftermath");
  assert.ok(guard, "the guard must be emitted whenever the carve-out is declared");
  assert.equal(guard.ok, false);

  const withRegion = assertionsOf(
    baseObservation({
      allowedNavigationAborts: [INSTRUMENT_NAVIGATION_ABORT],
      mainRegion: RENDERED_REGION,
    })
  );
  assert.equal(withRegion.get("network.instrument_allowance_has_aftermath").ok, true);

  // And it must NOT appear on a journey that never declared the carve-out —
  // an assertion every journey carries is one nobody reads.
  const undeclared = assertionsOf(
    baseObservation({
      allowedNavigationAborts: [RSC_PREFETCH_ABORT],
      mainRegion: RENDERED_REGION,
    })
  );
  assert.equal(undeclared.has("network.instrument_allowance_has_aftermath"), false);
});

test("the aftermath itself is never excused — a blank region still fails", () => {
  // The point of the whole amendment: the excuse buys the abort, never the
  // outcome. A harness-caused abort that leaves the page blank is #1909, and it
  // must still be a finding.
  const graded = assertionsOf(
    baseObservation({
      failedRequests: [feedAbort({ instrumentAction: "goto /" })],
      allowedNavigationAborts: [INSTRUMENT_NAVIGATION_ABORT],
      mainRegion: BLANK_REGION,
    })
  );
  assert.equal(graded.get("network.no_unexpected_failures").ok, true, "abort excused");
  assert.equal(
    graded.get("content.main_region_nonblank").ok,
    false,
    "and the blank region it caused is STILL a failure — that is the trade"
  );
});

test("instrumentAllowancesMissingAftermath names the offenders", () => {
  assert.deepEqual(
    instrumentAllowancesMissingAftermath(
      [RSC_PREFETCH_ABORT, INSTRUMENT_NAVIGATION_ABORT],
      UNGRADED
    ),
    [INSTRUMENT_NAVIGATION_ABORT]
  );
  assert.deepEqual(
    instrumentAllowancesMissingAftermath([RSC_PREFETCH_ABORT], UNGRADED),
    []
  );
  assert.deepEqual(
    instrumentAllowancesMissingAftermath([INSTRUMENT_NAVIGATION_ABORT], GRADED),
    []
  );
});

// ---------------------------------------------------------------------------
// The OTHER attribution decision on the same ledger: whose origin is it?
// ---------------------------------------------------------------------------

test("a THIRD-PARTY failure is not our defect — and the exclusion is visible", () => {
  // Measured on run 32177161167: `consent.grant` went red on two
  // `google-analytics.com/g/collect` beacons cancelled at teardown. The
  // collector's `response` channel has always recorded a 4xx/5xx only when it is
  // first-party; its `requestfailed` channel recorded everything. One ledger,
  // two policies — a third-party 500 ignored, a third-party abort failing the
  // journey.
  const thirdPartyAbort = {
    url: "https://www.google-analytics.com/g/collect?v=2",
    status: null,
    failure: "net::ERR_ABORTED",
    third_party: true,
  };
  const out = evaluateJourney(
    baseObservation({ failedRequests: [thirdPartyAbort], mainRegion: RENDERED_REGION })
  );
  const byId = new Map((out.assertions || []).map((a) => [a.assertion_id, a]));
  assert.equal(byId.get("network.no_unexpected_failures").ok, true);

  // Excluded, never dropped (gotcha #53): an exclusion nobody can see reads as
  // an absence.
  const note = (out.checked_clean || []).find((c) =>
    String(c).startsWith("network.third_party_failures_not_graded")
  );
  assert.ok(note, "the exclusion must be recorded in checked_clean");
  assert.match(note, /google-analytics\.com/, "and must name the origin it excluded");
});

test("the SAME failure unflagged is still graded — the flag is doing the work", () => {
  const unflagged = {
    url: "https://api.bainluck.com/api/predictions/resolutions",
    status: null,
    failure: "net::ERR_ABORTED",
  };
  const byId = new Map(
    (evaluateJourney(
      baseObservation({ failedRequests: [unflagged], mainRegion: RENDERED_REGION })
    ).assertions || []).map((a) => [a.assertion_id, a])
  );
  assert.equal(
    byId.get("network.no_unexpected_failures").ok,
    false,
    "a first-party abort with no declared allowance still fails"
  );
});

test("the VOLUME grader keeps counting third-party — #1600 was a third-party fan-out", () => {
  // Deliberate asymmetry, asserted so nobody "fixes" it into consistency. The
  // per-error grader asks "is this one failure a defect"; the volume grader asks
  // "is this page fanning out". #1600 was ~2,000 Wikipedia requests, so a
  // third-party blind spot there deletes a real find.
  const fanout = Array.from({ length: 40 }, (_, i) => ({
    url: `https://en.wikipedia.org/wiki/page_${i}`,
    status: 404,
    failure: null,
    third_party: true,
  }));
  const volume = classifyErrorVolume({ failedRequests: fanout }, GRADED);
  assert.equal(volume.requests.total, 40, "third-party volume must still be counted");
});

test("the collector stamps third_party on the SAME authority the response channel uses", () => {
  // Source-asserted: the collector is TypeScript and needs a browser. The
  // property worth blocking is that one origin authority serves both channels —
  // the asymmetry above is what happens when it does not.
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(
    path.join(__dirname, "..", "fixtures", "audit.ts"),
    "utf8"
  );
  assert.match(
    src,
    /if \(!this\.isFirstParty\(url\)\) record\.third_party = true;/,
    "the requestfailed channel must stamp third-party from isFirstParty"
  );
  // Count CODE, not prose. The comment above the stamp quotes the response
  // channel's own line on purpose, and a guard that cannot tell an explanation
  // from an implementation grades the wrong text (ruling 084's own species —
  // the same trap the #1948 source guard hit an hour earlier).
  const codeLines = src
    .split("\n")
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line));
  const uses = codeLines.filter((line) => line.includes("this.isFirstParty(url)"));
  assert.equal(
    uses.length,
    2,
    `both channels must consult the SAME origin authority, and only that one (found ${uses.length})`
  );
});
