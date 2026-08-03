"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { classifyMainRegion, CONTENT_STATES, MIN_CONTENT_CHARS } = require("../helpers/contentState");
const { evaluateJourney } = require("../helpers/journey");

/**
 * L2-239 Item 0 — the double-skeleton false red, and the false GREENS that
 * fixing it must not open.
 *
 * The rail's `content.main_region_nonblank` was `text.length > 40 &&
 * !skeletonVisible`. On `/discover` that was permanently false: the route
 * segment's `loading.tsx` puts a second `discover-skeleton` marker in the
 * document, `.first().isVisible()` answered for it, and two consecutive runs
 * (30830689689, 30830999441) reported RED at both viewports while their
 * terminal screenshots showed a fully populated feed. `/` — the same component
 * through a bare re-export — passed.
 *
 * Loosening the check is the easy half. These fixtures are the hard half: every
 * state that must STILL be red, pinned beside the one that must now be green.
 */

const MIN = MIN_CONTENT_CHARS;

/** A populated feed's worth of text. */
const POPULATED_CHARS = 30_165;

describe("main-region classification — the /discover false red", () => {
  it("a populated page WITH a leftover skeleton marker is content", () => {
    // The exact deployed shape: real feed text, and the route shell still in
    // the document beside it.
    const verdict = classifyMainRegion({
      textLength: POPULATED_CHARS,
      skeletonTextLength: 0,
      visibleSkeletonCount: 1,
    });
    assert.equal(verdict.state, CONTENT_STATES.CONTENT);
    assert.equal(verdict.nonBlank, true);
    assert.match(verdict.detail, /skeleton marker/);
  });

  it("`/` and `/discover` grade identically for identical rendered content", () => {
    // This is the defect, stated as an invariant. The ONLY difference between
    // the two surfaces is how many inert skeleton markers the framework emitted.
    const landing = classifyMainRegion({
      textLength: POPULATED_CHARS,
      skeletonTextLength: 0,
      visibleSkeletonCount: 1,
    });
    const route = classifyMainRegion({
      textLength: POPULATED_CHARS,
      skeletonTextLength: 0,
      visibleSkeletonCount: 2,
    });
    assert.equal(landing.state, route.state);
    assert.equal(landing.nonBlank, route.nonBlank);
    assert.equal(route.nonBlank, true);
  });

  it("skeletons are RANKED, not ignored — a skeleton-only page is still red", () => {
    // The regression the fix must not introduce. A shell carries chrome text
    // ("Discover", a filter label) that clears the raw 40-char floor, so a
    // naive "drop the skeleton clause" would have turned this green.
    const verdict = classifyMainRegion({
      textLength: 120,
      skeletonTextLength: 120,
      visibleSkeletonCount: 3,
    });
    assert.equal(verdict.state, CONTENT_STATES.LOADING);
    assert.equal(verdict.nonBlank, false);
    assert.match(verdict.detail, /only the loading skeleton/);
  });

  it("a genuine empty state is content — its copy is real rendered text", () => {
    const verdict = classifyMainRegion({
      textLength: 96,
      skeletonTextLength: 0,
      visibleSkeletonCount: 0,
    });
    assert.equal(verdict.state, CONTENT_STATES.CONTENT);
    assert.equal(verdict.nonBlank, true);
  });

  it("the unavailable/retry state is content — not blank, but not legitimate either", () => {
    // "Failed to load feed" + "Try again" IS something on screen, so the region
    // check passes. It is `content.real_card_or_named_empty` that refuses to
    // accept an error state as an outcome — see the journey-level fixture
    // below. Two checks, two jobs; neither can certify the other's blind spot.
    const verdict = classifyMainRegion({
      textLength: 64,
      skeletonTextLength: 0,
      visibleSkeletonCount: 0,
    });
    assert.equal(verdict.nonBlank, true);
  });

  it("a truly blank region is blank, and says so distinctly from loading", () => {
    const verdict = classifyMainRegion({
      textLength: 4,
      skeletonTextLength: 0,
      visibleSkeletonCount: 0,
    });
    assert.equal(verdict.state, CONTENT_STATES.BLANK);
    assert.equal(verdict.nonBlank, false);
    assert.doesNotMatch(verdict.detail, /skeleton/);
  });

  it("the character floor is a threshold, not a formality", () => {
    const atFloor = classifyMainRegion({
      textLength: MIN,
      skeletonTextLength: 0,
      visibleSkeletonCount: 0,
    });
    assert.equal(atFloor.nonBlank, false, "exactly the floor is not above it");

    const overFloor = classifyMainRegion({
      textLength: MIN + 1,
      skeletonTextLength: 0,
      visibleSkeletonCount: 0,
    });
    assert.equal(overFloor.nonBlank, true);
  });

  it("chrome text around a skeleton does not become content", () => {
    // Header/nav text lives in `main` on some surfaces. Non-skeleton characters
    // must clear the floor on their OWN, not on the skeleton's back.
    const verdict = classifyMainRegion({
      textLength: 200,
      skeletonTextLength: 175,
      visibleSkeletonCount: 2,
    });
    assert.equal(verdict.state, CONTENT_STATES.LOADING);
    assert.equal(verdict.nonBlank, false);
  });
});

