"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { evaluateJourney } = require("../helpers/journey");

/**
 * L2-221 Item 1 — the false-green fixtures.
 *
 * These drive the SAME evaluator the live specs use, with no browser and no
 * network, so a fixture proven to fail here cannot pass in production.
 *
 * They run on `node --test` — no Playwright, no browser download, no registry
 * — deliberately. A gate that only runs when a package install succeeds is a
 * gate that will be skipped on the day it matters.
 */

const SHA_A = "a".repeat(40);

/** A journey that should be, and stays, green. Every fixture mutates this. */
function healthy(overrides = {}) {
  return {
    infra: null,
    shaMatch: true,
    shaDetail: "frontend deployment matches the requested sha",
    expectedPath: "/discover",
    urlPath: "/discover",
    realCardFound: true,
    firstCardMs: 1234,
    emptyState: null,
    mainRegionNonBlank: true,
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    artifacts: [{ name: "terminal.png", sha256: "b".repeat(64) }],
    ...overrides,
  };
}

function failedIds(observation) {
  return evaluateJourney(observation)
    .assertions.filter((a) => !a.ok)
    .map((a) => a.assertion_id);
}

describe("journey evaluator — the control", () => {
  it("a healthy journey passes", () => {
    const verdict = evaluateJourney(healthy());
    assert.equal(verdict.result, "pass");
    assert.ok(verdict.assertions.every((a) => a.ok));
  });

  it("is not vacuous — the control carries real assertions", () => {
    // Guards against the evaluator degrading to "no checks, all green".
    const ids = evaluateJourney(healthy()).assertions.map((a) => a.assertion_id);
    assert.ok(ids.includes("content.real_card_or_named_empty"));
    assert.ok(ids.includes("build.frontend_sha_matches"));
    assert.ok(ids.includes("network.no_unexpected_failures"));
    assert.ok(ids.length >= 8, `expected >= 8 assertions, got ${ids.length}`);
  });
});

describe("false-green fixtures — every one of these must FAIL", () => {
  it("blank DOM: no card, no empty state", () => {
    const observation = healthy({ realCardFound: false, firstCardMs: null, mainRegionNonBlank: false });
    assert.equal(evaluateJourney(observation).result, "fail");
    const ids = failedIds(observation);
    assert.ok(ids.includes("content.real_card_or_named_empty"));
    assert.ok(ids.includes("content.main_region_nonblank"));
  });

  it("THE C96 P1 REGRESSION: a duration recorded for a card that never appeared", () => {
    // The exact old-spec behaviour — `.catch(() => {})` then record
    // `Date.now() - t0` anyway. It must fail on BOTH counts.
    const observation = healthy({ realCardFound: false, firstCardMs: 4210 });
    assert.equal(evaluateJourney(observation).result, "fail");
    const ids = failedIds(observation);
    assert.ok(ids.includes("timing.duration_only_when_observed"));
    assert.ok(ids.includes("content.real_card_or_named_empty"));
  });

  it("console error", () => {
    const observation = healthy({ consoleErrors: ["TypeError: x is not a function"] });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("console.no_errors"));
  });

  it("uncaught page error", () => {
    const observation = healthy({ pageErrors: ["ReferenceError: boom"] });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("page.no_uncaught_errors"));
  });

  it("failed request", () => {
    const observation = healthy({
      failedRequests: [{ url: "https://www.bainluck.com/api/feed", status: 500 }],
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  it("wrong SHA", () => {
    const observation = healthy({ shaMatch: false, shaDetail: `frontend deployment is ${SHA_A}` });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("build.frontend_sha_matches"));
  });

  it("missing SHA — an unresolved authority is a failure, not a skip", () => {
    for (const value of [null, undefined]) {
      const observation = healthy({ shaMatch: value });
      assert.equal(evaluateJourney(observation).result, "fail");
      assert.ok(failedIds(observation).includes("build.frontend_sha_matches"));
    }
  });

  it("missing artifact", () => {
    assert.ok(failedIds(healthy({ artifacts: [] })).includes("evidence.artifacts_present"));
    assert.ok(
      failedIds(healthy({ artifacts: [{ name: "terminal.png", sha256: "" }] })).includes(
        "evidence.artifacts_present"
      )
    );
  });

  it("an empty state that was DECLARED but not seen is not proof", () => {
    const observation = healthy({
      realCardFound: false,
      firstCardMs: null,
      emptyState: { name: "You're all caught up", visible: false },
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("content.real_card_or_named_empty"));
  });

  it("an UNNAMED empty state is not proof either", () => {
    const observation = healthy({
      realCardFound: false,
      firstCardMs: null,
      emptyState: { name: "", visible: true },
    });
    assert.equal(evaluateJourney(observation).result, "fail");
  });

  it("wrong route", () => {
    const observation = healthy({ expectedPath: "/discover", urlPath: "/login" });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("route.expected_path"));
  });
});

describe("legitimate outcomes", () => {
  it("a NAMED empty state that was actually visible passes", () => {
    const verdict = evaluateJourney(
      healthy({
        realCardFound: false,
        firstCardMs: null,
        emptyState: { name: "You're all caught up", visible: true },
      })
    );
    assert.equal(verdict.result, "pass");
  });

  it("a crashed browser is infra_error, never a product fail", () => {
    const verdict = evaluateJourney(
      healthy({ infra: { crashed: true, reason: "page crashed" }, realCardFound: false })
    );
    assert.equal(verdict.result, "infra_error");
  });

  it("an explicitly allowed failure does not fail the journey", () => {
    const url = "https://www.bainluck.com/api/known-404";
    const verdict = evaluateJourney(
      healthy({ failedRequests: [{ url, status: 404 }], allowedFailures: [url] })
    );
    assert.equal(verdict.result, "pass");
  });
});
