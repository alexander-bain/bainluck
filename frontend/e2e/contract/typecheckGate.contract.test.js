"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * L2-234 — `tsc --noEmit` must stay on the deploy path.
 *
 * ## The circularity this exists to break
 *
 * `frontend/__tests__/lib/ciTypecheckGate.test.ts` holds most of the invariants
 * that keep the typecheck gate honest, and that is the right home for them:
 * they only matter when the gate is running, and it can exercise the census
 * tool directly in-process.
 *
 * But it cannot guard its own existence. Delete the `npm run typecheck` step
 * from `ci.yml` and that file still runs — jest is a separate step — yet the
 * thing it guards is gone, and every subsequent build is green over an
 * unchecked codebase. Worse, deleting the jest step too would take both with
 * it, silently.
 *
 * So the assertions that must survive both of those live here, in the
 * dependency-free `node --test` suite that `ci.yml` runs as `e2e-contract` and
 * that `deploy: needs:` already lists. No install, no network, nothing to skip.
 *
 * ## What it asserts
 *
 * Only the wiring and the existence of the baseline: the typecheck is invoked,
 * in a job deploy depends on, after the build that generates the route types it
 * reads, and the file recording the frozen debt is present and parses.
 * Everything about HOW the census behaves is the jest-side file's job.
 *
 * The workflow is read as text and matched by indentation rather than parsed:
 * this runner has no dependencies by design. A renamed job throws with the
 * rename named, so a silent no-op is not one of the outcomes.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");
const BASELINE = path.join(REPO_ROOT, "frontend", "typecheck-baseline.json");

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    assert.fail(
      `L2-234 typecheck-gate fixture could not read ${path.relative(REPO_ROOT, file)}: ` +
        `${err.message}. If the file moved, update this fixture — do not delete the check.`,
    );
  }
}

/**
 * Drop whole-line YAML comments before any text assertion. Both of L2-233's
 * guards failed on their own first run by matching their own prose about the
 * flags they forbid; the step this fixture guards carries the same kind of
 * comment.
 */
function stripComments(text) {
  return text
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");
}

function jobBlock(yaml, jobName) {
  const lines = yaml.split("\n");
  const start = lines.indexOf(`  ${jobName}:`);
  assert.notEqual(
    start,
    -1,
    `ci.yml has no top-level job named "${jobName}". If it was renamed, update this ` +
      "fixture and frontend/__tests__/lib/ciTypecheckGate.test.ts together.",
  );
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return stripComments(rest.slice(0, end).join("\n"));
}

describe("L2-234: the typecheck is on the deploy path", () => {
  const ci = read(CI_YML);

  it("frontend-build runs the typecheck", () => {
    const block = jobBlock(ci, "frontend-build");
    assert.ok(
      block.includes("npm run typecheck"),
      "frontend-build no longer runs `npm run typecheck`. TypeScript is unenforced " +
        "again — next.config.mjs sets ignoreBuildErrors:true, so `npm run build` " +
        "will not catch it (gotcha #10). That is the exact defect L2-234 fixed.",
    );
  });

  it("it runs the checking script, not the one that rewrites the baseline", () => {
    const block = jobBlock(ci, "frontend-build");
    assert.ok(
      !block.includes("typecheck:baseline"),
      "frontend-build runs `typecheck:baseline`, which REWRITES the recorded debt " +
        "to match whatever the tree currently produces. That is a gate that passes " +
        "by definition.",
    );
  });

  it("it runs after the build, so generated route types exist", () => {
    const block = jobBlock(ci, "frontend-build");
    const build = block.indexOf("npm run build");
    const typecheck = block.indexOf("npm run typecheck");
    assert.ok(build >= 0, "frontend-build no longer runs the build");
    assert.ok(
      typecheck > build,
      "`npm run typecheck` runs before `npm run build`, so `.next/types/**` does " +
        "not exist yet and CI checks a smaller program than a developer does.",
    );
  });

  it("deploy authority depends on that job", () => {
    const deploy = jobBlock(ci, "deploy");
    const needs = /needs:\s*\[([^\]]*)\]/.exec(deploy);
    assert.ok(needs, "the deploy job no longer declares `needs: [...]`");
    const named = needs[1].split(",").map((s) => s.trim());
    assert.ok(
      named.includes("frontend-build"),
      `deploy no longer needs frontend-build (needs: ${named.join(", ")}), so a new ` +
        "type error would not stop a Heroku release.",
    );
  });

  it("no step in frontend-build is allowed to fail quietly", () => {
    const block = jobBlock(ci, "frontend-build");
    assert.ok(
      !/continue-on-error/.test(block),
      "a `continue-on-error` appeared in frontend-build — that turns the gate into " +
        "decoration while leaving every visible line of it in place.",
    );
  });

  it("the recorded debt exists, parses, and names an owner", () => {
    // Without this file the gate cannot run at all; with an unowned one, the
    // 89 frozen errors are a number nobody is accountable for.
    const baseline = JSON.parse(read(BASELINE));
    assert.equal(typeof baseline.total, "number", "typecheck-baseline.json has no total");
    assert.ok(baseline.byFile, "typecheck-baseline.json has no per-file counts");
    assert.match(
      String(baseline._meta && baseline._meta.owner),
      /github\.com\/.+\/issues\/\d+/,
      "typecheck-baseline.json._meta.owner must point at the issue that owns the debt",
    );
  });
});
