// Execute the actual reviewer wait step; no GitHub calls, dependencies or timers.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const workflow = fs.readFileSync(path.resolve(__dirname, '../../../.github/workflows/tier-b-review.yml'), 'utf8');
const source = workflow.match(/      - name: Wait for green CI at this head[\s\S]*?          script: \|\n([\s\S]*?)(?=      - uses:)/)[1];
const wait = new (Object.getPrototypeOf(async function(){}).constructor)(
  'github', 'context', 'core', 'Date', 'setTimeout', 'process', source);
const app = {databaseId: 15368};
const requirement = context => ({context, app});
let nextId = 1;
const check = (name, conclusion = 'success', more = {}) => ({
  id: nextId++, name, conclusion, status: 'completed', app: {id: 15368}, check_suite: {id: 2}, ...more,
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
      assert.match(query, /refUpdateRule\{requiredStatusCheckContexts\}/);
      assert.match(query, /isRequired\(pullRequestNumber:\$number\)/);
      assert.doesNotMatch(query, /branchProtectionRule/);
      assert.deepEqual(args, {owner: 'owner', repo: 'repo', number: 61, cursor: args.cursor});
      if (options.apiError) throw options.apiError;
      const specifications = rule?.requiresStatusChecks ? rule.requiredStatusChecks || [] : [];
      const all = rounds[Math.min(polls, rounds.length - 1)].checks.map(check => ({
        __typename: 'CheckRun', databaseId: check.id,
        isRequired: specifications.some(r => r.context === check.name && (!r.app || check.app?.id === r.app.databaseId)),
      }));
      all.push(...(options.statuses || []).map(status => ({__typename: 'StatusContext', context: status.context,
        isRequired: specifications.some(r => r.context === status.context && !r.app)})));
      const nodes = options.paginated ? (args.cursor ? all.slice(4) : all.slice(0, 4)) : all;
      return {repository: {pullRequest: {headRefOid: options.policyHead || 'head',
        baseRef: {refUpdateRule: rule ? {requiredStatusCheckContexts: specifications.map(r => r.context)} : null},
        commits: {nodes: [{commit: {statusCheckRollup: {contexts: {nodes,
          pageInfo: options.pageInfo || {hasNextPage: !!options.paginated && !args.cursor, endCursor: args.cursor ? null : 'rest'},
        }}}}]},
      }}};
    },
    paginate: async (fn, args) => {
      assert.equal(args.head_sha || args.ref, 'head');
      return fn(args);
    },
  };
  await wait(github, {eventName: options.eventName || 'workflow_run', repo: {owner: 'owner', repo: 'repo'}, payload: {pull_request: {number: 61, head: {sha: 'head'}}}},
    {notice() {}, info() {}, setOutput: (key, value) => ready.push([key, value]), setFailed: text => failures.push(text)},
    {now: () => now}, callback => {now += 60000; callback();}, {env: {REVIEW_PR: '61', REVIEW_HEAD: 'head'}});
  return {ready, failures, queries, polls, elapsed: now};
}

test('all eight required shards pass despite failed optional Watch and pending approval', async () => {
  const result = await run({checks: [...required.map(r => check(r.context)),
    check('Build exact simulator products once for five fresh pairs', 'failure'),
    check('review', 'failure'), check('Tier-B approval', 'failure')]});
  assert.deepEqual(result.ready, [['ready', 'true']]);
  assert.deepEqual(result.failures, []);
});

test('a PR event with pending CI frees its runner without polling', async () => {
  const pending = required.map(r => check(r.context));
  pending[7].status = 'in_progress';
  const result = await run({eventName: 'pull_request', checks: pending});
  assert.deepEqual(result.ready, []);
  assert.deepEqual(result.failures, []);
  assert.equal(result.elapsed, 0);
  assert.equal(result.polls, 1);
});

test('completion events allow at most five minutes for trailing checks', async () => {
  const pending = required.map(r => check(r.context));
  pending[7].status = 'in_progress';
  const result = await run({checks: pending});
  assert.deepEqual(result.ready, []);
  assert.match(result.failures[0], /Timed out after 5 minutes/);
  assert.equal(result.elapsed, 5 * 60 * 1000);
});

test('the job keeps time for setup and review after the short tail', () => {
  assert.match(workflow, /timeout-minutes: 40/);
  assert.match(workflow, /workflows: \[CI\]/);
  assert.match(workflow, /types: \[completed\]/);
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
  assert.match(workflow, /checks: write/);
  assert.match(workflow, /anthropics\/claude-code-action@v1\n        if: steps.ci.outputs.ready == 'true'/);
  for (const command of ['cd:*', 'python -m pytest:*', 'python3 -m pytest:*', 'echo:*', 'tail:*']) {
    assert.ok(workflow.includes(`Bash(${command})`), command);
  }
  assert.ok(!workflow.includes('Bash(python3:*)'));
  assert.ok(!workflow.includes('--dangerously-skip-permissions'));
});


