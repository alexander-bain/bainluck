"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * CI trap #2 — a stacked PR got NO CI AT ALL, and that reads as "nothing to wait for".
 *
 * ## What happened
 *
 * `ci.yml` opened with:
 *
 *   on:
 *     pull_request:
 *       branches: [master]
 *
 * That is not "PRs into master get CI". It is "ONLY PRs into master get CI".
 * A PR whose BASE is another branch matches no trigger, so GitHub schedules
 * nothing. The result is not a pending check and not a red one — it is an empty
 * checks list, which renders as a PR with no objections, in exactly the spot a
 * reviewer looks for permission to merge.
 *
 * Two named failures, one week, both on stacked lane branches:
 *
 *   1. **PR #1943** (`lane1/q363` -> `lane1/q362`) showed `mergeStateStatus:
 *      DIRTY` and no checks. Retargeting the base to master did NOT help:
 *      GitHub emits `edited` for a retarget, and ci.yml listens to the default
 *      `opened`/`synchronize`/`reopened`. The retarget scheduled NOTHING. A
 *      close+reopen is what finally produced a run.
 *   2. **PR #1950** (`lane1/q365`, cut from `lane1/q364`) hit the same wall.
 *      Only gitleaks reported — because `gitleaks.yml` carries a bare
 *      `pull_request:` with no branch filter. That accident is the control:
 *      same repo, same PR, same base, one workflow ran and one did not, and the
 *      only difference was the filter.
 *
 * Both times the workaround was rediscovered from scratch, because the symptom
 * (a clean-looking PR with no checks) does not point at a trigger.
 *
 * ## Why this guard, and why it is shaped this way
 *
 * The tempting assertion is "ci.yml runs on PRs into lane1/*". That guards the
 * symptom — the specific bases that happened to be stacked — and it would need
 * editing the first time someone stacks on a base nobody predicted.
 *
 * The class is: **a workflow that gates deploy must schedule a run for EVERY
 * pull request, whatever its base.** Any `branches:`/`branches-ignore:` filter
 * under `pull_request:` re-creates a set of bases that silently get no CI, so
 * the guard forbids the filter itself rather than enumerating what it excludes.
 *
 * ## The circularity, stated honestly
 *
 * This guard cannot fire on the PR it would have saved. If the trigger is
 * broken, no CI runs, so no test runs. What it does catch is the REGRESSION:
 * `push: branches: [master]` still runs on every merge, so re-adding the filter
 * turns master red at the merge that introduces it. That is the reachable
 * promise, and it is worth stating rather than implying a stronger one.
 *
 * ## Why it lives here
 *
 * Dependency-free `node --test`, runs as `e2e-contract`, and `deploy: needs:`
 * it — the same reasoning that puts `jestGate`, `typecheckGate` and
 * `codeqlLanguages` in this directory.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");
const CODEQL_YML = path.join(REPO_ROOT, ".github", "workflows", "codeql.yml");
const LOOK_RAIL_YML = path.join(REPO_ROOT, ".github", "workflows", "look-rail-guard.yml");

function readWorkflow(file = CI_YML) {
  assert.ok(
    fs.existsSync(file),
    `${path.relative(REPO_ROOT, file)} is missing. If it genuinely moved, update this fixture in the same commit rather than leaving it to fail as a mystery.`
  );
  return fs.readFileSync(file, "utf8");
}

/**
 * Strip full-line `#` comments before any text assertion.
 *
 * Not optional here: the `on:` block this fixture inspects is now mostly a
 * comment explaining the two failures, and that prose necessarily contains the
 * literal string `branches: [master]` under `pull_request:`. Without stripping,
 * this guard would fail on the FIXED workflow and get "fixed" by deleting the
 * explanation. Ruling 078's clause 3 is the same failure in the other
 * direction: prose satisfying a check instead of tripping one.
 */
function codeOf(text) {
  return text
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
}

/** The body of a top-level `key:` block: its lines, up to the next column-0 key. */
function topLevelBlock(text, key) {
  const lines = codeOf(text).split("\n");
  const start = lines.findIndex((l) => l === `${key}:`);
  assert.notEqual(
    start,
    -1,
    `ci.yml has no top-level \`${key}:\` block. If the workflow was restructured, update this fixture in the same commit.`
  );
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^\S/.test(l));
  if (end === -1) end = rest.length;
  return rest.slice(0, end);
}

/** The body of a two-space-indented `key:` inside an already-extracted block. */
function nestedBlock(blockLines, key) {
  const start = blockLines.findIndex((l) => /^ {2}\S/.test(l) && l.trim() === `${key}:`);
  if (start === -1) return null;
  const rest = blockLines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return rest.slice(0, end);
}

