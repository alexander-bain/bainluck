const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseRequest, configuration, configure, REVIEW_MARKER} = require('../../tools/release/reviewer_eval_comment.cjs');

const head = 'a'.repeat(40);
function context(number = 12169) {
  return {eventName: 'issue_comment', actor: 'alexander-bain',
    repo: {owner: 'alexander-bain', repo: 'bainluck'},
    payload: {issue: {number, pull_request: {}},
      comment: {body: `@claude\n<!-- reviewer-eval-11951 head:${head} -->`}}};
}
function pr(number = 12169) {
  const request = parseRequest(context(number));
  return {number, state: 'open', draft: false, user: {login: 'alexander-bain'},
    labels: [{name: 'tier-b'}], head: {sha: head, ref: request.branch,
      repo: {full_name: 'alexander-bain/bainluck'}}};
}

test('ordinary @claude requests keep the existing command', async () => {
  const c = context(); c.payload.comment.body = '@claude review this';
  assert.equal(await configure({}, c), null);
});

test('the command reads this PR and all its reviews before deciding to spend', async () => {
  const calls = [];
  const github = {rest: {pulls: {get: async args => {
    calls.push(args); return {data: pr()};
  }, listReviews: () => {}}}, paginate: async (_fn, args) => {
    calls.push(args); return [];
  }};
  const result = await configure(github, context());
  assert.equal(result.head, head);
  assert.deepEqual(calls, [
    {owner: 'alexander-bain', repo: 'bainluck', pull_number: 12169},
    {owner: 'alexander-bain', repo: 'bainluck', pull_number: 12169, per_page: 100},
  ]);
});

test('each of the fifteen registered inputs gets a capped, comment-only semantic review', () => {
  for (let number = 12169; number <= 12183; number++) {
    const request = parseRequest(context(number));
    const result = configuration(request, pr(number), []);
    assert.equal(result.skip, false);
    assert.equal(result.head, head);
    assert.match(result.args, /--model claude-sonnet-5-5 /);
    assert.match(result.args, /--max-budget-usd 0\.40$/);
    assert.match(result.args, /--tools Read,Grep,Glob,Bash /);
    assert.ok(result.args.includes(`Bash(gh pr review ${number} --comment:*)`));
    assert.ok(!result.args.includes('Bash(gh pr review:*)'));
    assert.ok(result.prompt.includes(head));
    assert.ok(result.prompt.includes(REVIEW_MARKER));
    assert.ok(result.prompt.includes('CI failure alone is not a semantic finding'));
  }
});

test('an unauthorized, malformed or out-of-study trigger cannot reach inference', async () => {
  const cases = [];
  for (const number of [12168, 12184, 12228]) cases.push(context(number));
  const other = context(); other.actor = 'somebody-else'; cases.push(other);
  const issue = context(); delete issue.payload.issue.pull_request; cases.push(issue);
  const event = context(); event.eventName = 'pull_request_review_comment'; cases.push(event);
  const missing = context(); missing.payload.comment.body = '@claude\n<!-- reviewer-eval-11951 -->'; cases.push(missing);
  const twice = context(); twice.payload.comment.body += `\n<!-- reviewer-eval-11951 head:${head} -->`; cases.push(twice);
  for (const c of cases) {
    let calls = 0;
    const github = {rest: {pulls: {get: async () => {calls++; throw Error('must not fetch');}}}};
    await assert.rejects(configure(github, c));
    assert.equal(calls, 0);
  }
});

test('a moved head, fork, wrong branch or changed eligibility stops the paid command', () => {
  for (const change of [
    p => p.head.sha = 'b'.repeat(40), p => p.head.repo.full_name = 'other/bainluck',
    p => p.head.ref = 'master', p => p.state = 'closed', p => p.draft = true,
    p => p.user.login = 'other', p => p.labels = [], p => p.number = 12170,
  ]) {
    const p = pr(); change(p);
    assert.throws(() => configuration(parseRequest(context()), p, []));
  }
});

test('the serialized second request skips a completed review at this exact head', () => {
  for (const review of [
    {state: 'COMMENTED', body: `${REVIEW_MARKER}\nHead: ${head}`},
    {state: 'APPROVED'}, {state: 'CHANGES_REQUESTED'},
  ]) {
    const r = {...review, user: {login: 'claude[bot]'}, commit_id: head};
    assert.deepEqual(configuration(parseRequest(context()), pr(), [r]), {skip: true});
    if (review.state === 'COMMENTED') {
      assert.deepEqual(configuration(parseRequest(context()), pr(), [
        {...r, user: {login: 'github-actions[bot]'}},
      ]), {skip: true});
    }
    assert.equal(configuration(parseRequest(context()), pr(), [{...r, commit_id: 'old'}]).skip, false);
    assert.equal(configuration(parseRequest(context()), pr(), [{...r, user: {login: 'human'}}]).skip, false);
  }
});

test('a native advisory COMMENT never earns the product approval check', () => {
  const {verdict} = require('../../tools/release/tier_b.cjs');
  assert.equal(verdict(pr(), [{id: 1, user: {login: 'claude[bot]'},
    state: 'COMMENTED', commit_id: head, body: `${REVIEW_MARKER}\nAdvisory verdict: APPROVE`}]).conclusion, 'failure');
});
