const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const study = require('../../tools/release/reviewer_eval_candidate.cjs');
const {verdict, evaluate} = require('../../tools/release/tier_b.cjs');
const root = path.resolve(__dirname, '../..');
const head = 'a'.repeat(40);
const repo = {owner: 'alexander-bain', repo: 'bainluck'};

function pr(number = 12169) {
  return {number, state: 'open', draft: true, user: {login: repo.owner},
    base: {ref: 'master'}, labels: [{name: 'tier-b'}, {name: study.LABEL}],
    head: {sha: head, ref: study.registeredBranch(number), repo: {full_name: study.REPOSITORY}}};
}
function context(candidate = pr(), eventName = 'pull_request_target') {
  return {repo, actor: repo.owner, eventName,
    payload: {action: 'labeled', label: {name: study.LABEL}, pull_request: candidate}};
}

test('exactly the 45 planned case/pass branches are registered, with no answer key', () => {
  const numbers = [12132, 12150, ...Array.from({length: 43}, (_, i) => 12155 + i)];
  const branches = numbers.map(study.registeredBranch);
  assert.equal(new Set(branches).size, 45);
  for (const n of numbers) assert.equal(study.eligible(pr(n), context(pr(n)), head), true);
  for (const n of [0, 12131, 12133, 12149, 12151, 12154, 12198, 12228]) {
    assert.equal(study.registeredBranch(n), null);
  }
  assert.equal(study.registeredBranch(12132), 'codex/eval-reviewer-full-r02-p1-20261105');
  assert.equal(study.registeredBranch(12150), 'codex/eval-reviewer-full-r12-p1-20261105');
  assert.equal(study.registeredBranch(12197), 'codex/eval-reviewer-full-r16-p3-20261105');
});

test('unlabelled production PRs do not enter the study exception', () => {
  const candidate = pr(12235); candidate.labels = [{name: 'tier-b'}];
  assert.equal(study.eligible(candidate, context(candidate, 'pull_request'), head), false);
});

test('wrong author, head, branch, base, repo, state or event fails before qualification', () => {
  for (const mutate of [
    (p, c) => c.actor = 'someone-else', (p, c) => c.eventName = 'pull_request',
    (p, c) => c.payload.action = 'edited', (p, c) => c.payload.label.name = 'other',
    (p, c) => c.repo = {...repo, owner: 'fork-owner'},
    p => p.state = 'closed', p => p.draft = false, p => p.user.login = 'other',
    p => p.base.ref = 'another-branch', p => p.head.repo.full_name = 'fork/bainluck',
    p => p.head.ref = 'codex/eval-reviewer-full-r06-p2-20261105',
    p => p.head.sha = 'b'.repeat(40), p => p.number = 12235,
    p => p.labels = [{name: study.LABEL}],
  ]) {
    const candidate = pr(), c = context(candidate); mutate(candidate, c);
    assert.throws(() => study.eligible(candidate, c, head));
  }
  assert.throws(() => study.eligible(pr(), context(), 'not-a-sha'));
});

test('serialized same-head duplicate admissions skip actual or dismissed verdicts', () => {
  for (const state of ['APPROVED', 'CHANGES_REQUESTED', 'DISMISSED']) {
    const review = {user: {login: 'claude[bot]'}, commit_id: head, state};
    assert.equal(study.alreadyReviewed([review], head), true);
    assert.equal(study.alreadyReviewed([{...review, commit_id: 'older'}], head), false);
    assert.equal(study.alreadyReviewed([{...review, user: {login: repo.owner}}], head), false);
  }
});

function workflowScript(name) {
  const yaml = fs.readFileSync(path.join(root, '.github/workflows/tier-b-review.yml'), 'utf8');
  const block = yaml.split(`      - name: ${name}\n`)[1]?.split(/\n      - /)[0];
  assert.ok(block, `missing real workflow step ${name}`);
  const lines = block.split('          script: |\n')[1]?.split('\n');
  assert.ok(lines, `step ${name} has no script`);
  return lines.filter(line => line.startsWith('            ') || !line.trim())
    .map(line => line.slice(12)).join('\n');
}
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
async function runStep(name, candidate, c, ciState = 'success', reviews = []) {
  const output = {}, calls = [], failures = [], notices = [];
  const core = {setOutput: (k, v) => output[k] = v, setFailed: text => failures.push(text),
    notice: text => notices.push(text), info: () => {}};
  const github = {rest: {pulls: {get: async () => {calls.push('pr'); return {data: candidate};},
    listReviews: () => {}}, actions: {listWorkflowRunsForRepo: () => {}},
    checks: {listForRef: () => {}}, repos: {listCommitStatusesForRef: () => {}}}};
  github.paginate = async fn => {
    if (fn === github.rest.pulls.listReviews) {calls.push('reviews'); return reviews;}
    if (fn === github.rest.actions.listWorkflowRunsForRepo) {calls.push('ci-runs'); return [{id: 1, path: '.github/workflows/ci.yml', check_suite_id: 10}];}
    if (fn === github.rest.checks.listForRef) {calls.push('ci-checks'); return [{id: 2, name: 'backend-tests', status: ciState === 'pending' ? 'queued' : 'completed', conclusion: ciState, check_suite: {id: 10}}];}
    assert.fail('unexpected API read');
  };
  github.graphql = async () => {
    calls.push('required-ci-policy');
    return {repository: {pullRequest: {headRefOid: head,
      baseRef: {refUpdateRule: {requiredStatusCheckContexts: ['backend-tests', 'Tier-B approval']}},
      commits: {nodes: [{commit: {statusCheckRollup: {contexts: {nodes: [
        {__typename: 'CheckRun', databaseId: 2, isRequired: true},
      ], pageInfo: {hasNextPage: false}}}}}]}}}};
  };
  const trustedRequire = module => {
    assert.equal(module, './_review_admission/tools/release/reviewer_eval_candidate.cjs');
    calls.push('trusted-study-policy'); return study;
  };
  await new AsyncFunction('github', 'context', 'core', 'require', 'process', workflowScript(name))(
    github, c, core, trustedRequire, {env: {REVIEW_PR: String(candidate.number), REVIEW_HEAD: head,
      EVAL_CANDIDATE: study.hasLabel(candidate) ? 'true' : 'false'}});
  return {output, calls, failures, notices};
}