test('native non-admin required-check discovery reads later pages before approving', async () => {
  const checks = required.map((r, i) => check(r.context, i === 7 ? 'failure' : 'success'));
  const result = await run({checks, paginated: true});
  assert.deepEqual(result.ready, []);
  assert.match(result.failures[0], /backend-tests \(8\)/);
  assert.equal(result.queries, 2);
});

test('truncated and repeating required-check pages refuse without reviewing', async () => {
  await assert.rejects(run({pageInfo: {hasNextPage: true, endCursor: null}}), /incomplete/);
  await assert.rejects(run({pageInfo: {hasNextPage: true, endCursor: 'same'}}), /repeated/);
});

const selectSource = workflow.match(/      - name: Resolve the current eligible PR[\s\S]*?          script: \|\n([\s\S]*?)(?=      - name: Wait)/)[1];
const select = new (Object.getPrototypeOf(async function(){}).constructor)('github', 'context', 'core', selectSource);
async function resolve(options = {}) {
  const output = {}, calls = [];
  const pr = {number: 61, state: 'open', draft: false, labels: [{name: 'tier-b'}],
    head: {sha: 'head', ref: 'codex/example', repo: {full_name: 'owner/repo'}}, ...options.pr};
  const run = {name: 'CI', path: '.github/workflows/ci.yml', event: 'pull_request',
    status: 'completed', conclusion: 'success', head_sha: 'head',
    head_repository: {full_name: 'owner/repo'}, ...options.run};
  const api = {repos: {listPullRequestsAssociatedWithCommit: async () => {
    calls.push('associated'); return options.associated || [pr];
  }}, pulls: {get: async () => ({data: pr}), listReviews: async () => {
    calls.push('reviews'); return options.reviews || [];
  }}};
  await select({rest: api, paginate: (fn, args) => fn(args)},
    {repo: {owner: 'owner', repo: 'repo'}, eventName: options.eventName || 'workflow_run',
      payload: {action: 'completed', workflow_run: run, pull_request: {number: 61, head: {sha: 'head'}}}},
    {setOutput: (k, v) => {output[k] = v;}});
  return {output, calls};
}

test('completed trusted CI resolves the current PR by its exact head', async () => {
  assert.deepEqual((await resolve()).output, {number: '61', head: 'head', branch: 'codex/example'});
  assert.equal((await resolve({eventName: 'pull_request'})).output.head, 'head');
});

test('forks, drafts, non-tier-b and moved heads never reach the action', async () => {
  for (const pr of [{draft: true}, {labels: []}, {state: 'closed'},
    {head: {sha: 'head', repo: {full_name: 'fork/repo'}}},
    {head: {sha: 'new', repo: {full_name: 'owner/repo'}}}]) {
    const result = await resolve({pr});
    assert.deepEqual(result.output, {});
    assert.ok(!result.calls.includes('reviews'));
  }
  assert.deepEqual((await resolve({run: {head_repository: {full_name: 'fork/repo'}}})).calls, []);
});

test('unrelated, unsuccessful, incomplete and ambiguous CI cannot invoke review', async () => {
  for (const run of [{name: 'other'}, {path: 'other.yml'}, {event: 'push'},
    {conclusion: 'failure'}, {status: 'in_progress'}]) {
    assert.deepEqual((await resolve({run})).output, {});
  }
  assert.deepEqual((await resolve({associated: []})).output, {});
});

test('a submitted exact-head bot verdict suppresses duplicate paid review', async () => {
  for (const state of ['APPROVED', 'CHANGES_REQUESTED']) {
    assert.deepEqual((await resolve({reviews: [{user: {login: 'claude[bot]'}, commit_id: 'head', state}]})).output, {});
  }
  assert.equal((await resolve({reviews: [{user: {login: 'claude[bot]'}, commit_id: 'old', state: 'APPROVED'}]})).output.head, 'head');
});

test('completion review preserves the native cap and trusted current-head policy publication', () => {
  assert.match(workflow, /startsWith\(steps.select.outputs.branch, 'codex\/eval-reviewer-'\) && '--max-budget-usd 0.40'/);
  assert.match(workflow, /ref: \$\{\{ github.workflow_sha \}\}/);
  assert.match(workflow, /path: _tier_b_policy/);
  assert.match(workflow, /Publish the current-head approval verdict\n        if: always\(\) && steps.policy.conclusion == 'success'/);
  assert.match(workflow, /require\('\.\/_tier_b_policy\/tools\/release\/tier_b.cjs'\)\.evaluate/);
  const policy = fs.readFileSync(path.resolve(__dirname, '../../../.github/workflows/tier-b.yml'), 'utf8');
  assert.match(policy, /github.event_name != 'workflow_run' \|\| github.event.workflow_run.event == 'pull_request'/);
});
