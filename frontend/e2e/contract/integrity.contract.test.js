"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const {
  CANONICAL_ORIGINS,
  CANONICAL_API_ORIGINS,
  ARTIFACT_ROOT,
  sha256,
  buildRunManifest,
  validateManifest,
  checkOrigin,
  checkArtifactPath,
  verifyArtifactBytes,
} = require("../helpers/manifest");
const { evaluateJourney } = require("../helpers/journey");

/**
 * L2-223 — the integrity gaps C98 found in the shipped phase-1 rail.
 *
 * Every fixture here is dependency-free (`node --test`, no Playwright, no
 * browser, no network) and drives the SAME functions the live rail uses, so a
 * case that fails here cannot pass in production.
 *
 * The through-line: L2-221 proved the rail could not report green with no
 * evidence. It could still report green with evidence that was *unbound* —
 * graded by a foreign commit, taken from a foreign origin, covering half the
 * selected journeys, produced by a dead runner, or described by artifacts
 * nobody ever wrote. Each of those is a fixture below.
 */

const SHA_DEPLOYED = "1".repeat(40);
const SHA_NEWER = "2".repeat(40);
const SHA_FOREIGN = "3".repeat(40);
const DIGEST = "c".repeat(64);

function journey(overrides = {}) {
  return {
    journey_id: "discover.landing",
    project: "desktop",
    viewport: { width: 1440, height: 900 },
    url_path: "/",
    final_origin: "https://www.bainluck.com",
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
    artifacts: [
      { name: "terminal.png", path: "artifacts/terminal.png", sha256: DIGEST, bytes: 1024 },
    ],
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
    requestedFrontendSha: SHA_DEPLOYED,
    observedFrontendSha: SHA_DEPLOYED,
    checkoutSha: SHA_DEPLOYED,
    runnerStatus: "passed",
    observedBackendSha: "deadbeef",
    baseUrl: "https://www.bainluck.com",
    apiBaseUrl: "https://api.bainluck.com",
    finalOrigin: "https://www.bainluck.com",
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

// ---------------------------------------------------------------------------
// Item 1 — the run is bound to a commit, an origin, a count, and a runner.
// ---------------------------------------------------------------------------

describe("control", () => {
  it("a fully-bound manifest still validates", () => {
    const result = validateManifest(manifest());
    assert.deepEqual(result.errors, []);
  });
});

describe("grading-commit authority", () => {
  it("rejects a manifest with no checkout sha — the grading commit is part of the claim", () => {
    rejects(manifest({ checkoutSha: null }), "checkout_sha");
  });

  it("rejects a checkout that differs from the audited commit with no proven ancestry", () => {
    // The realistic attack and the realistic accident are the same shape: run
    // the rail from a branch whose evaluator has been loosened, point it at
    // production, and file the green against the deployed commit.
    rejects(manifest({ checkoutSha: SHA_FOREIGN }), "without proven ancestry");
  });

  it("accepts a newer checkout ONLY when ancestry was proven", () => {
    // master legitimately runs ahead of what Vercel has deployed.
    const ok = validateManifest(
      manifest({ checkoutSha: SHA_NEWER, checkoutAncestry: "requested-is-ancestor-of-checkout" })
    );
    assert.deepEqual(ok.errors, []);
  });

  it("does not accept a hand-written ancestry claim of any other wording", () => {
    rejects(
      manifest({ checkoutSha: SHA_NEWER, checkoutAncestry: "probably fine" }),
      "without proven ancestry"
    );
  });

  it("still requires requested to equal observed — L2-221's invariant is untouched", () => {
    rejects(manifest({ observedFrontendSha: SHA_NEWER }), "frontend sha mismatch");
  });
});

describe("selected / completed equality", () => {
  it("rejects selected 2 with only 1 journey completed", () => {
    // The partial run: the runner died after the first journey. Before L2-223
    // this validated, because one record is not "more than" two.
    rejects(manifest({ selectedCount: 2 }), "must equal the number of journeys");
  });

  it("rejects more journeys than were selected", () => {
    rejects(
      manifest({ selectedCount: 1, journeys: [journey(), journey({ project: "mobile" })] }),
      "must equal the number of journeys"
    );
  });

  it("accepts an exact match across two viewports", () => {
    const ok = validateManifest(
      manifest({ selectedCount: 2, journeys: [journey(), journey({ project: "mobile" })] })
    );
    assert.deepEqual(ok.errors, []);
  });
});

describe("runner terminal status", () => {
  it("rejects a pass whose runner failed, even with every journey record passing", () => {
    rejects(manifest({ runnerStatus: "failed" }), "runner terminated");
  });

  it("rejects a pass whose runner timed out", () => {
    rejects(manifest({ runnerStatus: "timedout" }), "runner terminated");
  });

  it("rejects a pass whose runner was interrupted", () => {
    rejects(manifest({ runnerStatus: "interrupted" }), "runner terminated");
  });

  it("rejects an unrecorded runner status", () => {
    rejects(manifest({ runnerStatus: null }), "run.runner_status must be one of");
  });

  it("allows a non-passing runner to accompany a non-pass result", () => {
    // The honest combination: the runner failed AND the run is not green.
    const failing = journey({
      assertions: [{ assertion_id: "content.real_card_or_named_empty", ok: false, detail: "blank" }],
      result: "fail",
    });
    const result = validateManifest(
      manifest({ runnerStatus: "failed", journeys: [failing], result: undefined })
    );
    assert.deepEqual(result.errors, []);
  });
});

describe("canonical origin authority", () => {
  it("rejects a preview deployment origin", () => {
    // A preview host is a real Vercel deployment of a DIFFERENT build; a green
    // from one attached to a production commit is simply false.
    rejects(manifest({ baseUrl: "https://bainluck-git-feature.vercel.app" }), "not one of the canonical origins");
  });

  it("rejects a suffix-lookalike host", () => {
    const verdict = checkOrigin("https://www.bainluck.com.attacker.test", CANONICAL_ORIGINS, "f");
    assert.equal(verdict.ok, false);
  });

  it("rejects a subdomain of a canonical origin — allowlisting is exact", () => {
    const verdict = checkOrigin("https://preview.bainluck.com", CANONICAL_ORIGINS, "f");
    assert.equal(verdict.ok, false);
  });

  it("rejects plain http", () => {
    const verdict = checkOrigin("http://www.bainluck.com", CANONICAL_ORIGINS, "f");
    assert.equal(verdict.ok, false);
    assert.ok(verdict.errors.join(" ").includes("https"));
  });

  it("rejects a run that started canonical and REDIRECTED somewhere else", () => {
    rejects(manifest({ finalOrigin: "https://bainluck-git-feature.vercel.app" }), "run.final_origin");
  });

  it("rejects a foreign api origin", () => {
    rejects(manifest({ apiBaseUrl: "https://api.example.test" }), "run.api_base_url");
    assert.equal(checkOrigin("https://api.bainluck.com", CANONICAL_API_ORIGINS, "f").ok, true);
  });
});

describe("journey identity", () => {
  it("rejects a duplicated journey identity", () => {
    rejects(manifest({ selectedCount: 2, journeys: [journey(), journey()] }), "duplicates journey id");
  });

  it("rejects a non-terminal journey result", () => {
    rejects(manifest({ journeys: [journey({ result: "running" })] }), "journeys[0].result must be one of");
  });
});

describe("first-party API failures are our defects", () => {
  const base = {
    shaMatch: true,
    mainRegionNonBlank: true,
    realCardFound: true,
    firstCardMs: 800,
    artifacts: [{ name: "t.png", path: "artifacts/t.png", sha256: DIGEST }],
  };

  it("a backend 500 fails the journey", () => {
    // The bug this closes: the collector graded a 4xx/5xx only when its origin
    // equalled the SITE origin. api.bainluck.com is a different origin and
    // entirely ours, so every backend 500 behind a blank feed was discarded as
    // third-party noise and the journey went green on the empty state.
    const verdict = evaluateJourney({
      ...base,
      failedRequests: [{ url: "https://api.bainluck.com/api/feed", status: 500, method: "GET" }],
    });
    assert.equal(verdict.result, "fail");
    const network = verdict.assertions.find((a) => a.assertion_id === "network.no_unexpected_failures");
    assert.equal(network.ok, false);
  });

  it("a third-party failure does not fail the journey", () => {
    const verdict = evaluateJourney({ ...base, failedRequests: [] });
    assert.equal(verdict.result, "pass");
  });
});

describe("origin and redirect assertions inside a journey", () => {
  const base = {
    shaMatch: true,
    mainRegionNonBlank: true,
    realCardFound: true,
    firstCardMs: 800,
    canonicalOrigins: [...CANONICAL_ORIGINS],
    artifacts: [{ name: "t.png", path: "artifacts/t.png", sha256: DIGEST }],
  };

  it("fails when the browser landed on a non-canonical origin", () => {
    const verdict = evaluateJourney({ ...base, finalOrigin: "https://preview.bainluck.com" });
    assert.equal(verdict.assertions.find((a) => a.assertion_id === "route.final_origin_canonical").ok, false);
  });

  it("fails when no final origin could be resolved", () => {
    const verdict = evaluateJourney({ ...base, finalOrigin: null });
    assert.equal(verdict.assertions.find((a) => a.assertion_id === "route.final_origin_canonical").ok, false);
  });

  it("fails an unbounded redirect chain", () => {
    const verdict = evaluateJourney({
      ...base,
      finalOrigin: "https://www.bainluck.com",
      redirectChain: ["a", "b", "c", "d", "e"],
    });
    assert.equal(verdict.assertions.find((a) => a.assertion_id === "route.redirects_bounded").ok, false);
  });

  it("passes a canonical landing with no redirects", () => {
    const verdict = evaluateJourney({ ...base, finalOrigin: "https://www.bainluck.com" });
    assert.equal(verdict.result, "pass");
  });
});

// ---------------------------------------------------------------------------
// Item 2 — artifact truth and privacy containment.
// ---------------------------------------------------------------------------

describe("artifact path authority (string layer)", () => {
  const bad = [
    ["an absolute path", "/etc/passwd"],
    ["a traversal", "artifacts/../../etc/passwd"],
    ["a bare traversal", "../secrets.png"],
    ["a path outside the artifact root", "test-results/shot.png"],
    ["an unnormalized path", "artifacts/./shot.png"],
    ["a windows separator", "artifacts\\shot.png"],
    ["a drive letter", "C:/artifacts/shot.png"],
    ["a NUL byte", "artifacts/shot.png\u0000.txt"],
  ];
  for (const [label, value] of bad) {
    it(`rejects ${label}`, () => {
      assert.equal(checkArtifactPath(value, "a").ok, false, `${value} should be rejected`);
    });
  }

  it("accepts a normalized path under the artifact root", () => {
    const verdict = checkArtifactPath(`${ARTIFACT_ROOT}/discover.landing.desktop.terminal.png`, "a");
    assert.equal(verdict.ok, true);
  });

  it("rejects an artifact with a digest but no path — a digest alone is unfalsifiable", () => {
    rejects(
      manifest({ journeys: [journey({ artifacts: [{ name: "t.png", sha256: DIGEST, bytes: 10 }] })] }),
      "path is required"
    );
  });

  it("rejects a zero-byte artifact", () => {
    rejects(
      manifest({
        journeys: [journey({ artifacts: [{ name: "t.png", path: "artifacts/t.png", sha256: DIGEST, bytes: 0 }] })],
      }),
      "bytes must be a positive integer"
    );
  });

  it("rejects two artifacts claiming the same path inside one journey", () => {
    rejects(
      manifest({
        journeys: [
          journey({
            artifacts: [
              { name: "a.png", path: "artifacts/same.png", sha256: DIGEST, bytes: 10 },
              { name: "b.png", path: "artifacts/same.png", sha256: DIGEST, bytes: 10 },
            ],
          }),
        ],
      }),
      "claims the same artifact path twice"
    );
  });
});

describe("trace containment policy", () => {
  it("rejects a manifest that declares a Playwright trace", () => {
    // Scrubbing the manifest's JSON fields does nothing to a trace zip, which
    // carries request/response bodies, storage and cookie headers. Phase 1 has
    // no reviewed containment policy, so a declared trace is a policy
    // violation rather than a formatting error.
    rejects(
      manifest({
        journeys: [
          journey({
            artifacts: [
              { name: "terminal.png", path: "artifacts/terminal.png", sha256: DIGEST, bytes: 10 },
              { name: "trace.zip", path: "artifacts/trace.zip", sha256: DIGEST, bytes: 10 },
            ],
          }),
        ],
      }),
      "declares a Playwright trace"
    );
  });

  it("keeps tracing off at the config level", () => {
    const config = fs.readFileSync(path.join(__dirname, "..", "playwright.config.ts"), "utf8");
    assert.match(config, /trace:\s*"off"/, "phase 1 must not capture traces");
    assert.match(config, /video:\s*"off"/);
  });

  it("does not upload the raw playwright output directories", () => {
    const workflow = fs.readFileSync(
      path.join(__dirname, "..", "..", "..", ".github", "workflows", "browser-audit.yml"),
      "utf8"
    );
    const uploadBlock = workflow.slice(workflow.indexOf("upload-artifact"));
    assert.ok(!uploadBlock.includes("test-results/"), "test-results carries traces");
    assert.ok(!uploadBlock.includes("playwright-report/"), "the html report embeds attachments");
    assert.ok(uploadBlock.includes("frontend/e2e/audit-out/"), "the manifest tree must still be uploaded");
  });

  it("the collector no longer hashes a trace into the manifest", () => {
    const fixture = fs.readFileSync(path.join(__dirname, "..", "fixtures", "audit.ts"), "utf8");
    assert.ok(
      !/attachment\.name === "trace"/.test(fixture),
      "hashing the trace into the manifest re-declares it as evidence"
    );
  });
});

describe("artifact bytes are verified against disk", () => {
  /** Build a real temp tree so the filesystem paths are genuinely exercised. */
  function withTree(fn) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "bl-audit-"));
    try {
      fs.mkdirSync(path.join(root, ARTIFACT_ROOT), { recursive: true });
      return fn(root);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }

  function write(root, rel, contents) {
    const abs = path.join(root, rel);
    fs.writeFileSync(abs, contents);
    return { name: path.basename(rel), path: rel, sha256: sha256(contents), bytes: Buffer.byteLength(contents) };
  }

  it("verifies a real screenshot", () => {
    withTree((root) => {
      const artifact = write(root, `${ARTIFACT_ROOT}/shot.png`, "png-bytes");
      const verdict = verifyArtifactBytes(manifest({ journeys: [journey({ artifacts: [artifact] })] }), { root });
      assert.deepEqual(verdict.errors, []);
      assert.equal(verdict.verified, 1);
    });
  });

  it("rejects a FICTIONAL artifact that was never written", () => {
    // The pre-L2-223 hole: `{name, sha256}` with a plausible 64-hex digest and
    // no file anywhere validated. A fictional artifact is worse than none —
    // it reads as evidence in every downstream summary.
    withTree((root) => {
      const verdict = verifyArtifactBytes(manifest(), { root });
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /does not exist/);
    });
  });

  it("rejects an artifact deleted after the manifest was written", () => {
    withTree((root) => {
      const artifact = write(root, `${ARTIFACT_ROOT}/shot.png`, "png-bytes");
      fs.rmSync(path.join(root, artifact.path));
      const verdict = verifyArtifactBytes(manifest({ journeys: [journey({ artifacts: [artifact] })] }), { root });
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /does not exist/);
    });
  });

  it("rejects MUTATED bytes", () => {
    withTree((root) => {
      const artifact = write(root, `${ARTIFACT_ROOT}/shot.png`, "png-bytes");
      fs.writeFileSync(path.join(root, artifact.path), "different-bytes");
      const verdict = verifyArtifactBytes(manifest({ journeys: [journey({ artifacts: [artifact] })] }), { root });
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /sha256 mismatch/);
    });
  });

  it("rejects a byte-count that disagrees with the file", () => {
    withTree((root) => {
      const artifact = write(root, `${ARTIFACT_ROOT}/shot.png`, "png-bytes");
      const verdict = verifyArtifactBytes(
        manifest({ journeys: [journey({ artifacts: [{ ...artifact, bytes: 999999 }] })] }),
        { root }
      );
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /byte count mismatch/);
    });
  });

  it("rejects a SYMLINK — the bytes would not travel in the upload", () => {
    withTree((root) => {
      const target = path.join(root, "outside.png");
      fs.writeFileSync(target, "png-bytes");
      const rel = `${ARTIFACT_ROOT}/link.png`;
      try {
        fs.symlinkSync(target, path.join(root, rel));
      } catch {
        return; // a platform without symlink permission cannot regress this
      }
      const artifact = { name: "link.png", path: rel, sha256: sha256("png-bytes"), bytes: 9 };
      const verdict = verifyArtifactBytes(manifest({ journeys: [journey({ artifacts: [artifact] })] }), { root });
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /symlink/);
    });
  });

  it("rejects a traversal path before touching the filesystem", () => {
    withTree((root) => {
      const artifact = { name: "x", path: "artifacts/../../etc/passwd", sha256: DIGEST, bytes: 1 };
      const verdict = verifyArtifactBytes(manifest({ journeys: [journey({ artifacts: [artifact] })] }), { root });
      assert.equal(verdict.ok, false);
    });
  });

  it("rejects two journeys COLLIDING on one artifact path", () => {
    withTree((root) => {
      const artifact = write(root, `${ARTIFACT_ROOT}/shot.png`, "png-bytes");
      const verdict = verifyArtifactBytes(
        manifest({
          selectedCount: 2,
          journeys: [journey({ artifacts: [artifact] }), journey({ project: "mobile", artifacts: [artifact] })],
        }),
        { root }
      );
      assert.equal(verdict.ok, false);
      assert.match(verdict.errors.join("\n"), /already claimed by/);
    });
  });
});

