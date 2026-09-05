// Deploy guard contract (#3171).
//
// The deploy step's guard is a shell script living inside ci.yml, so nothing in
// the repo ever executed it. That is how #3171 survived: the guard compared this
// run's SHA against `origin/master`'s TIP, and once merges started landing faster
// than CI completes, no run was ever still the tip by the time its deploy job
// began. Every deploy job printed "Skipping deploy" and exited 0, so the whole
// pipeline stayed green while production sat 80 minutes and ten merge commits
// behind master with certified ships undeployed.
//
// A text assertion could not have caught that — the old guard's text was exactly
// what its author intended. So this suite EXTRACTS the run block out of ci.yml
// and RUNS it, against a fake `git` on PATH that answers ls-remote/merge-base and
// records every push. The invariant under test is not "the script says X", it is:
//
//   deploy when this commit is ahead of what is live, never when it is behind.
//
// Dependency-free (`node --test`), and it lives in the e2e-contract job that
// `deploy: needs:` already lists, so it cannot be skipped on the way to a release.

const { test, describe, before } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");

// Fabricated 40-char SHAs. OLD is an ancestor of NEW is an ancestor of NEWEST.
const OLD = "a".repeat(40);
const NEW = "b".repeat(40);
const NEWEST = "c".repeat(40);
// Ancestry the fake git will honour, as "ancestor:descendant" pairs.
const LINEAGE = [`${OLD}:${NEW}`, `${OLD}:${NEWEST}`, `${NEW}:${NEWEST}`].join(" ");

/**
 * Pull the `run: |` body of the deploy step out of ci.yml and dedent it.
 * Deliberately text-based: the point is to execute the bytes CI executes, not a
 * paraphrase of them.
 */
function extractDeployScript() {
  const lines = fs.readFileSync(CI_YML, "utf8").split("\n");

  const jobStart = lines.indexOf("  deploy:");
  assert.notEqual(jobStart, -1, "ci.yml has no top-level job named `deploy`.");
  const after = lines.slice(jobStart + 1);
  let jobEnd = after.findIndex((l) => /^ {2}\S/.test(l));
  if (jobEnd === -1) jobEnd = after.length;
  const job = after.slice(0, jobEnd);

  const runIdx = job.findIndex((l) => /^ {8}run: \|\s*$/.test(l));
  assert.notEqual(
    runIdx,
    -1,
    "the deploy job no longer has a step with a literal `run: |` block. This suite " +
      "executes that block; if the deploy moved to an action or a checked-in script, " +
      "point this suite at wherever the guard now lives rather than deleting it.",
  );

  const body = [];
  for (const line of job.slice(runIdx + 1)) {
    if (line.trim() === "") {
      body.push("");
      continue;
    }
    if (!/^ {10}/.test(line)) break;
    body.push(line.slice(10));
  }
  assert.ok(body.length > 0, "the deploy step's `run: |` block is empty.");
  return body.join("\n");
}

/** The guard's decision logic, with comment lines removed. */
function codeOf(text) {
  return text
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");
}

/**
 * A stand-in `git` that answers only what the guard asks and journals every
 * call. Scenario knobs arrive as env vars so each case configures it inline.
 */
const FAKE_GIT = `#!/usr/bin/env bash
echo "$*" >> "$FAKE_GIT_LOG"
case "$1" in
  ls-remote)
    if [ -f "$FAKE_GIT_LOG.pushed" ] && [ -n "$FAKE_LIVE_AFTER_PUSH" ]; then
      [ "$FAKE_LIVE_AFTER_PUSH" = "none" ] || printf '%s\\trefs/heads/master\\n' "$FAKE_LIVE_AFTER_PUSH"
    else
      [ -z "$FAKE_LIVE" ] || printf '%s\\trefs/heads/master\\n' "$FAKE_LIVE"
    fi
    exit \${FAKE_LS_REMOTE_EXIT:-0}
    ;;
  merge-base)
    # git merge-base --is-ancestor <maybe-ancestor> <maybe-descendant>
    for pair in $FAKE_LINEAGE; do
      [ "$pair" = "$3:$4" ] && exit 0
    done
    exit 1
    ;;
  push)
    # The non-force attempt fails when the scenario says the server rejects it;
    # a --force attempt always lands.
    if [ -n "$FAKE_PUSH_REJECTS" ] && [[ "$*" != *"--force"* ]]; then
      touch "$FAKE_GIT_LOG.pushed"
      echo "! [rejected] master -> master (non-fast-forward)" >&2
      exit 1
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
`;

