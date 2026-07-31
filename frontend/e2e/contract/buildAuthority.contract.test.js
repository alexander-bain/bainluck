"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { compareSha, normalizeSha, waitForFrontendSha } = require("../helpers/buildAuthority");

/**
 * L2-221 Item 2 — build-authority contract.
 *
 * Clock and fetch are injected, so the timeout, mismatch and never-appears
 * paths are covered deterministically — no network, no real waiting.
 */

const SHA_TARGET = "1".repeat(40);
const SHA_OTHER = "2".repeat(40);

describe("sha normalization", () => {
  it("accepts a full 40-hex sha, case-insensitively", () => {
    assert.equal(normalizeSha(SHA_TARGET.toUpperCase()), SHA_TARGET);
    assert.equal(normalizeSha(`  ${SHA_TARGET}  `), SHA_TARGET);
  });

  it("rejects abbreviations, empties and non-strings", () => {
    for (const bad of [SHA_TARGET.slice(0, 7), "", "  ", null, undefined, 42, "zz".repeat(20)]) {
      assert.equal(normalizeSha(bad), null, `expected ${String(bad)} to be rejected`);
    }
  });
});

describe("compareSha", () => {
  it("matches only on an exact full sha", () => {
    assert.equal(compareSha(SHA_TARGET, SHA_TARGET).match, true);
    assert.equal(compareSha(SHA_TARGET, SHA_OTHER).match, false);
  });

  it("a 7-char prefix of the SAME commit does not satisfy authority", () => {
    const verdict = compareSha(SHA_TARGET, SHA_TARGET.slice(0, 7));
    assert.equal(verdict.match, false);
    assert.ok(verdict.reason.includes("build marker"));
  });

  it("a missing marker fails with a reason distinct from a mismatch", () => {
    assert.ok(compareSha(SHA_TARGET, null).reason.includes("missing"));
    assert.ok(compareSha(SHA_TARGET, SHA_OTHER).reason.includes("requested"));
  });

  it("a missing request is itself a failure", () => {
    assert.equal(compareSha(null, SHA_TARGET).match, false);
  });
});

/** A fetch stub returning a scripted sequence of build markers. */
function stubFetch(sequence) {
  let call = 0;
  const impl = async () => {
    const step = sequence[Math.min(call, sequence.length - 1)];
    call += 1;
    if (step.throws) throw new Error(step.throws);
    return {
      ok: (step.status ?? 200) < 400,
      status: step.status ?? 200,
      json: async () => ({ commit: step.commit ?? null }),
    };
  };
  return { impl, calls: () => call };
}

describe("waitForFrontendSha", () => {
  const base = { baseUrl: "https://www.bainluck.com", intervalMs: 1, timeoutMs: 50 };
  const noSleep = async () => {};

  it("succeeds when the marker already matches", async () => {
    const { impl } = stubFetch([{ commit: SHA_TARGET }]);
    const result = await waitForFrontendSha({
      ...base,
      requestedSha: SHA_TARGET,
      fetchImpl: impl,
      sleep: noSleep,
    });
    assert.equal(result.ok, true);
    assert.equal(result.observed, SHA_TARGET);
    assert.equal(result.attempts, 1);
  });

  it("keeps polling until the requested deployment lands", async () => {
    const { impl } = stubFetch([{ commit: SHA_OTHER }, { commit: SHA_OTHER }, { commit: SHA_TARGET }]);
    let clock = 0;
    const result = await waitForFrontendSha({
      ...base,
      timeoutMs: 1000,
      requestedSha: SHA_TARGET,
      fetchImpl: impl,
      now: () => (clock += 1),
      sleep: noSleep,
    });
    assert.equal(result.ok, true);
    assert.equal(result.attempts, 3);
  });

  it("times out when the requested sha never deploys — and reports what IS deployed", async () => {
    const { impl } = stubFetch([{ commit: SHA_OTHER }]);
    let clock = 0;
    const result = await waitForFrontendSha({
      ...base,
      timeoutMs: 5,
      requestedSha: SHA_TARGET,
      fetchImpl: impl,
      now: () => (clock += 10),
      sleep: noSleep,
    });
    assert.equal(result.ok, false);
    assert.equal(result.observed, SHA_OTHER);
    assert.ok(result.reason.includes("timed out"));
  });

  it("a missing marker route times out rather than passing", async () => {
    const { impl } = stubFetch([{ status: 404 }]);
    let clock = 0;
    const result = await waitForFrontendSha({
      ...base,
      timeoutMs: 5,
      requestedSha: SHA_TARGET,
      fetchImpl: impl,
      now: () => (clock += 10),
      sleep: noSleep,
    });
    assert.equal(result.ok, false);
    assert.ok(result.lastError.includes("404"));
  });

  it("a network error never resolves as success", async () => {
    const { impl } = stubFetch([{ throws: "ECONNREFUSED" }]);
    let clock = 0;
    const result = await waitForFrontendSha({
      ...base,
      timeoutMs: 5,
      requestedSha: SHA_TARGET,
      fetchImpl: impl,
      now: () => (clock += 10),
      sleep: noSleep,
    });
    assert.equal(result.ok, false);
    assert.ok(result.lastError.includes("ECONNREFUSED"));
  });

  it("an unusable requested sha short-circuits without a single request", async () => {
    const { impl, calls } = stubFetch([{ commit: SHA_TARGET }]);
    const result = await waitForFrontendSha({
      ...base,
      requestedSha: "not-a-sha",
      fetchImpl: impl,
      sleep: noSleep,
    });
    assert.equal(result.ok, false);
    assert.equal(calls(), 0);
  });
});
