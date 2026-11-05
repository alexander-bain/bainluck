// Execute the actual reviewer wait step; no GitHub calls, dependencies or timers.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const workflow = fs.readFileSync(path.resolve(__dirname, '../../../.github/workflows/tier-b-review.yml'), 'utf8');
const source = workflow.match(/      - name: Wait for green CI at this head[\s\S]*?          script: \|\n([\s\S]*?)(?=      - uses:)/)[1];
const wait = new (Object.getPrototypeOf(async function(){}).constructor)(
  'github', 'context', 'core', 'Date', 'setTimeout', source);
const app = {databaseId: 15368};
const requirement = context => ({context, app});
const check = (name, conclusion = 'success', more = {}) => ({
  name, conclusion, status: 'completed', app: {id: 15368}, check_suite: {id: 2}, ...more,
});
const required = Array.from({length: 8}, (_, i) => requirement(`backend-tests (${i + 1})`));

async function run(options = {}) {
  let now = 0, gets = 0, queries = 0;
  const ready = [], failures = [];
  let polls = 0;
  const defaultChecks = required.map(r => check(r.context));
  const rounds = options.rounds || [{checks: options.checks || defaultChecks, runs: options.runs}];
  const pr = {state: 'open', draft: false, head: {sha: 'head'}, labels: [{name: 'tier-b'}]};
  const rule = options.rule === undefined
    ? {requiresStatusChecks: true, requiredStatusChecks: [...required, requirement('Tier-B approval')]}
    : options.rule;
  const github = {
    rest: {
      pulls: {get: async () => ({data: (++gets === 2 && options.finalPR) || options.initialPR || pr})},
      actions: {listWorkflowRunsForRepo: async () => rounds[Math.min(polls, rounds.length - 1)].runs || [
        {id: 2, path: '.github/workflows/ci.yml', status: 'completed', conclusion: 'success', check_suite_id: 2},
      ]},
      checks: {listForRef: async () => rounds[Math.min(polls++, rounds.length - 1)].checks},
      repos: {listCommitStatusesForRef: async () => options.statuses || []},
    },
    graphql: async (query, args) => {
      queries++;
      assert.match(query, /requiredStatusChecks\{context app\{databaseId\}\}/);
      assert.deepEqual(args, {owner: 'owner', repo: 'repo', number: 61});
      if (options.apiError) throw options.apiError;
      return {repository: {pullRequest: {headRefOid: options.policyHead || 'head', baseRef: {branchProtectionRule: rule}}}};
    },
    paginate: async (fn, args) => {
      assert.equal(args.head_sha || args.ref, 'head');
      return fn(args);
    },
  };
  await wait(github, {repo: {owner: 'owner', repo: 'repo'}, payload: {pull_request: {number: 61, head: {sha: 'head'}}}},
    {notice() {}, info() {}, setOutput: (key, value) => ready.push([key, value]), setFailed: text => failures.push(text)},
    {now: () => now}, callback => {now += 60000; callback();});
  return {ready, failures, queries, polls, elapsed: now};
}

test('all eight required shards pass despite failed optional Watch and pending approval', async () => {
  const result = await run({checks: [...required.map(r => check(r.context)),
    check('Build exact simulator products once for five fresh pairs', 'failure'),
    check('review', 'failure'), check('Tier-B approval', 'failure')]});
  assert.deepEqual(result.ready, [['ready', 'true']]);
  assert.deepEqual(result.failures, []);
});

test('any one of eight required shards failing prevents the reviewer', async () => {
  for (let failed = 0; failed < 8; failed++) {
    const result = await run({checks: required.map((r, i) => check(r.context, i === failed ? 'failure' : 'success'))});
    assert.deepEqual(result.ready, []);
    assert.match(result.failures[0], new RegExp(`backend-tests \\(${failed + 1}\\)`));
  }
});

