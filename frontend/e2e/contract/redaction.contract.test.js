"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { assertRedacted, redactHeaders, redactText, redactUrl } = require("../helpers/redaction");

/**
 * L2-221 Item 1 — "no raw cookies/auth headers/storage state or arbitrary
 * query/user text enters artifacts."
 *
 * The build-tag test below matters most: `1.4.2 (231)` must survive intact.
 * A scrubber that mangles build tags cannot attest build identity — the
 * L2-219/L2-220 shape-vs-digit-count trap, which this rail would otherwise
 * have inherited verbatim.
 */

describe("query and user text", () => {
  it("removes query VALUES and keeps keys", () => {
    assert.equal(
      redactUrl("https://www.bainluck.com/search?q=alex+mortgage&page=2"),
      "https://www.bainluck.com/search?q=[redacted-value]&page=[redacted-value]"
    );
  });

  it("drops fragments entirely", () => {
    assert.equal(
      redactUrl("https://www.bainluck.com/preferences#telemetry"),
      "https://www.bainluck.com/preferences"
    );
  });

  it("handles relative paths without throwing", () => {
    assert.equal(redactUrl("/api/feed?limit=20"), "/api/feed?limit=[redacted-value]");
    assert.equal(redactUrl("/api/feed"), "/api/feed");
  });

  it("strips query values from a URL embedded in prose", () => {
    const out = redactText("failed GET https://www.bainluck.com/search?q=secret-term 500");
    assert.ok(!out.includes("secret-term"), out);
  });
});

describe("credentials and identity", () => {
  it("drops auth and cookie headers rather than shortening them", () => {
    const out = redactHeaders({
      Authorization: "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
      Cookie: "session=abc123; theme=light",
      "Set-Cookie": "session=abc123",
      "Content-Type": "application/json",
    });
    assert.equal(out.authorization, "[redacted]");
    assert.equal(out.cookie, "[redacted]");
    assert.equal(out["set-cookie"], "[redacted]");
    assert.equal(out["content-type"], "application/json");
  });

  it("scrubs emails, JWTs and bearer tokens from free text", () => {
    assert.ok(redactText("login failed for alex@bainluck.com").includes("[redacted-email]"));
    assert.ok(!redactText("token eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop").includes("eyJ"));
    assert.ok(!redactText("Authorization: Bearer sk_live_abcdefghijklmnop").includes("sk_live_"));
  });

  it("scrubs long hex tokens", () => {
    assert.ok(redactText(`key ${"a".repeat(40)}`).includes("[redacted-token]"));
  });

  it("bounds free-text length", () => {
    assert.ok(redactText("x".repeat(2000)).length < 600);
  });
});

describe("the shape-vs-digit-count trap (L2-219 / L2-220)", () => {
  it("leaves a build tag intact", () => {
    assert.equal(redactText("1.4.2 (231)"), "1.4.2 (231)");
  });

  it("does not treat short version-like strings as phone numbers", () => {
    for (const value of ["v2.1.0", "14.2 (99)", "1-2-3", "2026-07-31"]) {
      assert.equal(redactText(value), value);
    }
  });

  it("but redacts a real phone number, >= 7 digits", () => {
    assert.ok(redactText("call +1 (415) 555-0134").includes("[redacted-phone]"));
    assert.equal(redactText("4155550134"), "[redacted-phone]");
  });
});

describe("assertRedacted — the last gate before publication", () => {
  it("passes a clean payload", () => {
    assert.deepEqual(assertRedacted({ headers: { cookie: "[redacted]" }, msg: "ok" }), {
      ok: true,
      leaks: [],
    });
  });

  it("catches a raw cookie header", () => {
    const result = assertRedacted({ headers: { cookie: "session=abc123" } });
    assert.equal(result.ok, false);
    assert.ok(result.leaks.includes("cookie_header"));
  });

  it("catches a raw authorization header", () => {
    assert.equal(assertRedacted({ headers: { authorization: "Bearer abc" } }).ok, false);
  });

  it("catches an email anywhere in the payload", () => {
    assert.ok(assertRedacted({ deep: { nested: ["alex@bainluck.com"] } }).leaks.includes("email"));
  });

  it("catches a Playwright storage-state blob", () => {
    const storageState = { cookies: [{ name: "session", value: "abc", domain: "x" }], origins: [] };
    assert.equal(assertRedacted(storageState).ok, false);
  });
});
