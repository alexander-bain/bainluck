'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const workflow = fs.readFileSync(path.resolve(__dirname, '../../../.github/workflows/tier-b-review.yml'), 'utf8');
const script = workflow.split('          script: |\n')[1]?.split('\n      - uses:')[0]
  .split('\n').map(line => line.replace(/^ {12}/, '')).join('\n');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const ci = {id: 2, path: '.github/workflows/ci.yml', check_suite_id: 20,
  status: 'completed', conclusion: 'success', html_url: 'https://example.test/ci/2'};
const check = {name: 'backend-tests (7)', check_suite: {id: 20}, status: 'completed', conclusion: 'success'};
const open = {state: 'open', draft: false, head: {sha: 'head'}, labels: [{name: 'tier-b'}]};

async function runGate({rounds = [{runs: [ci], checks: [check]}], prs = [open]} = {}) {
  let elapsed = 0, poll = 0, reads = 0;
  const outputs = {}, errors = [], messages = [];
  const github = {rest: {pulls: {}, actions: {listWorkflowRunsForRepo() {}}, checks: {listForRef() {}}}};
  github.rest.pulls.get = async () => ({data: prs[Math.min(reads++, prs.length - 1)]});
  github.paginate = async (fn, args) => {
    assert.equal(args.per_page, 100);
    if (fn === github.rest.actions.listWorkflowRunsForRepo) {
      assert.equal(args.head_sha, 'head');
      assert.equal(args.event, 'pull_request');
      return rounds[Math.min(poll, rounds.length - 1)].runs;
    }
    assert.equal(fn, github.rest.checks.listForRef);
    assert.equal(args.ref, 'head');
    assert.equal(args.filter, 'latest');
    return rounds[Math.min(poll++, rounds.length - 1)].checks;
  };
  await new AsyncFunction('github', 'context', 'core', 'Date', 'setTimeout', script)(
    github, {repo: {owner: 'owner', repo: 'repo'}, payload: {pull_request: {number: 1, head: {sha: 'head'}}}},
    {setOutput: (k, v) => { outputs[k] = v; }, setFailed: msg => errors.push(msg),
      notice: msg => messages.push(msg), info: msg => messages.push(msg)},
    {now: () => elapsed}, (callback, ms) => { elapsed += ms; callback(); });
  return {outputs, errors, elapsed, poll, messages};
}

test('pending CI never starts Claude; green CI does, without policy/self deadlock', async () => {
  const policy = {...check, name: 'Tier-B approval', conclusion: 'failure', check_suite: {id: 30}};
  const self = {...check, name: 'review', status: 'in_progress', conclusion: null, check_suite: {id: 40}};
  const result = await runGate({rounds: [
    {runs: [{...ci, status: 'in_progress', conclusion: null}], checks: [{...check, status: 'in_progress', conclusion: null}, policy, self]},
    {runs: [ci], checks: [check, policy, self]},
  ]});
  assert.deepEqual(result.outputs, {ready: 'true'});
  assert.equal(result.elapsed, 60000);
  assert.equal(result.poll, 2);
  assert.deepEqual(result.errors, []);
});

test('cancelled/superseded suites cannot masquerade as current failures', async () => {
  const cancelled = {...ci, id: 3, check_suite_id: 30, conclusion: 'cancelled'};
  const older = {...ci, id: 1, check_suite_id: 10, conclusion: 'failure'};
  const result = await runGate({rounds: [{runs: [ci, cancelled, older], checks: [check,
    {...check, name: 'old-red', check_suite: {id: 30}, conclusion: 'failure'},
    {...check, name: 'older-red', check_suite: {id: 10}, conclusion: 'failure'}]}]});
  assert.equal(result.outputs.ready, 'true');
});

test('red CI or another current check stops immediately', async () => {
  for (const round of [
    {runs: [{...ci, conclusion: 'failure'}], checks: [check]},
    {runs: [ci], checks: [{...check, conclusion: 'failure'}]},
    {runs: [ci], checks: [{...check, name: 'CodeQL', conclusion: 'timed_out', check_suite: {id: 50}}]},
  ]) {
    const result = await runGate({rounds: [round]});
    assert.equal(result.outputs.ready, undefined);
    assert.equal(result.elapsed, 0);
    assert.match(result.errors[0], /CI is red/);
  }
});

test('a new pending run supersedes old success; a missing or cancelled-only CI times out', async () => {
  for (const runs of [[], [{...ci, conclusion: 'cancelled'}],
    [ci, {...ci, id: 3, status: 'in_progress', conclusion: null, check_suite_id: 30}]]) {
    const result = await runGate({rounds: [{runs, checks: [check]}]});
    assert.equal(result.outputs.ready, undefined);
    assert.equal(result.elapsed, 30 * 60000);
    assert.match(result.errors[0], /Timed out after 30 minutes/);
  }
});

test('pending non-CI checks and empty check lists never pass on CI success alone', async () => {
  for (const checks of [[], [{...check, status: 'queued', conclusion: null}]]) {
    const result = await runGate({rounds: [{runs: [ci], checks}]});
    assert.equal(result.outputs.ready, undefined);
    assert.match(result.errors[0], /Timed out/);
  }
});

test('closed/draft/unlabeled/stale PRs never review, including a head move after check reads', async () => {
  for (const stale of [{...open, state: 'closed'}, {...open, draft: true}, {...open, labels: []},
    {...open, head: {sha: 'new-head'}}]) {
    for (const prs of [[stale], [open, stale]]) {
      const result = await runGate({prs});
      assert.equal(result.outputs.ready, undefined);
      assert.equal(result.elapsed, 0);
    }
  }
});

test('the installed action is gated and pytest uses separate narrow executable permissions', () => {
  assert.match(workflow, /actions: read/);
  assert.match(workflow, /checks: read/);
  assert.match(workflow, /anthropics\/claude-code-action@v1\n        if: steps.ci.outputs.ready == 'true'/);
  for (const command of ['cd:*', 'python -m pytest:*', 'python3 -m pytest:*', 'echo:*', 'tail:*']) {
    assert.ok(workflow.includes(`Bash(${command})`), command);
  }
  assert.ok(!workflow.includes('Bash(python3:*)'));
  assert.ok(!workflow.includes('--dangerously-skip-permissions'));
});
