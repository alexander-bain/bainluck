// Heroku release-required contract (#4456).
//
// Every master merge used to cycle the Heroku dynos, and a dyno cycle kills
// whatever the workers are mid-way through — the matcher, and the ~2h
// calibration rebuild that has been killed repeatedly at ~110/128 by a release
// landing under it. `release-required` makes a frontend-only merge cost the
// backend nothing.
//
// That decision is a DEPLOY GATE, so the way it fails matters more than the way
// it succeeds:
//
//   * decide "false" when it should be "true" => production silently sits behind
//     master, with certified ships undeployed. Nobody notices for hours. This is
//     the #3171 failure mode, and it is the one this suite mostly guards.
//   * decide "true" when it could be "false" => one redundant dyno cycle. Cheap.
//
// So the invariant under test is NOT "the script is clever". It is:
//
//     the script only ever says "false" when it has positively proved
//     every changed path is one Heroku cannot serve — and says "true"
//     in every other circumstance, including its own failures.
//
// Following deployGuard.contract.test.js (#3171): a text assertion would not
// catch this, because the wrong version's text also reads correctly. This suite
// RUNS the real script against real throwaway git repositories. It is
// dependency-free (`node --test`) and lives in the e2e-contract job that
// `deploy: needs:` already lists, so it cannot be skipped on the way to a
// release.

const { test, describe } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRIPT = path.join(REPO_ROOT, ".github", "scripts", "heroku-release-required.sh");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

/** Build a throwaway repo whose HEAD commit touches exactly `files`. */
function repoWithChange(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rel-required-"));
  git(dir, "init", "-q", "-b", "main");
  git(dir, "config", "user.email", "t@t.t");
  git(dir, "config", "user.name", "t");
  // A base commit so there is something to diff against.
  fs.writeFileSync(path.join(dir, "seed.txt"), "seed\n");
  git(dir, "add", "-A");
  git(dir, "commit", "-qm", "seed");
  const before = git(dir, "rev-parse", "HEAD").trim();

  for (const f of files) {
    const full = path.join(dir, f);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, "x\n");
  }
  git(dir, "add", "-A");
  git(dir, "commit", "-qm", "change");
  const after = git(dir, "rev-parse", "HEAD").trim();
  return { dir, before, after };
}