// ---------------------------------------------------------------------------
// Item 1 — no dispatch value reaches shell syntax.
// ---------------------------------------------------------------------------

describe("workflow dispatch input safety", () => {
  const workflowPath = path.join(__dirname, "..", "..", "..", ".github", "workflows", "browser-audit.yml");
  const workflow = fs.readFileSync(workflowPath, "utf8");
  const runBlocks = [...workflow.matchAll(/run:\s*\|[\s\S]*?(?=\n {6}- |\n {6}\w+:|$)/g)].map((m) => m[0]);

  it("never expands a dispatch input inside a run block", () => {
    // `${{ }}` is substituted BEFORE the shell sees the line, so quoting does
    // not help: `$(( ${{ inputs.sha_timeout_seconds }} * 1000 ))` evaluated
    // arbitrary shell arithmetic chosen by whoever dispatched the run.
    for (const block of runBlocks) {
      const leaks = [...block.matchAll(/\$\{\{\s*inputs\.[a-z_]+\s*\}\}/g)].map((m) => m[0]);
      assert.deepEqual(leaks, [], `a dispatch input reaches shell syntax:\n${block}`);
    }
  });

  it("passes every dispatch input through the job env instead", () => {
    for (const name of ["pack", "frontend_sha", "base_url", "api_base_url"]) {
      assert.ok(
        new RegExp(`:\\s*\\$\\{\\{\\s*inputs\\.${name}\\s*\\}\\}`).test(workflow),
        `${name} must be bound to an env var`
      );
    }
  });

  it("validates the timeout as bounded digits before using it", () => {
    assert.match(workflow, /RAW_TIMEOUT.*grep -Eq '\^\[0-9\]\{1,4\}\$'/s);
    assert.match(workflow, /AUDIT_SHA_TIMEOUT_MS=\$\(\( RAW_TIMEOUT \* 1000 \)\)/);
    assert.match(workflow, /--timeout-ms "\$\{AUDIT_SHA_TIMEOUT_MS\}"/);
  });

  it("allowlists the audited origins in the workflow, not only in the validator", () => {
    assert.match(workflow, /https:\/\/www\.bainluck\.com\|https:\/\/bainluck\.com/);
    assert.match(workflow, /api_base_url must be https:\/\/api\.bainluck\.com/);
  });

  it("refuses to run outside the canonical repository", () => {
    assert.match(workflow, /GITHUB_REPOSITORY.*!=.*alexander-bain\/bainluck/s);
  });

  it("proves the audited commit is in the checkout's history", () => {
    assert.match(workflow, /fetch-depth:\s*0/, "merge-base needs full history");
    assert.match(workflow, /git merge-base --is-ancestor/);
    assert.match(workflow, /AUDIT_CHECKOUT_ANCESTRY=requested-is-ancestor-of-checkout/);
  });

  it("re-hashes artifacts in CI", () => {
    assert.match(workflow, /npm run validate -- .*--verify-bytes/);
  });
});