describe("malformed markup is its own outcome, never a quiet pass", () => {
  it("skeleton text exceeding the whole region is malformed", () => {
    const verdict = classifyMainRegion({
      textLength: 10,
      skeletonTextLength: 5_000,
      visibleSkeletonCount: 1,
    });
    assert.equal(verdict.state, CONTENT_STATES.MALFORMED);
    assert.equal(verdict.nonBlank, false);
    assert.match(verdict.detail, /exceeds the whole main region/);
  });

  it("missing, negative or non-numeric measurements are malformed", () => {
    const broken = [
      {},
      { textLength: 100, skeletonTextLength: 0 },
      { textLength: 100, skeletonTextLength: 0, visibleSkeletonCount: -1 },
      { textLength: -1, skeletonTextLength: 0, visibleSkeletonCount: 0 },
      { textLength: NaN, skeletonTextLength: 0, visibleSkeletonCount: 0 },
      { textLength: Infinity, skeletonTextLength: 0, visibleSkeletonCount: 0 },
      { textLength: "30165", skeletonTextLength: 0, visibleSkeletonCount: 0 },
      { textLength: null, skeletonTextLength: null, visibleSkeletonCount: null },
    ];
    for (const input of broken) {
      const verdict = classifyMainRegion(input);
      assert.equal(
        verdict.state,
        CONTENT_STATES.MALFORMED,
        `${JSON.stringify(input)} should be malformed`
      );
      assert.equal(verdict.nonBlank, false);
    }
  });

  it("a null observation does not throw", () => {
    assert.equal(classifyMainRegion(null).state, CONTENT_STATES.MALFORMED);
    assert.equal(classifyMainRegion(undefined).nonBlank, false);
  });
});

/**
 * The same states, driven through the WHOLE evaluator — because the classifier
 * being right is worth nothing if `evaluateJourney` reads the wrong field, and
 * because the independence of the two content checks is a property of the
 * evaluator, not of either check alone.
 */