/**
 * Execute the real guard under a fake git. Returns its stdout and the journal of
 * git invocations it made.
 */
function runGuard(script, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lane1b-deploy-guard-"));
  try {
    const binDir = path.join(dir, "bin");
    fs.mkdirSync(binDir);
    fs.writeFileSync(path.join(binDir, "git"), FAKE_GIT, { mode: 0o755 });

    const scriptPath = path.join(dir, "guard.sh");
    fs.writeFileSync(scriptPath, script);
    const log = path.join(dir, "git.log");
    fs.writeFileSync(log, "");

    let stdout = "";
    let status = 0;
    try {
      stdout = execFileSync("bash", ["-e", scriptPath], {
        cwd: dir,
        encoding: "utf8",
        env: {
          PATH: `${binDir}:${process.env.PATH}`,
          HOME: dir,
          FAKE_GIT_LOG: log,
          FAKE_LINEAGE: LINEAGE,
          HEROKU_API_KEY: "fake-key",
          ...env,
        },
      });
    } catch (err) {
      status = err.status ?? 1;
      stdout = (err.stdout || "") + (err.stderr || "");
    }

    const calls = fs.readFileSync(log, "utf8").split("\n").filter(Boolean);
    return {
      stdout,
      status,
      calls,
      pushes: calls.filter((c) => c.startsWith("push ")),
    };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

describe("deploy guard (#3171): forward progress without ever rewinding", () => {
  let script;
  before(() => {
    script = extractDeployScript();
  });

  test("the harness is really executing the guard, not an empty string", () => {
    // Guards over extracted text rot silently when the extraction breaks: every
    // behavioural case below would "pass" against an empty script. Anchor it.
    assert.ok(
      script.includes("HEROKU_API_KEY"),
      "the extracted deploy script does not mention HEROKU_API_KEY — extraction is broken, " +
        "and every behavioural assertion in this file is passing vacuously.",
    );
    assert.ok(
      /git\s+push\s+heroku/.test(script),
      "the extracted deploy script contains no `git push heroku` — extraction is broken.",
    );
  });

  test("THE #3171 DEFECT: deploys when production is behind, even mid-merge-storm", () => {
    // The exact shape that starved production: this run's commit is ahead of
    // what is live, and master's tip has ALREADY moved on to something newer.
    // The old guard skipped here — that is the whole bug — so this case is the
    // one that must fail if the tip ever becomes the reference point again.
    const r = runGuard(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.equal(
      r.pushes.length,
      1,
      "the deploy did not push. Production was on an ANCESTOR of this run's commit, so " +
        "this release is pure forward progress and must happen regardless of how far " +
        `master's tip has moved on. Guard said:\n${r.stdout}`,
    );
    assert.match(
      r.pushes[0],
      new RegExp(`${NEW}:refs/heads/master`),
      "the deploy pushed something other than this run's exact commit.",
    );
  });

  test("does not rewind production when a NEWER commit is already live", () => {
    // The v3320-after-v3319 hazard the guard exists for: an older commit's
    // re-run reaching the push after a newer release already landed.
    const r = runGuard(script, { GITHUB_SHA: OLD, FAKE_LIVE: NEWEST });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.deepEqual(
      r.pushes,
      [],
      "an older re-run pushed over a newer live commit — this rewinds production, " +
        `which is the incident the guard exists to prevent. Guard said:\n${r.stdout}`,
    );
  });

  test("does nothing when this commit is already the live one", () => {
    const r = runGuard(script, { GITHUB_SHA: NEW, FAKE_LIVE: NEW });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.deepEqual(
      r.pushes,
      [],
      `re-releasing the commit already live restarts every dyno for nothing:\n${r.stdout}`,
    );
  });

  test("the first push is a fast-forward, so the read-then-write race is closed by git", () => {
    // The pre-check is a read followed by a write and cannot close the race on
    // its own. `--force` on the first attempt would let a lost race rewind prod.
    const r = runGuard(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD });

    assert.equal(r.pushes.length, 1, `expected exactly one push:\n${r.stdout}`);
    assert.ok(
      !r.pushes[0].includes("--force"),
      "the deploy force-pushes on its first attempt. The guard's check is a read " +
        "followed by a write, so only the server refusing a non-fast-forward stops a " +
        "deploy that lost the race from rewinding production.",
    );
  });

  test("a push rejected because a newer deploy won the race is left alone", () => {
    const r = runGuard(script, {
      GITHUB_SHA: NEW,
      FAKE_LIVE: OLD,
      FAKE_PUSH_REJECTS: "1",
      FAKE_LIVE_AFTER_PUSH: NEWEST,
    });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.deepEqual(
      r.pushes.filter((p) => p.includes("--force")),
      [],
      "the guard force-pushed after losing the race to a newer deploy, rewinding " +
        `production. Guard said:\n${r.stdout}`,
    );
  });

  test("a push rejected by diverged history still lands, via force", () => {
    // History rewrite: no fast-forward exists, and we have already established
    // the live commit is not ahead of us. Refusing here would jam deploys shut.
    const r = runGuard(script, {
      GITHUB_SHA: NEW,
      FAKE_LIVE: OLD,
      FAKE_PUSH_REJECTS: "1",
      FAKE_LIVE_AFTER_PUSH: OLD,
    });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.equal(
      r.pushes.filter((p) => p.includes("--force")).length,
      1,
      "master's history diverged and the live commit is not ahead of us, but the guard " +
        `never forced — deploys would stay jammed shut. Guard said:\n${r.stdout}`,
    );
  });

  test("an unreadable live ref defers to the push rather than skipping", () => {
    // Gotcha #53: an empty answer is a response shape, not an absence. Treating
    // "could not read" as "nothing is live" must not silently skip the release;
    // the non-fast-forward push is what adjudicates it.
    const r = runGuard(script, {
      GITHUB_SHA: NEW,
      FAKE_LIVE: "",
      FAKE_LS_REMOTE_EXIT: "1",
    });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.equal(
      r.pushes.length,
      1,
      "an unreadable live ref made the guard skip the deploy. A failed read is not " +
        `evidence that a release is unnecessary. Guard said:\n${r.stdout}`,
    );
  });

  test("no Heroku credential means no push, and no red job", () => {
    const r = runGuard(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD, HEROKU_API_KEY: "" });

    assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
    assert.deepEqual(r.pushes, [], `pushed without a credential:\n${r.stdout}`);
  });

  test("the deploy decision never reads origin/master's tip again", () => {
    // The defect's signature. `origin`'s tip says what has been MERGED; only
    // Heroku's ref says what is LIVE, and the guard's question is about the
    // latter. Comments are stripped so the incident write-up above may keep
    // naming the old behaviour.
    const code = codeOf(script);
    assert.ok(
      !/ls-remote\s+origin/.test(code),
      "the deploy guard is reading `origin`'s tip again. That is #3171: with merges " +
        "landing faster than CI completes, no run is still the tip when its deploy job " +
        "starts, so every deploy skips and production silently stops advancing.",
    );
  });
});
