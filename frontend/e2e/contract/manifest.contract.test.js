"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const {
  SCHEMA_VERSION,
  REQUIRED_RUN_FIELDS,
  REQUIRED_JOURNEY_FIELDS,
  buildRunManifest,
  deriveRunResult,
  validateManifest,
} = require("../helpers/manifest");

/**
 * L2-221 Item 1 — manifest invariants.
 *
 * A manifest is the ONLY thing downstream consumers see. If it can validate
 * while the run proved nothing, the whole rail is theatre. These fixtures
 * cover the queue's named cases: zero selected journeys, wrong/missing SHA,
 * missing artifacts, non-terminal results, and redaction leaks.
 */

const SHA_TARGET = "1".repeat(40);
const SHA_OTHER = "2".repeat(40);
const DIGEST = "c".repeat(64);

function journey(overrides = {}) {
  return {
    journey_id: "discover.landing",
    project: "desktop",
    viewport: { width: 1440, height: 900 },
    url_path: "/",
    redirect_chain: [],
    selected_fixture_ids: [],
    started_at_utc: "2026-07-31T19:00:00.000Z",
    finished_at_utc: "2026-07-31T19:00:12.000Z",
    duration_ms: 12000,
    assertions: [{ assertion_id: "content.real_card_or_named_empty", ok: true, detail: null }],
    checked_clean: [],
    console_errors: [],
    page_errors: [],
    failed_requests: [],
    telemetry_requests: [],
    first_card_ms: 900,
    artifacts: [{ name: "terminal.png", path: "artifacts/terminal.png", sha256: DIGEST, bytes: 1024 }],
    attempt: 1,
    result: "pass",
    ...overrides,
  };
}

function manifest(overrides = {}) {
  return buildRunManifest({
    runId: "1234",
    runUrl: "https://github.com/alexander-bain/bainluck/actions/runs/1234",
    pack: "deploy-smoke",
    trigger: "workflow_dispatch",
    startedAt: "2026-07-31T19:00:00.000Z",
    finishedAt: "2026-07-31T19:01:00.000Z",
    requestedFrontendSha: SHA_TARGET,
    observedFrontendSha: SHA_TARGET,
    checkoutSha: SHA_TARGET,
    runnerStatus: "passed",
    observedBackendSha: "deadbeef",
    baseUrl: "https://www.bainluck.com",
    apiBaseUrl: "https://api.bainluck.com",
    runtime: { node: "v20.11.0", playwright: "1.48.2", browser: "chromium-1140", os: "linux-x64" },
    selectedCount: 1,
    journeys: [journey()],
    ...overrides,
  });
}

function rejects(m, needle) {
  const result = validateManifest(m);
  assert.equal(result.ok, false, "expected the manifest to be rejected");
  if (needle) {
    assert.ok(
      result.errors.join("\n").includes(needle),
      `expected an error mentioning "${needle}", got:\n${result.errors.join("\n")}`
    );
  }
}

describe("manifest — the control", () => {
  it("a complete manifest validates", () => {
    const result = validateManifest(manifest());
    assert.deepEqual(result.errors, []);
    assert.equal(result.ok, true);
  });
});

