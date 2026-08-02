"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * L2-233 — the frontend unit suite must stay on the deploy path.
 *
 * ## The circularity this exists to break
 *
 * `frontend/__tests__/lib/ciJestGate.test.ts` holds most of the invariants that
 * keep the jest gate honest, and it is the right place for them: they only
 * matter when jest is running, and it can assert things about the live process
 * that no static check can.
 *
 * But it cannot guard its own existence. Delete the `npm run test:ci` step from
 * `ci.yml` and that whole file stops executing — silently, on a green build,
 * because every other job still passes. The 1,393 tests would go back to being
 * laptop-only and nothing would say so.
 *
 * So the one assertion that has to survive jest not running lives here instead,
 * in the dependency-free `node --test` suite that `ci.yml` runs as
 * `e2e-contract` and that `deploy: needs:` already lists. No install, no
 * network, nothing to skip — which is exactly why the browser rail's fixtures
 * live here too.
 *
 * ## What it asserts
 *
 * Only the wiring: jest is invoked in a job, that job installs from the
 * lockfile first, and deploy authority depends on that job. Everything about
 * HOW jest runs (flags, collection, focus, the network guard) is the jest-side
 * file's job — duplicating it here would mean two copies to keep in step for no
 * additional coverage.
 *
 * The workflow is read as text and matched by indentation rather than parsed:
 * this runner has no dependencies by design, and the shape is two levels deep
 * and stable. A renamed job throws with the rename named, so a silent no-op is
 * not one of the outcomes.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    assert.fail(
      `L2-233 jest-gate fixture could not read ${path.relative(REPO_ROOT, file)}: ` +
        `${err.message}. If the file moved, update this fixture — do not delete the check.`,
    );
  }
}

/**
 * Drop whole-line YAML comments before any text assertion.
 *
 * Found by this fixture on its first run: the step added in L2-233 carries a
 * comment saying it must never gain a `continue-on-error`, and the naive scan
 * matched that sentence and failed. A guard that reads prose as configuration
 * is a guard that fires on documentation — including documentation of itself.
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
      "fixture and frontend/__tests__/lib/ciJestGate.test.ts together.",
  );
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return stripComments(rest.slice(0, end).join("\n"));
}

describe("L2-233: jest is on the deploy path", () => {
  const ci = read(CI_YML);

  it("frontend-build invokes the unit suite", () => {
    const block = jobBlock(ci, "frontend-build");
    assert.ok(
      block.includes("npm run test:ci"),
      "frontend-build no longer runs `npm run test:ci`. The 1,393-test frontend suite " +
        "is off the deploy path again — that is the exact defect L2-233 fixed.",
    );
  });

  it("it runs after the lockfile install, so jest is actually present", () => {
    const block = jobBlock(ci, "frontend-build");
    const install = block.indexOf("npm ci");
    const test = block.indexOf("npm run test:ci");
    assert.ok(install >= 0, "frontend-build no longer installs from the lockfile");
    assert.ok(
      test > install,
      "`npm run test:ci` runs before `npm ci`, so jest is not installed yet",
    );
  });

  it("deploy authority depends on that job", () => {
    const deploy = jobBlock(ci, "deploy");
    const needs = /needs:\s*\[([^\]]*)\]/.exec(deploy);
    assert.ok(needs, "the deploy job no longer declares `needs: [...]`");
    const named = needs[1].split(",").map((s) => s.trim());
    assert.ok(
      named.includes("frontend-build"),
      `deploy no longer needs frontend-build (needs: ${named.join(", ")}), so a red ` +
        "frontend suite would not stop a Heroku release.",
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
});
