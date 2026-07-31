"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

/**
 * L2-221 Item 1 — reproducibility and blast-radius contract (C96 [P2]).
 *
 * The old tree carried `"@playwright/test": "^1.48.0"` with `package-lock.json`
 * in `.gitignore`. Two runs could therefore use different runners and browser
 * revisions while claiming to prove the same commit.
 *
 * `npm ci` is the enforcing gate for the lockfile itself — it exits non-zero
 * when the lock is missing or disagrees with package.json, and the workflow
 * uses nothing else. What `npm ci` CANNOT catch is a future edit that
 * reintroduces a range specifier, un-isolates the tree from the Vercel build,
 * or quietly widens the workflow's permissions. That is what this file guards.
 */

const e2eRoot = path.join(__dirname, "..");
const repoRoot = path.join(e2eRoot, "..", "..");

const pkg = JSON.parse(fs.readFileSync(path.join(e2eRoot, "package.json"), "utf8"));

/** Anything that is not a single exact version. */
const RANGE_SPECIFIER = /^[\^~>< ]|[*x]$|\s-\s|\|\|/;

describe("dependency pinning", () => {
  it("pins every dependency to an exact version", () => {
    const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
    assert.ok(Object.keys(deps).length > 0, "expected at least one dependency");
    for (const [name, range] of Object.entries(deps)) {
      assert.equal(
        RANGE_SPECIFIER.test(String(range)),
        false,
        `${name} must be pinned exactly, got "${range}" — a range lets two runs use different browsers`
      );
    }
  });

  it("uses @playwright/test, pinned", () => {
    const version = (pkg.devDependencies || {})["@playwright/test"];
    assert.ok(version, "@playwright/test must be a devDependency");
    assert.match(version, /^\d+\.\d+\.\d+$/);
  });

  it("no longer ignores the lockfile", () => {
    const entries = fs
      .readFileSync(path.join(e2eRoot, ".gitignore"), "utf8")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    assert.ok(
      !entries.includes("package-lock.json"),
      "package-lock.json must be committed so `npm ci` can pin the runner"
    );
  });
});

describe("isolation from the Vercel build", () => {
  it("the main frontend tsconfig still excludes e2e", () => {
    // Without this, the audit tree enters `next build` and the deploy path.
    const mainTsconfig = JSON.parse(
      fs.readFileSync(path.join(repoRoot, "frontend", "tsconfig.json"), "utf8")
    );
    assert.ok(
      (mainTsconfig.exclude || []).includes("e2e"),
      "frontend/tsconfig.json must exclude e2e"
    );
  });

  it("the audit tree declares its own package identity", () => {
    assert.equal(pkg.private, true);
    assert.notEqual(pkg.name, "bainluck-frontend");
  });
});

describe("the manual workflow keeps its phase-1 boundary", () => {
  const workflowPath = path.join(repoRoot, ".github", "workflows", "browser-audit.yml");
  const raw = fs.readFileSync(workflowPath, "utf8");

  /**
   * Strip `#` comment lines before asserting on content.
   *
   * Learned the hard way in this very file: the first version of these
   * assertions tripped on the workflow's OWN comments, which explain that it
   * uses `npm ci` and never `npm install`, and that `issues: write` belongs to
   * a later job. A prose mention is not a configured behaviour, so the
   * assertions must read the configuration.
   */
  const config = raw
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");

  it("the comment-stripped config is not vacuous", () => {
    // Guard: if stripping ever eats the file, every `!includes` below would
    // pass for the wrong reason.
    assert.ok(config.includes("jobs:"), "stripped config lost its jobs block");
    assert.ok(config.length > 500, `stripped config is suspiciously short (${config.length})`);
  });

  it("is dispatch-only — no schedule in phase 1", () => {
    assert.ok(config.includes("workflow_dispatch:"));
    assert.ok(!/^\s{2}schedule:/m.test(config), "phase 1 must not carry a schedule trigger");
  });

  it("installs a browser with its OS dependencies", () => {
    assert.ok(config.includes("playwright install --with-deps chromium"));
  });

  it("installs with npm ci — the lockfile gate — and never npm install", () => {
    assert.ok(config.includes("npm ci"));
    assert.ok(
      !/\bnpm install\b/.test(config),
      "npm install would defeat the lockfile gate"
    );
  });

  it("holds least privilege: no write scope, no issue filing", () => {
    assert.ok(config.includes("contents: read"));
    assert.ok(!config.includes("issues: write"));
    assert.ok(!config.includes("contents: write"));
    assert.ok(!config.includes("gh issue create"));
  });

  it("always uploads artifacts, and does not swallow the upload's failure", () => {
    assert.ok(config.includes("if: always()"));
    assert.ok(
      !config.includes("continue-on-error: true"),
      "a swallowed step can turn a no-evidence run green"
    );
    assert.ok(config.includes("if-no-files-found: error"));
  });

  it("validates the manifest before it can be called green", () => {
    assert.ok(config.includes("npm run validate"));
  });

  it("pins the Node major the repo builds with", () => {
    assert.match(config, /node-version:\s*["']?20/);
  });

  it("carries no production secret", () => {
    assert.ok(!/secrets\./.test(config), "phase 1 runs anonymously, with no secret");
  });
});