describe("the evaluator consumes the measurements", () => {
  const SHA = "a".repeat(40);

  function journey(overrides = {}) {
    return {
      infra: null,
      shaMatch: true,
      shaDetail: `frontend deployment matches ${SHA}`,
      expectedPath: "/discover",
      urlPath: "/discover",
      realCardFound: true,
      firstCardMs: 1234,
      emptyState: null,
      mainRegion: {
        textLength: POPULATED_CHARS,
        skeletonTextLength: 0,
        visibleSkeletonCount: 1,
      },
      consoleErrors: [],
      pageErrors: [],
      failedRequests: [],
      artifacts: [{ name: "terminal.png", sha256: "b".repeat(64) }],
      ...overrides,
    };
  }

  const failedIds = (o) =>
    evaluateJourney(o)
      .assertions.filter((a) => !a.ok)
      .map((a) => a.assertion_id);

  it("the deployed /discover shape now passes end to end", () => {
    assert.equal(evaluateJourney(journey()).result, "pass");
  });

  it("a skeleton-only page still fails the journey", () => {
    const o = journey({
      realCardFound: false,
      firstCardMs: null,
      mainRegion: { textLength: 120, skeletonTextLength: 120, visibleSkeletonCount: 3 },
    });
    assert.equal(evaluateJourney(o).result, "fail");
    assert.ok(failedIds(o).includes("content.main_region_nonblank"));
  });

  it("THE INDEPENDENCE PROPERTY: a non-blank region cannot certify an error state", () => {
    // The unavailable/retry page. Its copy is real, so the region check passes
    // — and the journey must STILL fail, because an error state is not a
    // legitimate outcome. If both checks ever read the same signal, this is the
    // fixture that goes green and nobody notices.
    const o = journey({
      realCardFound: false,
      firstCardMs: null,
      emptyState: null,
      mainRegion: { textLength: 64, skeletonTextLength: 0, visibleSkeletonCount: 0 },
    });
    const ids = failedIds(o);
    assert.equal(evaluateJourney(o).result, "fail");
    assert.ok(ids.includes("content.real_card_or_named_empty"));
    assert.ok(
      !ids.includes("content.main_region_nonblank"),
      "the region really was non-blank — the OTHER check is what must catch this"
    );
  });

  it("conversely, a proven named empty state cannot rescue a blank region", () => {
    const o = journey({
      realCardFound: false,
      firstCardMs: null,
      emptyState: { name: "You're all caught up", visible: true },
      mainRegion: { textLength: 3, skeletonTextLength: 0, visibleSkeletonCount: 0 },
    });
    const ids = failedIds(o);
    assert.equal(evaluateJourney(o).result, "fail");
    assert.ok(ids.includes("content.main_region_nonblank"));
    assert.ok(!ids.includes("content.real_card_or_named_empty"));
  });

  it("malformed measurements fail the journey and name themselves", () => {
    const o = journey({
      mainRegion: { textLength: 10, skeletonTextLength: 5_000, visibleSkeletonCount: 1 },
    });
    assert.equal(evaluateJourney(o).result, "fail");
    const failed = evaluateJourney(o).assertions.find(
      (a) => a.assertion_id === "content.main_region_nonblank"
    );
    assert.match(failed.detail, /^malformed:/);
  });

  it("measurements win over a disagreeing legacy boolean", () => {
    // A spec that computes its own optimistic verdict must not be able to
    // override what it measured.
    const o = journey({
      mainRegionNonBlank: true,
      mainRegion: { textLength: 120, skeletonTextLength: 120, visibleSkeletonCount: 3 },
    });
    assert.ok(failedIds(o).includes("content.main_region_nonblank"));
  });

  it("the legacy boolean still works for surfaces not yet converted", () => {
    const passing = journey({ mainRegion: undefined, mainRegionNonBlank: true });
    assert.equal(evaluateJourney(passing).result, "pass");
    const failing = journey({ mainRegion: undefined, mainRegionNonBlank: false });
    assert.ok(failedIds(failing).includes("content.main_region_nonblank"));
  });

  it("supplying NEITHER form is a failure, not an absent check", () => {
    const o = journey({ mainRegion: undefined, mainRegionNonBlank: undefined });
    assert.equal(evaluateJourney(o).result, "fail");
    const failed = evaluateJourney(o).assertions.find(
      (a) => a.assertion_id === "content.main_region_nonblank"
    );
    assert.match(failed.detail, /no main-region observation/);
    assert.ok(
      !evaluateJourney(o).checked_clean.some((c) => c.startsWith("content.main_region_nonblank")),
      "an unobserved region must never be recorded as checked-clean"
    );
  });
});