for (const kind of ['missing', 'pending', 'wrong app']) test(`a ${kind} required shard never starts review`, async () => {
  const checks = required.map(r => check(r.context));
  if (kind === 'missing') checks.pop();
  if (kind === 'pending') checks[7].status = 'in_progress';
  if (kind === 'wrong app') checks[7].app.id = 1;
  const result = await run({checks});
  assert.deepEqual(result.ready, []);
  assert.match(result.failures[0], /Timed out/);
});

test('superseded cancelled check suites cannot hide their successful replacement', async () => {
  const result = await run({runs: [
    {id: 2, path: 'ci.yml', conclusion: 'success', check_suite_id: 2},
    {id: 1, path: 'ci.yml', conclusion: 'cancelled', check_suite_id: 1},
  ], checks: [check(required[0].context, 'cancelled', {check_suite: {id: 1}}), ...required.map(r => check(r.context))]});
  assert.deepEqual(result.ready, [['ready', 'true']]);
});

test('a newly required optional check becomes a blocker without editing a list', async () => {
  const result = await run({rule: {requiresStatusChecks: true, requiredStatusChecks: [requirement('Watch')]},
    checks: [check('Watch', 'failure')]});
  assert.deepEqual(result.ready, []);
  assert.match(result.failures[0], /Watch/);
});

test('unbound legacy status contexts obey their actual GitHub state', async () => {
  const rule = {requiresStatusChecks: true, requiredStatusChecks: [{context: 'external', app: null}]};
  for (const state of ['success', 'pending', 'failure']) {
    const result = await run({rule, statuses: [{context: 'external', state}]});
    assert.equal(result.ready.length, state === 'success' ? 1 : 0);
  }
});

test('unreadable or empty protection never produces an approval-ready output', async () => {
  for (const rule of [null, {requiresStatusChecks: false},
    {requiresStatusChecks: true, requiredStatusChecks: []},
    {requiresStatusChecks: true, requiredStatusChecks: [requirement('Tier-B approval')]}]) {
    const result = await run({rule});
    assert.deepEqual(result.ready, []);
    assert.equal(result.failures.length, 1);
  }
  await assert.rejects(run({apiError: new Error('403')}), /403/);
});

test('a moved head, draft or removed label still stops the reviewer', async () => {
  assert.deepEqual((await run({policyHead: 'new'})).ready, []);
  for (const change of [{head: {sha: 'new'}}, {draft: true}, {labels: []}, {state: 'closed'}]) {
    const result = await run({finalPR: {state: 'open', draft: false, head: {sha: 'head'}, labels: [{name: 'tier-b'}], ...change}});
    assert.deepEqual(result.ready, []);
  }
});


test('a pending required check is polled until its green replacement arrives', async () => {
  const result = await run({rounds: [
    {checks: required.map(r => check(r.context, null, {status: 'in_progress'}))},
    {checks: required.map(r => check(r.context))},
  ]});
  assert.deepEqual(result.ready, [['ready', 'true']]);
  assert.equal(result.polls, 2);
  assert.equal(result.elapsed, 60000);
});

test('a newer pending suite prevents reusing the superseded successful checks', async () => {
  const result = await run({runs: [
    {id: 2, path: 'ci.yml', conclusion: 'success', check_suite_id: 2},
    {id: 3, path: 'ci.yml', conclusion: null, status: 'in_progress', check_suite_id: 3},
  ]});
  assert.deepEqual(result.ready, []);
  assert.match(result.failures[0], /Timed out/);
});

test('closed, draft and unlabeled PRs stop before querying checks', async () => {
  for (const change of [{state: 'closed'}, {draft: true}, {labels: []}, {head: {sha: 'new'}}]) {
    const result = await run({initialPR: {state: 'open', draft: false, head: {sha: 'head'}, labels: [{name: 'tier-b'}], ...change}});
    assert.deepEqual(result.ready, []);
    assert.equal(result.queries, 0);
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
