"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");

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

describe("#12858: only a completed compiler run can be counted", () => {
  const diagnostic = "app/page.tsx(1,1): error TS2322: fixture type error.\n";
  const empty = { total: 0, byFile: {}, byCode: {} };
  const one = { total: 1, byFile: { "app/page.tsx": 1 }, byCode: { TS2322: 1 } };

  function run(t, compiler, { mode = "--check", baseline = one } = {}) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "bainluck-tsc-process-"));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    fs.mkdirSync(path.join(root, "scripts"));
    fs.mkdirSync(path.join(root, "node_modules/typescript/bin"), { recursive: true });
    fs.copyFileSync(path.join(REPO_ROOT, "frontend/scripts/tsc-census.js"), path.join(root, "scripts/tsc-census.js"));
    const baselinePath = path.join(root, "typecheck-baseline.json");
    const before = JSON.stringify({ _meta: { owner: "fixture" }, ...baseline }) + "\n";
    fs.writeFileSync(baselinePath, before);
    const invocations = path.join(root, "invocations");
    fs.writeFileSync(path.join(root, "node_modules/typescript/bin/tsc"),
      `require('node:fs').appendFileSync(${JSON.stringify(invocations)}, 'run\\n');\n${compiler}\n`);
    const result = spawnSync(process.execPath, [path.join(root, "scripts/tsc-census.js"), "--run", mode], {
      encoding: "utf8", timeout: 10000,
    });
    assert.equal(result.error, undefined);
    assert.equal(result.signal, null);
    assert.equal(fs.readFileSync(invocations, "utf8"), "run\n", "one invocation; never retry the compiler");
    return { ...result, before, after: fs.readFileSync(baselinePath, "utf8") };
  }

  it("accepts a successful clean compiler with a zero baseline", (t) => {
    assert.equal(run(t, "process.exitCode = 0;", { baseline: empty }).status, 0);
  });

  for (const status of [1, 2]) {
    it(`accepts completed diagnostic exit ${status} when the baseline matches`, (t) => {
      const result = run(t, `require('node:fs').writeSync(1, ${JSON.stringify(diagnostic)}); process.exitCode = ${status};`);
      assert.equal(result.status, 0);
      assert.match(result.stdout, /typecheck errors: 1 \(baseline 1\)/);
    });
  }

  for (const mode of ["--check", "--write-baseline", "--census"]) {
    it(`refuses a killed compiler before ${mode} can report a census`, (t) => {
      const result = run(t, "process.kill(process.pid, 'SIGKILL');", { mode });
      assert.equal(result.status, 2);
      assert.match(result.stderr, /SIGKILL/);
      assert.doesNotMatch(result.stdout, /typecheck errors:|total errors:|wrote .*errors/);
      assert.equal(result.after, result.before);
    });
  }

  it("refuses a partial matching census if the compiler then dies", (t) => {
    const result = run(t, `require('node:fs').writeSync(1, ${JSON.stringify(diagnostic)}); process.kill(process.pid, 'SIGKILL');`);
    assert.equal(result.status, 2);
    assert.match(result.stderr, /SIGKILL/);
    assert.match(result.stderr, /TS2322/);
  });

  it("reports a fatal compiler exit with its original stderr", (t) => {
    const result = run(t, "require('node:fs').writeSync(2, 'fixture compiler failure\\n'); process.exitCode = 3;");
    assert.equal(result.status, 2);
    assert.match(result.stderr, /status=3/);
    assert.match(result.stderr, /fixture compiler failure/);
  });

  it("refuses a diagnostic exit with no countable output", (t) => {
    const result = run(t, "process.exitCode = 2;", { baseline: empty });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /no countable diagnostics/);
  });

  it("cannot hide a global configuration error behind matching file counts", (t) => {
    const output = diagnostic + "error TS6046: Invalid compiler option.\n";
    const result = run(t, `require('node:fs').writeSync(1, ${JSON.stringify(output)}); process.exitCode = 2;`);
    assert.equal(result.status, 2);
    assert.match(result.stderr, /TS6046/);
  });
});