describe("CI trap #2: every pull request gets a CI run, whatever its base", () => {
  it("ci.yml triggers on pull_request at all", () => {
    const on = topLevelBlock(readWorkflow(), "on");
    assert.ok(
      on.some((l) => l.trim() === "pull_request:"),
      "ci.yml no longer triggers on `pull_request:`. Every PR would merge with zero test signal."
    );
  });

  it("the pull_request trigger carries NO branch filter", () => {
    const on = topLevelBlock(readWorkflow(), "on");
    const pr = nestedBlock(on, "pull_request");
    assert.notEqual(pr, null, "no `pull_request:` key under `on:` in ci.yml.");

    const filter = pr.find((l) => /^\s+branches(-ignore)?:/.test(l));
    assert.equal(
      filter,
      undefined,
      `ci.yml restricts \`pull_request\` by base branch: "${filter && filter.trim()}".\n\n` +
        "That does not mean 'PRs into these branches get CI'. It means ONLY those PRs do — " +
        "a PR based on anything else matches no trigger and gets NO RUN AT ALL, which renders " +
        "as an empty checks list rather than a pending or failing one. Two stacked PRs (#1943, " +
        "#1950) were merged-blocked and then hand-worked around this way in one week. " +
        "Deploy does not need this filter: the `deploy` job is separately gated on " +
        "`github.event_name == 'push'` and `github.ref == 'refs/heads/master'`."
    );
  });

  it("push stays master-only, so branch pushes do not double-run alongside their PR", () => {
    const on = topLevelBlock(readWorkflow(), "on");
    const push = nestedBlock(on, "push");
    assert.notEqual(push, null, "no `push:` key under `on:` in ci.yml.");
    assert.ok(
      push.some((l) => /^\s+branches:\s*\[\s*master\s*\]/.test(l)),
      "ci.yml's `push:` trigger is no longer restricted to master. Removing the PULL_REQUEST " +
        "filter is the fix; removing the PUSH filter just runs the whole suite twice for every " +
        "branch that has a PR open."
    );
  });

  it("deploy is still gated on a push to master, so an any-base PR cannot release", () => {
    // This is the assertion that makes dropping the pull_request filter safe.
    // If deploy's guard ever weakens to something a pull_request event can
    // satisfy, a PR from a fork or a stacked branch could push to Heroku.
    const lines = codeOf(readWorkflow()).split("\n");
    const start = lines.findIndex((l) => l === "  deploy:");
    assert.notEqual(start, -1, "ci.yml has no top-level job named `deploy`.");
    const rest = lines.slice(start + 1);
    let end = rest.findIndex((l) => /^ {2}\S/.test(l));
    if (end === -1) end = rest.length;
    const deploy = rest.slice(0, end).join("\n");

    assert.match(
      deploy,
      /if:.*github\.event_name\s*==\s*'push'/,
      "the deploy job no longer requires `github.event_name == 'push'`. Since ci.yml now runs " +
        "on pull requests into ANY base, that condition is the only thing standing between a PR " +
        "run and a Heroku release."
    );
    assert.match(
      deploy,
      /if:.*github\.ref\s*==\s*'refs\/heads\/master'/,
      "the deploy job no longer requires `github.ref == 'refs/heads/master'`."
    );
  });
});

/** The `deploy:` job's body, comments stripped, as one string. */
function deployJob(text = readWorkflow()) {
  const lines = codeOf(text).split("\n");
  const start = lines.findIndex((l) => l === "  deploy:");
  assert.notEqual(start, -1, "ci.yml has no top-level job named `deploy`.");
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return rest.slice(0, end).join("\n");
}

/**
 * THRU-F — the release queue may DELAY a deploy; it may never KILL one.
 *
 * ## The two cancellations, which are not the same act
 *
 * A concurrency group can cancel a deploy in two states, and they are worlds
 * apart:
 *
 *   - **PENDING** — it holds the queue slot and has not started. Cancelling it
 *     costs nothing and is the whole reason the group is here: it coalesces a
 *     burst of merges down to one release of the newest sha instead of one
 *     release per merge.
 *   - **IN PROGRESS** — it is inside `git push heroku`. That push is not a
 *     handshake. Heroku streams the entire build and release back over it, so
 *     the job stays "in progress" for minutes *while production is changing*.
 *
 * `cancel-in-progress: true` did not distinguish them. Killing the second kind
 * does not stop the deploy — once the ref moves, Heroku builds and releases
 * server-side regardless — it removes only our ability to WATCH it. The release
 * lands, the run reads `cancelled`, and the never-backwards guard's entire
 * reconciliation path (re-read what is live, retry a proven fast-forward, fail
 * closed on unprovable ancestry) never executes, because there is no job left
 * to execute it. The outcome is a production change with no adjudicator.
 *
 * ## Why turning it off does not cost throughput
 *
 * `cancel-in-progress` does not govern the pending case at all. A concurrency
 * group holds exactly ONE pending job, and a newly queued job always cancels
 * the previously pending one. So the coalescing survives the flag being false:
 * ten merges still cost at most two Heroku builds — the one already running,
 * then the newest sha that queued behind it.
 *
 * ## Why the assertion is shaped this way
 *
 * The class is "a release must not be cancelled mid-flight", so the guard
 * forbids the value `true` rather than demanding the literal `false`. Deleting
 * the key is also safe (false is the default) and must not fail this test —
 * a guard that reddens on a *safe* config gets deleted, not obeyed.
 *
 * The group itself is asserted separately and for the opposite reason: dropping
 * `group: heroku-deploy`, or making it per-run with a `${{ }}` expression, would
 * remove the serialization and let two `git push heroku` calls race — which is
 * the failure the group exists to prevent and is not what this change loosens.
 */