// ---------------------------------------------------------------------------
// Item 3 — the audit binds to stable hooks, not layout classes or copy.
// ---------------------------------------------------------------------------

describe("Discover audit hooks are state-based", () => {
  const repoRoot = path.join(__dirname, "..", "..", "..");
  const read = (...p) => fs.readFileSync(path.join(repoRoot, ...p), "utf8");
  const specs = ["discover-smoke.spec.ts", "discover-latency.spec.ts"];
  /**
   * Strip comments before matching. The explanation of WHY the old selector
   * was wrong necessarily quotes it, and losing that history to satisfy a
   * regex would be the wrong trade — the guard is about executable selectors.
   */
  const code = (raw) => raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  it("no spec selects a card by a Tailwind layout class", () => {
    // `break-inside-avoid` is shared with DiscoverSkeletonGrid, so a feed
    // stuck on skeletons satisfied "a real card was visible" and recorded a
    // first-card latency. That is the C96 [P1] false green, reintroduced
    // through the selector rather than the `.catch()`.
    for (const spec of specs) {
      const raw = read("frontend", "e2e", "specs", spec);
      assert.ok(!code(raw).includes("break-inside-avoid"), `${spec} still selects by layout class`);
      assert.ok(raw.includes('[data-testid="discover-card"]'), `${spec} must use the stable card hook`);
    }
  });

  it("no spec identifies the empty state by its copy", () => {
    for (const spec of specs) {
      const raw = code(read("frontend", "e2e", "specs", spec));
      assert.ok(
        !/getByText\(NAMED_EMPTY/.test(raw) && !raw.includes('const NAMED_EMPTY = "You'),
        `${spec} still matches editable copy`
      );
      assert.ok(raw.includes('[data-testid="discover-empty-state"]'));
    }
  });

  it("the smoke journey fails a still-mounted skeleton", () => {
    const raw = read("frontend", "e2e", "specs", "discover-smoke.spec.ts");
    assert.ok(raw.includes('[data-testid="discover-skeleton"]'));
    assert.match(raw, /skeletonVisible/);
  });

  it("the components actually render the hooks the specs look for", () => {
    const page = read("frontend", "app", "discover", "page.tsx");
    assert.ok(page.includes('data-testid="discover-card"'), "the feed item wrapper needs the card hook");
    assert.ok(page.includes('data-testid="discover-feed-error"'), "the error state needs its own hook");

    const empty = read("frontend", "components", "discover", "EndOfFeedCard.tsx");
    assert.ok(empty.includes('data-testid="discover-empty-state"'));
    assert.ok(empty.includes("data-empty-state-name"), "the state name must be data, not scraped prose");

    const skeleton = read("frontend", "components", "discover", "DiscoverSkeletonGrid.tsx");
    assert.ok(skeleton.includes('data-testid="discover-skeleton"'));
    assert.ok(
      !skeleton.includes('data-testid="discover-card"'),
      "the skeleton must never carry the card hook — that is the whole point"
    );
  });
});
