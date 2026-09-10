// Vercel ignored-build-step contract (#4456).
//
// ~20 Vercel deploys/hour, 17 of them PREVIEW builds nobody reads (previews are
// auth-gated, so every lane already shoots production for its LOOK, notice 4).
// `vercel-ignore-build.sh` skips those.
//
// VERCEL'S CONTRACT IS INVERTED, which is the whole reason this file exists:
//
//     exit 0  ->  SKIP the build
//     exit 1  ->  PROCEED with the build
//
// Get that backwards and the failure is not a wasted build, it is that MASTER
// STOPS DEPLOYING and the site quietly freezes at whatever was last shipped.
// The asymmetry is the same one `heroku-release-required.sh` is written around:
//
//   * wrongly SKIP a production build => the site silently stops updating.
//   * wrongly RUN a preview build     => one wasted build. Cheap.
//
// So the invariant is not "the script is clever", it is: the script only ever
// skips when it has positively identified a disposable lane preview, and builds
// in every other circumstance INCLUDING every unknown.
//
// This suite RUNS the real script with real environments rather than asserting
// on its text — CERT-2423 landed on the Heroku half precisely because a
// correct-READING script had an incorrect BEHAVIOUR. The Vercel half was graded
// as holding; this table is what stops it drifting.

const { test, describe } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRIPT = path.join(REPO_ROOT, "frontend", "scripts", "vercel-ignore-build.sh");
const VERCEL_JSON = path.join(REPO_ROOT, "frontend", "vercel.json");

const BUILD = "BUILD";
const SKIP = "SKIP";

/**
 * Run the real hook under `env` and translate Vercel's inverted exit code into
 * a word, so an assertion that reads "BUILD" cannot silently mean exit 0.
 */
function decide(env) {
  const res = spawnSync("bash", [SCRIPT], {
    // A bare environment: only what the case declares is visible, so a case can
    // never pass by inheriting VERCEL_* from the machine running the suite.
    env: { PATH: process.env.PATH, ...env },
    encoding: "utf8",
  });
  assert.strictEqual(res.error, undefined, `script failed to run: ${res.error}`);
  if (res.status === 0) return SKIP;
  if (res.status === 1) return BUILD;
  throw new Error(
    `script exited ${res.status}, which is neither SKIP (0) nor BUILD (1): ${res.stderr}`
  );
}

// The six cases, as one table so a future edit has to change a ROW rather than
// quietly lose a branch. `why` is the fail-safe claim each row is defending.
const DECISION_TABLE = [
  {
    name: "1. the production deployment always builds",
    env: { VERCEL_ENV: "production", VERCEL_GIT_COMMIT_REF: "master" },
    expect: BUILD,
    why: "the load-bearing guard: if all else were wrong, the site still deploys",
  },
  {
    name: "2. master builds even when Vercel does not call it production",
    env: { VERCEL_ENV: "preview", VERCEL_GIT_COMMIT_REF: "master" },
    expect: BUILD,
    why: "belt and braces if the project's production branch is reconfigured",
  },
  {
    name: "3. a lane branch opts in with 'wants-preview' in the commit message",
    env: {
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "program/ux-1165-something",
      VERCEL_GIT_COMMIT_MESSAGE: "fix(#4483): a thing [wants-preview]",
    },
    expect: BUILD,
    why: "the escape hatch has to actually work or lanes lose previews for good",
  },
  {
    name: "4. an unidentifiable branch builds rather than guessing",
    env: { VERCEL_ENV: "preview", VERCEL_GIT_COMMIT_REF: "" },
    expect: BUILD,
    why: "an empty ref is not proof of disposability",
  },
  {
    name: "5. a lane branch with no opt-in is the ONE case that skips",
    env: {
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "program/ux-1165-something",
      VERCEL_GIT_COMMIT_MESSAGE: "fix(#4483): a thing",
    },
    expect: SKIP,
    why: "this row is the entire saving; if it flips to BUILD nothing is saved",
  },
  {
    name: "6. a bare environment — nothing set at all — builds",
    env: {},
    expect: BUILD,
    why: "a missing env var must never be the reason master stopped deploying",
  },
];

describe("#4456 — a lane push does not build a Vercel preview", () => {
  test("the decision lives in a FILE that vercel.json actually invokes", () => {
    assert.ok(fs.existsSync(SCRIPT), "vercel-ignore-build.sh must exist");
    const cfg = JSON.parse(fs.readFileSync(VERCEL_JSON, "utf8"));
    assert.strictEqual(
      cfg.ignoreCommand,
      "bash scripts/vercel-ignore-build.sh",
      "vercel.json must invoke the script, or this whole suite grades nothing"
    );
  });

  for (const row of DECISION_TABLE) {
    test(row.name, () => {
      assert.strictEqual(decide(row.env), row.expect, row.why);
    });
  }

  test("the table is not vacuous — the script can say both words", () => {
    // Hard-coding `exit 1` would pass five of the six rows above while
    // disabling the feature; hard-coding `exit 0` would stop master deploying.
    const seen = new Set(DECISION_TABLE.map((r) => decide(r.env)));
    assert.deepStrictEqual([...seen].sort(), [BUILD, SKIP]);
  });

  test("the skip case is reached by BRANCH, not by the commit message alone", () => {
    // A message-only rule would skip master builds whose message happens to
    // lack the opt-in — i.e. all of them.
    assert.strictEqual(
      decide({
        VERCEL_ENV: "preview",
        VERCEL_GIT_COMMIT_REF: "master",
        VERCEL_GIT_COMMIT_MESSAGE: "no opt-in here",
      }),
      BUILD
    );
  });
});
