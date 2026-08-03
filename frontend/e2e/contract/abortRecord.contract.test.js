"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { isAbort, boundedMs, describeAbort } = require("../helpers/abortRecord");

/**
 * L2-241 — the bounded abort packet (#1525 Shape A).
 *
 * The point of these fields is to distinguish a navigation TEARDOWN from a
 * client TIMEOUT on an aborted first-party request, without dumping anything
 * unbounded or sensitive into the manifest. This drives the same pure shaper the
 * live collector (`fixtures/audit.ts`) calls, so a fixture that passes here
 * cannot behave differently in a real run.
 */

describe("isAbort — narrow by design", () => {
  it("matches net::ERR_ABORTED and the bare word", () => {
    assert.equal(isAbort("net::ERR_ABORTED"), true);
    assert.equal(isAbort("NS_BINDING_ABORTED — request was aborted"), true);
  });

  it("does NOT match unrelated failures", () => {
    assert.equal(isAbort("net::ERR_NAME_NOT_RESOLVED"), false);
    assert.equal(isAbort("net::ERR_CONNECTION_REFUSED"), false);
    assert.equal(isAbort("collaborated"), false); // substring "aborated" must not trip
    assert.equal(isAbort(undefined), false);
    assert.equal(isAbort(null), false);
  });
});

describe("boundedMs — no misleading zeros", () => {
  it("rounds a real number", () => {
    assert.equal(boundedMs(12.7), 13);
    assert.equal(boundedMs(0), 0);
  });
  it("maps Playwright's -1 / non-finite to null, never 0", () => {
    assert.equal(boundedMs(-1), null);
    assert.equal(boundedMs(NaN), null);
    assert.equal(boundedMs(Infinity), null);
    assert.equal(boundedMs("300"), null);
    assert.equal(boundedMs(undefined), null);
  });
});

describe("describeAbort — only on an abort, and only bounded fields", () => {
  it("returns null when the failure is not an abort", () => {
    assert.equal(
      describeAbort({ failureText: "net::ERR_CONNECTION_REFUSED", timing: { requestStart: 10 } }),
      null
    );
  });

  it("a teardown: aborted early, mostly -1 phases, tiny elapsed", () => {
    const packet = describeAbort({
      failureText: "net::ERR_ABORTED",
      resourceType: "fetch",
      timing: { requestStart: 3, responseStart: -1, responseEnd: -1, connectEnd: 2 },
      frameUrl: "https://www.bainluck.com/sports?session=secret",
      isFeed: true,
    });
    assert.equal(packet.aborted, true);
    assert.equal(packet.resource_type, "fetch");
    assert.equal(packet.is_feed_request, true);
    assert.equal(packet.elapsed_before_abort_ms, 3); // max of the non-negative phases
    // frame_url keeps origin+path, drops the query VALUE.
    assert.equal(packet.frame_url, "https://www.bainluck.com/sports?session=[redacted-value]");
  });

  it("a timeout: aborted after a long wait — a large elapsed distinguishes it", () => {
    const teardown = describeAbort({
      failureText: "net::ERR_ABORTED",
      timing: { requestStart: 4, responseStart: -1, responseEnd: -1 },
    });
    const timeout = describeAbort({
      failureText: "net::ERR_ABORTED",
      timing: { requestStart: 5, responseStart: 30020, responseEnd: -1 },
    });
    assert.equal(teardown.elapsed_before_abort_ms, 4);
    assert.equal(timeout.elapsed_before_abort_ms, 30020);
    assert.ok(
      timeout.elapsed_before_abort_ms > teardown.elapsed_before_abort_ms * 100,
      "the two abort shapes must be numerically separable"
    );
  });

  it("elapsed is null when no phase ever fired (nothing to attest)", () => {
    const packet = describeAbort({
      failureText: "net::ERR_ABORTED",
      timing: { requestStart: -1, responseStart: -1, responseEnd: -1 },
    });
    assert.equal(packet.elapsed_before_abort_ms, null);
  });

  it("stays bounded — resource_type capped, no unexpected keys, missing inputs tolerated", () => {
    const packet = describeAbort({
      failureText: "net::ERR_ABORTED",
      resourceType: "x".repeat(200),
      timing: null,
    });
    assert.ok(packet.resource_type.length <= 40, "resource_type must be capped");
    assert.equal(packet.elapsed_before_abort_ms, null);
    assert.equal(packet.is_feed_request, false);
    assert.equal(packet.frame_url, null);
    assert.deepEqual(
      Object.keys(packet).sort(),
      ["aborted", "elapsed_before_abort_ms", "frame_url", "is_feed_request", "resource_type"],
      "the packet must not grow unbounded fields"
    );
  });
});
