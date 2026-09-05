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
// FORK shares no ancestry with any of them: a rewritten master.
const OLD = "a".repeat(40);
const NEW = "b".repeat(40);
const NEWEST = "c".repeat(40);
const FORK = "d".repeat(40);
// Ancestry the fake git will honour, as "ancestor:descendant" pairs.
const LINEAGE = [`${OLD}:${NEW}`, `${OLD}:${NEWEST}`, `${NEW}:${NEWEST}`].join(" ");
// Commit objects the fake git admits to holding. A live commit absent from this
// list models the case the guard must not misread: `merge-base --is-ancestor`
// against a commit we never fetched exits non-zero, exactly like a truthful "no".
const ALL_KNOWN = [OLD, NEW, NEWEST, FORK].join(" ");

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
    # $2 is the remote: origin is GitHub's master tip, heroku is what is live.
    if [ "$2" = "origin" ]; then
      [ -z "$FAKE_ORIGIN_TIP" ] || printf '%s\\trefs/heads/master\\n' "$FAKE_ORIGIN_TIP"
      exit 0
    fi
    if [ -f "$FAKE_GIT_LOG.pushed" ] && [ -n "$FAKE_LIVE_AFTER_PUSH" ]; then
      # "none" is the sentinel for a ref read that comes back EMPTY, which an
      # empty env var cannot express: bash cannot tell it from unset.
      [ "$FAKE_LIVE_AFTER_PUSH" = "none" ] || printf '%s\\trefs/heads/master\\n' "$FAKE_LIVE_AFTER_PUSH"
    else
      [ -z "$FAKE_LIVE" ] || printf '%s\\trefs/heads/master\\n' "$FAKE_LIVE"
    fi
    exit \${FAKE_LS_REMOTE_EXIT:-0}
    ;;
  cat-file)
    # git cat-file -e <sha>^{commit} — do we hold this object at all?
    want="\${3%%^*}"
    for sha in \${FAKE_KNOWN:-$FAKE_ALL_KNOWN}; do
      [ "$sha" = "$want" ] && exit 0
    done
    exit 1
    ;;
  merge-base)
    # git merge-base --is-ancestor <maybe-ancestor> <maybe-descendant>
    for pair in $FAKE_LINEAGE; do
      [ "$pair" = "$3:$4" ] && exit 0
    done
    exit 1
    ;;
  push)
    # Only the FIRST non-force attempt is rejected, so a scenario can exercise a
    # retry. A --force attempt always lands — which is the point: the tests below
    # assert the guard does not reach one.
    if [ -n "$FAKE_PUSH_REJECTS" ] && [[ "$*" != *"--force"* ]] \\
       && [ ! -f "$FAKE_GIT_LOG.pushed" ]; then
      touch "$FAKE_GIT_LOG.pushed"
      echo "! [rejected] master -> master (non-fast-forward)" >&2
      exit 1
    fi
    touch "$FAKE_GIT_LOG.pushed"
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
`;

/**
 * Execute the real guard under a fake git, once per shell mode. Returns its
 * stdout and the journal of git invocations it made.
 *
 * CI runs the step as `bash -e {0}`. The suite ALSO runs every scenario under
 * `-o pipefail`, so the guard's behaviour is pinned under both: a runner or
 * workflow that later adds pipefail must not silently change what deploys.
 */
function runGuardIn(shellArgs, script, env) {
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
      stdout = execFileSync("bash", [...shellArgs, scriptPath], {
        cwd: dir,
        encoding: "utf8",
        env: {
          PATH: `${binDir}:${process.env.PATH}`,
          HOME: dir,
          FAKE_GIT_LOG: log,
          FAKE_LINEAGE: LINEAGE,
          FAKE_ALL_KNOWN: ALL_KNOWN,
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
      forcePushes: calls.filter((c) => c.startsWith("push ") && c.includes("--force")),
    };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

const SHELL_MODES = [
  ["bash -e (what CI runs)", ["-e"]],
  ["bash -e -o pipefail", ["-e", "-o", "pipefail"]],
];

/** Run a scenario under every shell mode and assert each result identically. */
function forEachShell(script, env, assertResult) {
  for (const [label, args] of SHELL_MODES) {
    const r = runGuardIn(args, script, env);
    try {
      assertResult(r);
    } catch (err) {
      err.message = `under ${label}: ${err.message}`;
      throw err;
    }
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
    // what is live, and GitHub's master tip has ALREADY moved past us. The old
    // guard skipped here — that is the whole bug — so this is the case that must
    // fail if the tip ever becomes the deploy DECISION's reference point again.
    forEachShell(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD, FAKE_ORIGIN_TIP: NEWEST }, (r) => {
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
  });

  test("does not rewind production when a NEWER commit is already live", () => {
    // The v3320-after-v3319 hazard the guard exists for: an older commit's
    // re-run reaching the push after a newer release already landed.
    forEachShell(script, { GITHUB_SHA: OLD, FAKE_LIVE: NEWEST, FAKE_ORIGIN_TIP: NEWEST }, (r) => {
      assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
      assert.deepEqual(
        r.pushes,
        [],
        "an older re-run pushed over a newer live commit — this rewinds production, " +
          `which is the incident the guard exists to prevent. Guard said:\n${r.stdout}`,
      );
    });
  });

  test("does nothing when this commit is already the live one", () => {
    forEachShell(script, { GITHUB_SHA: NEW, FAKE_LIVE: NEW }, (r) => {
      assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
      assert.deepEqual(
        r.pushes,
        [],
        `re-releasing the commit already live restarts every dyno for nothing:\n${r.stdout}`,
      );
    });
  });

  test("the first push is a fast-forward, so the read-then-write race is closed by git", () => {
    // The pre-check is a read followed by a write and cannot close the race on
    // its own. `--force` on the first attempt would let a lost race rewind prod.
    forEachShell(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD }, (r) => {
      assert.equal(r.pushes.length, 1, `expected exactly one push:\n${r.stdout}`);
      assert.deepEqual(
        r.forcePushes,
        [],
        "the deploy force-pushes on its first attempt. The guard's check is a read " +
          "followed by a write, so only the server refusing a non-fast-forward stops a " +
          "deploy that lost the race from rewinding production.",
      );
    });
  });

  test("a push rejected because a newer deploy won the race is left alone", () => {
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: OLD,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: NEWEST,
        FAKE_ORIGIN_TIP: NEWEST,
      },
      (r) => {
        assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
        assert.deepEqual(
          r.forcePushes,
          [],
          "the guard force-pushed after losing the race to a newer deploy, rewinding " +
            `production. Guard said:\n${r.stdout}`,
        );
      },
    );
  });

  // ---------------------------------------------------------------------------
  // CERT-1867's finding. The first cut of this repair treated "the live commit
  // is not provably newer" as permission to force. It is not: `merge-base
  // --is-ancestor` against a commit we never fetched exits non-zero, which is
  // indistinguishable from a truthful "no". So an unreadable or unfetched live
  // commit — which can perfectly well BE a newer deploy — reached `--force` and
  // rewound production. "Cannot prove" must fail closed, not fall through.
  // ---------------------------------------------------------------------------

  test("CERT-1867: a live commit whose ancestry we cannot prove NEVER gets force-pushed", () => {
    // NEWEST is genuinely live and genuinely newer, but we never fetched it, so
    // every ancestry question about it answers "no" for the wrong reason.
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: OLD,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: NEWEST,
        FAKE_KNOWN: `${OLD} ${NEW}`, // NEWEST deliberately absent: never fetched
        FAKE_ORIGIN_TIP: NEWEST,
      },
      (r) => {
        assert.deepEqual(
          r.forcePushes,
          [],
          "the guard force-pushed over a live commit it could not reason about. That " +
            "commit was NEWER, so this rewinds production — CERT-1867's exact finding. " +
            `Unprovable ancestry must fail closed. Guard said:\n${r.stdout}`,
        );
        assert.notEqual(
          r.status,
          0,
          "the guard exited green after refusing to deploy. A deploy that could not be " +
            "completed safely must redden the job so somebody looks, not pass silently — " +
            `that silence is how #3171 hid for 80 minutes. Guard said:\n${r.stdout}`,
        );
      },
    );
  });

  test("CERT-1867: an unreadable live ref after a rejection NEVER gets force-pushed", () => {
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: OLD,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: "none", // the ref read comes back EMPTY after the reject
        FAKE_ORIGIN_TIP: NEWEST,
      },
      (r) => {
        assert.deepEqual(
          r.forcePushes,
          [],
          "the guard force-pushed while it could not read what was live at all. An empty " +
            "answer is a response shape, not an absence (gotcha #53) — it is not evidence " +
            `that nothing newer is deployed. Guard said:\n${r.stdout}`,
        );
        assert.notEqual(r.status, 0, `expected a red job, not a silent pass:\n${r.stdout}`);
      },
    );
  });

  test("CERT-1867: diverged history does not force either, unless we ARE master's tip", () => {
    // FORK shares no ancestry with our commit: master was rewritten. We are not
    // the tip, so something newer may exist and forcing could lose it.
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: FORK,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: FORK,
        FAKE_ORIGIN_TIP: NEWEST,
      },
      (r) => {
        assert.deepEqual(
          r.forcePushes,
          [],
          "the guard forced over diverged history while a newer commit existed on " +
            `master. Guard said:\n${r.stdout}`,
        );
        assert.notEqual(r.status, 0, `expected a red job, not a silent pass:\n${r.stdout}`);
      },
    );
  });

  test("a history rewrite still self-heals when this commit IS master's tip", () => {
    // The single sanctioned force. Nothing newer exists to lose, so a rewrite
    // does not need a human — otherwise the repair would jam deploys shut, which
    // is the failure mode #3171 was in the first place.
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: FORK,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: FORK,
        FAKE_ORIGIN_TIP: NEW, // we are the tip
      },
      (r) => {
        assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
        assert.equal(
          r.forcePushes.length,
          1,
          "master's history diverged and this commit IS the tip, so nothing newer can be " +
            `lost — but the guard never forced, and deploys stay jammed. Guard said:\n${r.stdout}`,
        );
      },
    );
  });

  test("a rejection over a provably-behind live commit retries as a fast-forward, not a force", () => {
    // Transient rejection: the ref moved and moved back. A fast-forward exists,
    // so take it — but as a fast-forward.
    forEachShell(
      script,
      {
        GITHUB_SHA: NEW,
        FAKE_LIVE: OLD,
        FAKE_PUSH_REJECTS: "1",
        FAKE_LIVE_AFTER_PUSH: OLD,
        FAKE_ORIGIN_TIP: NEW,
      },
      (r) => {
        assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
        assert.deepEqual(
          r.forcePushes,
          [],
          "the guard forced when a plain fast-forward was available and provably safe. " +
            `Guard said:\n${r.stdout}`,
        );
        assert.equal(r.pushes.length, 2, `expected a retry, got ${r.pushes.length}:\n${r.stdout}`);
      },
    );
  });

  test("an unreadable live ref BEFORE the push defers to the push rather than skipping", () => {
    // Gotcha #53 in the other direction: a failed read must not be mistaken for
    // "nothing is live" and silently skip the release. The non-fast-forward push
    // is what adjudicates it, and it is safe because it cannot overwrite.
    forEachShell(
      script,
      { GITHUB_SHA: NEW, FAKE_LIVE: "", FAKE_LS_REMOTE_EXIT: "1" },
      (r) => {
        assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
        assert.equal(
          r.pushes.length,
          1,
          "an unreadable live ref made the guard skip the deploy. A failed read is not " +
            `evidence that a release is unnecessary. Guard said:\n${r.stdout}`,
        );
        assert.deepEqual(r.forcePushes, [], `and it must not force:\n${r.stdout}`);
      },
    );
  });

  test("no Heroku credential means no push, and no red job", () => {
    forEachShell(script, { GITHUB_SHA: NEW, FAKE_LIVE: OLD, HEROKU_API_KEY: "" }, (r) => {
      assert.equal(r.status, 0, `guard exited ${r.status}:\n${r.stdout}`);
      assert.deepEqual(r.pushes, [], `pushed without a credential:\n${r.stdout}`);
    });
  });

  test("the tip is read only AFTER the push, so it cannot gate the deploy decision", () => {
    // #3171's signature was the tip deciding WHETHER to deploy. The tip is still
    // read once — to decide whether a force can lose anything — so the invariant
    // is structural rather than a ban: it must come after the push has already
    // been attempted, which makes it impossible for it to suppress one.
    // Comments are stripped so the incident write-up may keep naming the old
    // behaviour; the behavioural cases above are the real guarantee.
    const code = codeOf(script);

    const tipReads = (code.match(/ls-remote\s+origin/g) || []).length;
    assert.ok(
      tipReads <= 1,
      `the guard reads origin's tip ${tipReads} times. It needs it once, to decide whether ` +
        "a force can lose anything; more suggests the tip is creeping back into the deploy " +
        "decision, which is #3171.",
    );

    if (tipReads === 0) return; // a repair that drops the escape hatch entirely is fine

    const firstPush = code.search(/git\s+push\s+heroku/);
    const tipRead = code.search(/ls-remote\s+origin/);
    assert.ok(firstPush !== -1, "the guard no longer pushes to heroku at all.");
    assert.ok(
      tipRead > firstPush,
      "the guard reads origin/master's tip BEFORE it attempts the push, so the tip can " +
        "once again decide whether a deploy happens at all. With merges landing faster " +
        "than CI completes, no run is still the tip when its deploy job starts — that " +
        "makes every deploy skip and production silently stops advancing (#3171).",
    );
  });
});