describe("THRU-F: the deploy queue delays releases, it never kills one", () => {
  it("deploy still serializes on a constant `heroku-deploy` concurrency group", () => {
    const deploy = deployJob();

    assert.match(
      deploy,
      /^\s+concurrency:$/m,
      "the deploy job no longer declares a `concurrency:` block. Without one, two merges " +
        "whose CI finishes together both run `git push heroku` at once and race over which " +
        "release lands last."
    );

    const group = deploy.split("\n").find((l) => /^\s+group:/.test(l));
    assert.notEqual(group, undefined, "deploy's `concurrency:` block has no `group:` key.");
    assert.equal(
      group.trim(),
      "group: heroku-deploy",
      `deploy's concurrency group is "${group.trim()}", not "group: heroku-deploy".`
    );
    assert.doesNotMatch(
      group,
      /\$\{\{/,
      `deploy's concurrency group is templated ("${group.trim()}"). A group computed from the ` +
        "run, sha or ref puts every deploy in a group of its own, which is the same as having " +
        "no group: releases stop being serialized and can push to Heroku concurrently."
    );
  });

  it("deploy is never cancelled in progress, because in progress means mid-release", () => {
    const deploy = deployJob();
    const flag = deploy.split("\n").find((l) => /^\s+cancel-in-progress:/.test(l));

    // Absent is fine — false is the GitHub default. Only `true` is the defect.
    if (flag === undefined) return;

    assert.equal(
      flag.trim(),
      "cancel-in-progress: false",
      `deploy sets "${flag.trim()}". A deploy job is "in progress" for the whole of ` +
        "`git push heroku`, and Heroku streams the build and release back over that push — so " +
        "cancelling it does not stop the release, it only throws away the job that was " +
        "supposed to verify and reconcile it. Production changes, the run reads `cancelled`, " +
        "and the never-backwards guard's rejection/ancestry/fail-closed path never runs.\n\n" +
        "This does not need to be true to coalesce a merge burst: a concurrency group holds " +
        "one pending job and a newly queued job already cancels the previously pending one, " +
        "whatever this flag says. Delete the key or set it to false; do not set it to true."
    );
  });
});

/**
 * The SAME trap, in the other workflow that carried it (queue 367).
 *
 * `codeql.yml` opened with the identical `pull_request: branches: ["master"]`,
 * so a stacked PR got no CodeQL run either. CodeQL does not gate deploy, which
 * is exactly what makes its absence quieter and the reading worse: a security
 * analysis that never ran and a security analysis that found nothing produce
 * the same PR page.
 *
 * The assertion is deliberately the class, not the file: any workflow that is
 * expected to speak on a pull request must not filter by base. If a third
 * workflow acquires the filter, add it to `PR_WORKFLOWS` — the point of a
 * shared list is that the next instance is one line, not one rediscovery.
 */
const PR_WORKFLOWS = [
  { name: "ci.yml", file: CI_YML },
  { name: "codeql.yml", file: CODEQL_YML },
  // #4032 — taking the invitation above: the third instance is one line here,
  // not one rediscovery. This one carries a `paths:` filter, which is a
  // different thing and is deliberate — it scopes WHICH pull requests the LOOK
  // rail guard speaks on, and never leaves a PR it should have spoken on
  // showing an empty checks list.
  { name: "look-rail-guard.yml", file: LOOK_RAIL_YML },
];

describe("CI trap #2, generalized: no PR-reporting workflow filters by base branch", () => {
  for (const { name, file } of PR_WORKFLOWS) {
    it(`${name} triggers on pull_request with NO branch filter`, () => {
      const on = topLevelBlock(readWorkflow(file), "on");
      assert.ok(
        on.some((l) => l.trim() === "pull_request:"),
        `${name} no longer triggers on \`pull_request:\` at all.`
      );

      const pr = nestedBlock(on, "pull_request");
      // A bare `pull_request:` with no body yields an empty block, which is the
      // fixed shape. `null` means the key is absent entirely — caught above.
      const filter = (pr || []).find((l) => /^\s+branches(-ignore)?:/.test(l));
      assert.equal(
        filter,
        undefined,
        `${name} restricts \`pull_request\` by base branch: "${filter && filter.trim()}".\n\n` +
          "A PR based on anything else matches no trigger and gets NO RUN AT ALL — an empty " +
          "checks list, not a pending or failing one. For a workflow that does not gate deploy " +
          "this is worse, not better: nothing turns red, so the absence is never chased."
      );
    });
  }
});