test('the installed selector and qualification step admit a registered draft without reading CI', async () => {
  const candidate = pr(), c = context(candidate);
  const selected = await runStep('Resolve the current eligible PR', candidate, c);
  assert.deepEqual(selected.output, {number: String(candidate.number), head, branch: candidate.head.ref, eval_candidate: 'true'});
  const qualified = await runStep('Wait for green CI at this head', candidate, c);
  assert.equal(qualified.output.ready, 'true');
  assert.deepEqual(qualified.calls, ['trusted-study-policy', 'pr', 'reviews']);
  assert.match(qualified.notices[0], /bypassed under 75-A.*\$0\.40/);
});

test('duplicate or changed study inputs cannot start the paid action through the real steps', async () => {
  const candidate = pr(), c = context(candidate);
  const reviews = [{user: {login: 'claude[bot]'}, commit_id: head, state: 'APPROVED'}];
  for (const name of ['Resolve the current eligible PR', 'Wait for green CI at this head']) {
    assert.equal((await runStep(name, candidate, c, 'success', reviews)).output.ready, undefined);
  }
  candidate.head.sha = 'b'.repeat(40);
  await assert.rejects(runStep('Wait for green CI at this head', candidate, c));
});

test('the unlabelled control still waits for its required CI, then gets the normal reviewer', async () => {
  const candidate = pr(12235); candidate.draft = false; candidate.head.ref = 'codex/12235-eval-candidate';
  candidate.labels = [{name: 'tier-b'}];
  const c = context(candidate, 'pull_request');
  const selected = await runStep('Resolve the current eligible PR', candidate, c);
  assert.equal(selected.output.eval_candidate, 'false');
  for (const state of ['failure', 'pending', 'success']) {
    const result = await runStep('Wait for green CI at this head', candidate, c, state);
    assert.equal(result.output.ready, state === 'success' ? 'true' : undefined);
    assert.ok(result.calls.includes('required-ci-policy'));
    assert.equal(result.failures.length, state === 'failure' ? 1 : 0);
    assert.ok(!result.calls.includes('trusted-study-policy'));
  }
});

test('an APPROVE on a labelled input cannot satisfy the actual merge-policy publisher', async () => {
  const candidate = pr();
  const approved = [{id: 1, user: {login: 'claude[bot]'}, state: 'APPROVED', commit_id: head}];
  assert.equal(verdict(candidate, approved).conclusion, 'failure');
  assert.equal(verdict({...candidate, labels: [{name: study.LABEL}]}, []).conclusion, 'failure');
  const published = [];
  const github = {rest: {pulls: {get: async () => ({data: candidate}), listReviews: () => {}},
    checks: {listForRef: () => {}, create: async result => published.push(result)}},
    paginate: async fn => fn === github.rest.pulls.listReviews ? approved : []};
  await evaluate(github, {...context(candidate), payload: {pull_request: {number: candidate.number}}});
  assert.equal(published.at(-1).conclusion, 'failure');
});

test('native cap, trusted policy, exact checkout and CI skip are wired in the workflows', () => {
  const review = fs.readFileSync(path.join(root, '.github/workflows/tier-b-review.yml'), 'utf8');
  const ci = fs.readFileSync(path.join(root, '.github/workflows/ci.yml'), 'utf8');
  assert.match(review, /pull_request_target:\n\s+types: \[labeled, synchronize, reopened\]/);
  assert.match(review, /ref: \$\{\{ github.workflow_sha \}\}\n\s+path: _review_admission/);
  assert.match(review, /ref: \$\{\{ steps.select.outputs.head \}\}/);
  assert.match(review, /--model claude-sonnet-5-5/);
  assert.match(review, /--max-turns 60/);
  assert.match(review, /eval_candidate == 'true'.*--max-budget-usd 0\.40/);
  assert.match(review, /cancel-in-progress: false/);
  assert.match(ci, /change-scope:\n(?:\s+#.*\n)*\s+if:.*!contains\(github.event.pull_request.labels\.\*\.name, 'eval-candidate'\)/);
  assert.match(ci, /search-recall:\n\s+needs:.*\n\s+if:.*!contains\(github.event.pull_request.labels\.\*\.name, 'eval-candidate'\)/);
});
