// #12539 / 119-A (Alex, Nov 10): Fable's ACCEPT is needed only for PRs that are
// reader-visible, destructive or touch evals and gates. Every other tier-b PR
// merges on claude[bot]'s approval at its head and green CI. The PR's first line
// declares which, and a `Fable: not needed` PR that touches a listed path is
// blocked with the paths named.
//
// TIER_B_FILE points these tests at another copy of the evaluator (used to show
// they fail on the pre-119-A policy).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const file = process.env.TIER_B_FILE || path.resolve(__dirname, '../../tools/release/tier_b.cjs');
const policy = () => require(file);
const repoRoot = path.resolve(__dirname, '../..');

const APPROVED = [{id: 1, user: {login: 'claude[bot]'}, state: 'APPROVED', commit_id: 'head'}];
const pr = body => ({number: 7, state: 'open', user: {login: 'author'}, head: {sha: 'head'},
  labels: [{name: 'tier-b'}], body});

test('the first line is read as the declaration', () => {
  const {fableLine} = policy();
  assert.equal(fableLine('Fable: not needed\n\nTests only.'), 'not needed');
  assert.equal(fableLine('\n\n  fable: Not Needed (alarm wording)'), 'not needed');
  assert.equal(fableLine('**Fable: needed (reader-visible)**'), 'needed');
  assert.equal(fableLine('Fable: needed (eval)'), 'needed');
  assert.equal(fableLine('## Summary\nFable: not needed'), 'missing');
  assert.equal(fableLine(''), 'missing');
  assert.equal(fableLine(null), 'missing');
});

test('a `not needed` PR touching a reader path is blocked, even with the bot approval', () => {
  const {verdict} = policy();
  const result = verdict(pr('Fable: not needed'), APPROVED,
    [{filename: 'backend/tests/test_x.py'}, {filename: 'frontend/components/DiscoverCard.tsx'}]);
  assert.equal(result.conclusion, 'failure');
  assert.match(result.summary, /frontend\/components\/DiscoverCard\.tsx \(reader-visible/);
  assert.match(result.summary, /Fable: needed/);
  assert.doesNotMatch(result.summary, /test_x\.py/);
});

test('a `not needed` tests-only PR passes on the bot approval, with no Fable ACCEPT asked', () => {
  const {verdict} = policy();
  const files = ['backend/tests/test_x.py', 'frontend/components/__tests__/Card.test.tsx',
    'frontend/e2e/flow.spec.ts', 'docs/notes.md'].map(filename => ({filename}));
  const result = verdict(pr('Fable: not needed'), APPROVED, files);
  assert.equal(result.conclusion, 'success');
  assert.match(result.summary, /merges after green CI\.$/);
  assert.doesNotMatch(result.summary, /Fable ACCEPT at this head is needed|and Fable ACCEPT/);
});

test('a `needed` PR and a PR with no line both still ask for Fable', () => {
  const {verdict} = policy();
  assert.match(verdict(pr('Fable: needed (eval)'), APPROVED, []).summary, /Fable ACCEPT at this head/);
  const missing = verdict(pr('## Summary'), APPROVED, []);
  assert.equal(missing.conclusion, 'success');
  assert.match(missing.summary, /no `Fable:` first line, so Fable ACCEPT at this head is needed/);
});

test('without the bot approval nothing passes, whatever the line says', () => {
  const {verdict} = policy();
  for (const body of ['Fable: not needed', 'Fable: needed (destructive)', '']) {
    assert.equal(verdict(pr(body), [], []).conclusion, 'failure');
  }
});

test('every 119-A category is on the list, and alarms, tests and docs are not', () => {
  const {fableHits} = policy();
  for (const name of [
    'frontend/app/discover/page.tsx', 'frontend/lib/format.ts', 'ios/Bain Luck/Views/X.swift',
    'ios/Bain Luck/BainLuckWatch/Y.swift', 'backend/app/routes/events.py', 'backend/app/routes/admin_teams.py',
    'backend/app/utils/live_blend.py', 'backend/app/utils/feed_reasons.py', 'backend/app/utils/aggregation.py',
    'backend/app/services/event_registry.py', 'backend/app/tasks/prediction_market_matching.py',
    'backend/data/containers/nfl.json', 'backend/data/evals/sibling.json', 'backend/tests/evals/test_x.py',
    'tools/release/tier_b.cjs', '.github/workflows/ci.yml', 'docs/release-loop/tier-b-review-brief.md',
    'backend/alembic/versions/abc_add.py', 'backend/app/models/models.py',
    'backend/app/tasks/repair_golf_round_closing_line.py', 'backend/scripts/restore_7501_clubs.py',
  ]) assert.equal(fableHits([{filename: name}]).length, 1, name);
  for (const name of [
    'backend/tests/test_team_merge.py', 'frontend/__tests__/Card.test.tsx', 'docs/notes.md',
    'backend/app/tasks/watchdog.py', 'backend/app/tasks/horizon_sentinel.py',
    'backend/app/tasks/grid_sentinel.py', 'CLAUDE.md',
  ]) assert.equal(fableHits([{filename: name}]).length, 0, name);
});

test('files are read only to test a `not needed` claim', async () => {
  const {evaluate} = policy();
  for (const [body, reads] of [['Fable: not needed', 1], ['Fable: needed (eval)', 0], ['', 0]]) {
    let files = 0;
    const created = [];
    const current = pr(body);
    const github = {rest: {pulls: {}, checks: {}}, paginate: async (fn, args) => fn(args)};
    github.rest.pulls.get = async () => ({data: {...current}});
    github.rest.pulls.listReviews = async () => APPROVED;
    github.rest.pulls.listFiles = async () => { files++; return [{filename: 'ios/Bain Luck/X.swift'}]; };
    github.rest.checks.listForRef = async () => [];
    github.rest.checks.create = async c => created.push(c);
    await evaluate(github, {repo: {owner: 'o', repo: 'r'}, eventName: 'pull_request_target',
      payload: {pull_request: {number: 7}}});
    assert.equal(files, reads, body || '(no line)');
    assert.equal(created.at(-1).conclusion, body === 'Fable: not needed' ? 'failure' : 'success');
  }
});

test('the PR template opens with the declaration', () => {
  const template = fs.readFileSync(path.join(repoRoot, '.github/PULL_REQUEST_TEMPLATE.md'), 'utf8');
  assert.match(template.split('\n')[0], /^Fable: (needed \(reader-visible \| destructive \| eval\)|not needed)/);
});

test('the docs and the bot brief state 119-A, not the old every-PR rule', () => {
  const claude = fs.readFileSync(path.join(repoRoot, 'CLAUDE.md'), 'utf8');
  const brief = fs.readFileSync(path.join(repoRoot, 'docs/release-loop/tier-b-review-brief.md'), 'utf8');
  for (const text of [claude, brief]) {
    assert.match(text, /119-A/);
    assert.doesNotMatch(text, /Tier B and policy: claude\[bot\] at head \+ Fable ACCEPT/);
  }
  assert.match(brief, /`Fable: not needed`/);
});