describe("manifest invariants — each of these must be REJECTED", () => {
  it("zero selected journeys", () => {
    rejects(manifest({ selectedCount: 0, journeys: [] }), "selected_count");
  });

  it("a run with journeys but selected_count 0 still fails", () => {
    rejects(manifest({ selectedCount: 0 }));
  });

  it("frontend SHA mismatch", () => {
    rejects(manifest({ observedFrontendSha: SHA_OTHER }), "frontend sha mismatch");
  });

  it("missing frontend SHA — the backend SHA can never stand in for it", () => {
    rejects(
      manifest({ observedFrontendSha: null, observedBackendSha: SHA_TARGET }),
      "observed_frontend_sha"
    );
  });

  it("an abbreviated SHA is not authority", () => {
    rejects(manifest({ requestedFrontendSha: SHA_TARGET.slice(0, 7) }));
  });

  it("a journey with no artifacts", () => {
    rejects(manifest({ journeys: [journey({ artifacts: [] })] }), "artifacts");
  });

  it("an artifact with no digest", () => {
    rejects(manifest({ journeys: [journey({ artifacts: [{ name: "x.png", sha256: "nope" }] })] }));
  });

  it("a non-terminal journey result", () => {
    rejects(manifest({ journeys: [journey({ result: "running" })] }));
  });

  it("a journey claiming pass while carrying a failed assertion", () => {
    rejects(
      manifest({
        journeys: [
          journey({
            result: "pass",
            assertions: [{ assertion_id: "console.no_errors", ok: false, detail: "1 error" }],
          }),
        ],
      }),
      "pass while carrying a failed assertion"
    );
  });

  it("a run claiming pass while carrying a failing journey", () => {
    const m = manifest({
      journeys: [
        journey({
          result: "fail",
          assertions: [{ assertion_id: "console.no_errors", ok: false, detail: "1 error" }],
        }),
      ],
    });
    // buildRunManifest derives `fail`; force the lie to prove it is caught.
    m.run.result = "pass";
    m.run.failed_count = 0;
    rejects(m, "disagrees with the journeys");
  });

  it("a superseded run must name what superseded it", () => {
    const m = manifest({ observedFrontendSha: SHA_OTHER, superseded: true });
    rejects(m, "superseded_by");
    m.run.superseded_by = SHA_OTHER;
    assert.deepEqual(validateManifest(m).errors, []);
  });

  it("duplicate journey ids within the same project", () => {
    rejects(manifest({ selectedCount: 2, journeys: [journey(), journey()] }));
  });

  it("a wrong schema version", () => {
    const m = manifest();
    m.schema_version = "browser-audit/v0";
    rejects(m);
  });

  it("REDACTION: a leaked bearer token fails validation", () => {
    const m = manifest();
    m.journeys[0].failed_requests = [
      { url: "/api/feed", status: 500, failure: "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop" },
    ];
    rejects(m, "redaction failed");
  });

  it("REDACTION: an email anywhere in the manifest fails validation", () => {
    const m = manifest();
    m.journeys[0].console_errors = ["failed for alex@example.com"];
    rejects(m, "redaction failed");
  });
});

describe("run result derivation", () => {
  it("an empty journey list is an infra_error, never a pass", () => {
    assert.equal(deriveRunResult([]), "infra_error");
  });

  it("one infra_error dominates", () => {
    assert.equal(deriveRunResult([{ result: "pass" }, { result: "infra_error" }]), "infra_error");
  });

  it("one fail dominates a pass", () => {
    assert.equal(deriveRunResult([{ result: "pass" }, { result: "fail" }]), "fail");
  });

  it("all pass is the only route to pass", () => {
    assert.equal(deriveRunResult([{ result: "pass" }, { result: "pass" }]), "pass");
  });
});

describe("published schema and enforcing validator agree", () => {
  const schemaPath = path.join(__dirname, "..", "schema", "audit-manifest.schema.json");
  const schema = JSON.parse(fs.readFileSync(schemaPath, "utf8"));

  it("schema_version const matches the code", () => {
    assert.equal(schema.properties.schema_version.const, SCHEMA_VERSION);
  });

  it("required run fields match", () => {
    assert.deepEqual(
      [...schema.properties.run.required].sort(),
      [...REQUIRED_RUN_FIELDS].sort()
    );
  });

  it("required journey fields match", () => {
    assert.deepEqual(
      [...schema.properties.journeys.items.required].sort(),
      [...REQUIRED_JOURNEY_FIELDS].sort()
    );
  });

  it("the schema forbids a zero selected_count and an empty journey list", () => {
    assert.equal(schema.properties.run.properties.selected_count.minimum, 1);
    assert.equal(schema.properties.journeys.minItems, 1);
  });
});
