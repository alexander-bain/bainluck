"use strict";

/**
 * UX-P029 Item 2 — the privilege split is the security property, so it is pinned.
 *
 * The runner drives a browser against the live site. The filer writes to the
 * issue tracker. Those two capabilities must never sit in the same job: a browser
 * run that could also file is one bug away from writing to the board on behalf of
 * whatever the page did. Phase 1 kept them apart by having no filer at all;
 * phase 2 keeps them apart on purpose, and this file is what makes that
 * deliberate rather than incidental.
 */

const fs = require("node:fs");
const path = require("node:path");
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const repoRoot = path.join(__dirname, "..", "..", "..");
const workflows = path.join(repoRoot, ".github", "workflows");

const stripComments = (raw) =>
  raw
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");

const runnerRaw = fs.readFileSync(path.join(workflows, "browser-audit.yml"), "utf8");
const filerRaw = fs.readFileSync(path.join(workflows, "browser-audit-filer.yml"), "utf8");
const runner = stripComments(runnerRaw);
const filer = stripComments(filerRaw);

describe("the browser rail keeps filing OUT of the browser job", () => {
  it("neither stripped config is vacuous", () => {
    assert.ok(runner.includes("jobs:") && runner.length > 500);
    assert.ok(filer.includes("jobs:") && filer.length > 300);
  });

  it("the runner still holds read-only scope after gaining a schedule", () => {
    assert.match(runner, /permissions:\s*\n\s*contents:\s*read\s*\n/);
    assert.ok(!runner.includes("issues: write"), "the browser job must never file");
    assert.ok(!runner.includes("contents: write"));
    assert.ok(!runner.includes("gh issue"), "the browser job must not touch the tracker at all");
  });

  it("the filer is a SEPARATE workflow, triggered by the runner finishing", () => {
    assert.match(filer, /workflow_run:/);
    assert.match(filer, /workflows:\s*\["Browser audit"\]/);
    assert.match(filer, /types:\s*\[completed\]/);
    // The name it listens for must be the runner's actual name, or it never runs.
    assert.match(runnerRaw, /^name:\s*Browser audit\s*$/m);
  });

  it("the filer takes issues:write and nothing wider", () => {
    assert.ok(filer.includes("issues: write"));
    assert.ok(!filer.includes("contents: write"), "the filer must not be able to push code");
    assert.ok(!filer.includes("packages: write"));
    assert.ok(!filer.includes("id-token: write"));
  });

  it("the filer never runs a browser", () => {
    // If it did, the split would be cosmetic.
    assert.ok(!filer.includes("playwright"));
    assert.ok(!filer.includes("npm run smoke"));
  });

  it("the filer does not cancel itself mid-write", () => {
    assert.match(filer, /cancel-in-progress:\s*false/);
  });

  it("the consumer the filer runs exists and delegates every judgement", () => {
    const consumer = path.join(repoRoot, "frontend", "e2e", "scripts", "file-sweep-findings.js");
    assert.ok(filer.includes("scripts/file-sweep-findings.js"));
    assert.ok(fs.existsSync(consumer));

    const src = fs.readFileSync(consumer, "utf8");
    assert.match(src, /require\("\.\.\/helpers\/sweepFiling"\)/, "decisions must come from the pure layer");
    assert.match(src, /decide\(/);
    // A missing manifest must refuse, never read as "all clear".
    assert.match(src, /no manifest found/i);
    assert.match(src, /dedup state unknown/i);
  });
});