/** Run the real script; return its stdout verdict. */
function decide(dir, before, after) {
  const out = execFileSync("bash", [SCRIPT, before, after], {
    cwd: dir,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return out.trim();
}

function verdictFor(files) {
  const { dir, before, after } = repoWithChange(files);
  try {
    return decide(dir, before, after);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Build a throwaway repo whose HEAD commit MOVES `from` to `to`.
 *
 * A move is its own case because git reports it differently from an
 * add+delete: with rename detection on (the default), `--name-only` prints
 * only the destination, so the vanishing source path is invisible.
 */
function repoWithRename(from, to) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rel-required-mv-"));
  git(dir, "init", "-q", "-b", "main");
  git(dir, "config", "user.email", "t@t.t");
  git(dir, "config", "user.name", "t");
  const src = path.join(dir, from);
  fs.mkdirSync(path.dirname(src), { recursive: true });
  // Enough content that this is unambiguously one file moving, not two
  // coincidentally-similar tiny files.
  fs.writeFileSync(src, Array.from({ length: 40 }, (_, i) => `line ${i}\n`).join(""));
  git(dir, "add", "-A");
  git(dir, "commit", "-qm", "seed");
  const before = git(dir, "rev-parse", "HEAD").trim();

  const dst = path.join(dir, to);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  git(dir, "mv", from, to);
  git(dir, "add", "-A");
  git(dir, "commit", "-qm", "move");
  const after = git(dir, "rev-parse", "HEAD").trim();
  return { dir, before, after };
}

function verdictForRename(from, to) {
  const { dir, before, after } = repoWithRename(from, to);
  try {
    return decide(dir, before, after);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

describe("#4456 — a frontend-only merge does not cycle the Heroku dynos", () => {
  test("the decision lives in a FILE, so this suite can execute it", () => {
    // The #3171 lesson: a guard inlined in ci.yml is unreachable by every gate
    // we own. If someone moves this logic back into the workflow, fail here.
    assert.ok(fs.existsSync(SCRIPT), "heroku-release-required.sh must exist");
    const yml = fs.readFileSync(CI_YML, "utf8");
    assert.ok(
      yml.includes(".github/scripts/heroku-release-required.sh"),
      "ci.yml must invoke the script, not re-implement the decision inline"
    );
  });

  test("a genuinely frontend-only change skips the release", () => {
    assert.strictEqual(
      verdictFor(["frontend/components/Foo.tsx", "frontend/__tests__/foo.test.tsx"]),
      "false"
    );
  });

  test("docs, tools, ios and handoff-only changes skip the release", () => {
    assert.strictEqual(verdictFor(["docs/whatever.md"]), "false");
    assert.strictEqual(verdictFor(["tools/look.sh"]), "false");
    assert.strictEqual(verdictFor(["ios/Bain Luck/Thing.swift"]), "false");
    assert.strictEqual(verdictFor([".claude/handoff/NOTE.md"]), "false");
    assert.strictEqual(verdictFor(["README.md"]), "false");
  });

  // ---- the load-bearing direction: these MUST release --------------------
  test("THE LOAD-BEARING ONE — any backend file forces a release", () => {
    assert.strictEqual(verdictFor(["backend/app/routes/feed.py"]), "true");
  });

  test("a backend file mixed in with frontend files still forces a release", () => {
    // The realistic regression: a big frontend batch with one backend file in it.
    assert.strictEqual(
      verdictFor([
        "frontend/components/Foo.tsx",
        "frontend/lib/bar.ts",
        "backend/app/utils/discover_bundles.py",
      ]),
      "true"
    );
  });

  test("deploy-shaped files outside backend/ still force a release", () => {
    // These change what the dyno runs without living under backend/.
    for (const f of [
      "Procfile",
      "requirements.txt",
      "runtime.txt",
      "app.json",
      ".github/workflows/ci.yml",
    ]) {
      assert.strictEqual(verdictFor([f]), "true", `${f} must force a release`);
    }
  });

  // ---- moves: the source path must not disappear from the decision -------
  test("THE RENAME ONE — moving a file OUT of backend/ still forces a release", () => {
    // CERT-2423's BLOCK. Rename detection is on by default and prints only the
    // DESTINATION for a detected rename, so `backend/app/served.py` ->
    // `frontend/app/served.py` reported as the single path
    // `frontend/app/served.py`: every path read frontend-only and the script
    // said "false", silently skipping a release production needed. The deleted
    // backend file is exactly the thing that changes what the dynos serve.
    assert.strictEqual(
      verdictForRename("backend/app/served.py", "frontend/app/served.py"),
      "true"
    );
    // Same shape for the other safe roots, so the fix is not a one-path patch.
    assert.strictEqual(verdictForRename("backend/app/thing.py", "docs/thing.py"), "true");
    assert.strictEqual(verdictForRename("Procfile", "docs/Procfile"), "true");
  });

  test("moving a file INTO backend/ forces a release", () => {
    assert.strictEqual(
      verdictForRename("frontend/lib/calc.ts", "backend/app/calc.ts"),
      "true"
    );
  });

  test("NEGATIVE CONTROL — a move that stays inside safe roots still skips", () => {
    // Without this, "return true on any rename" would pass every assertion
    // above while disabling the feature for the frontend refactors it exists
    // to serve.
    assert.strictEqual(
      verdictForRename("frontend/components/Old.tsx", "frontend/components/New.tsx"),
      "false"
    );
    assert.strictEqual(verdictForRename("docs/a.md", "tools/a.md"), "false");
  });

  test("a path that merely STARTS like a safe one is not safe", () => {
    // "frontend-tools/" is not "frontend/". A prefix match without the slash
    // would wave this through.
    assert.strictEqual(verdictFor(["frontendish/thing.py"]), "true");
    assert.strictEqual(verdictFor(["backend/docs/notes.md"]), "true");
  });

  // ---- fail-safe: every uncertainty releases -----------------------------
  test("an unusable base commit releases rather than guessing", () => {
    const { dir, after } = repoWithChange(["frontend/x.tsx"]);
    try {
      assert.strictEqual(decide(dir, "0".repeat(40), after), "true", "zero base");
      assert.strictEqual(decide(dir, "", after), "true", "empty base");
      assert.strictEqual(decide(dir, "deadbeef".repeat(5), after), "true", "absent base");
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  test("an empty diff releases — 'nothing changed' is not proof of frontend-only", () => {
    const { dir, after } = repoWithChange(["frontend/x.tsx"]);
    try {
      assert.strictEqual(decide(dir, after, after), "true");
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  test("the script is not vacuous — it can say both words", () => {
    // Guards against a future edit that hard-codes "true" and passes every
    // release-direction test above while silently disabling the whole feature.
    const seen = new Set([
      verdictFor(["frontend/a.tsx"]),
      verdictFor(["backend/a.py"]),
    ]);
    assert.deepStrictEqual([...seen].sort(), ["false", "true"]);
  });

  // ---- the wiring, not just the decision ---------------------------------
  test("deploy consumes the gate, and defaults to releasing if the output is missing", () => {
    const yml = fs.readFileSync(CI_YML, "utf8");
    assert.ok(
      yml.includes("release-required"),
      "the gate job must exist"
    );
    // `!= 'false'` (not `== 'true'`) is the fail-safe direction: an absent or
    // empty output must still deploy.
    assert.ok(
      yml.includes("needs.release-required.outputs.required != 'false'"),
      "deploy must gate on != 'false', so a missing output still releases"
    );
    assert.ok(
      !yml.includes("needs.release-required.outputs.required == 'true'"),
      "gating on == 'true' would turn a missing output into a silent non-deploy"
    );
  });
});
