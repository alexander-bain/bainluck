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

function readWorkflow() {
  assert.ok(
    fs.existsSync(CI_YML),
    ".github/workflows/ci.yml is missing. It is the deploy gate; if it genuinely moved, update this fixture in the same commit rather than leaving it to fail as a mystery."
  );
  return fs.readFileSync(CI_YML, "utf8");
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
