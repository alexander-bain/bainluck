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
    'backend/app/utils/kalshi_threshold_label.py',
    'backend/app/services/event_registry.py', 'backend/app/tasks/prediction_market_matching.py',
    'backend/data/containers/nfl.json', 'backend/data/evals/sibling.json', 'backend/tests/evals/test_x.py',
    'tools/release/tier_b.cjs', '.github/workflows/ci.yml', 'docs/release-loop/tier-b-review-brief.md',
    'backend/alembic/versions/abc_add.py', 'backend/app/models/models.py',
    'backend/app/tasks/repair_golf_round_closing_line.py', 'backend/scripts/restore_7501_clubs.py',
  ]) assert.equal(fableHits([{filename: name}]).length, 1, name);
  for (const name of [
    'backend/tests/test_team_merge.py', 'frontend/__tests__/Card.test.tsx', 'docs/notes.md',
    'backend/app/tasks/watchdog.py', 'backend/app/tasks/horizon_sentinel.py',
    'backend/app/tasks/grid_sentinel.py', 'backend/app/utils/issue_labels.py', 'CLAUDE.md',
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

// Fable's review of #12543 (Nov 10): pinned on real PRs from that day.
const PR_12536 = ['backend/app/utils/grouping_licences.py', 'backend/app/utils/roundup_containers.py',
  'backend/app/utils/sibling_family.py', 'backend/app/utils/sibling_family_exam.py',
  'backend/app/utils/sibling_family_proposer.py', 'backend/data/containers/nhl-playoffs-2026-27.json',
  'backend/data/discover/sibling-family-exam-dataset-2026-11.json', 'backend/data/grouping_licences.json',
  'frontend/components/evals/SiblingFamilyExamSection.tsx', 'frontend/lib/evals/data/sibling-family-exam-2026-11.json'];
const PR_12520 = ['backend/app/routes/admin_team_clusters.py', 'backend/app/utils/team_merge.py'];
// #12542's tasks/__init__.py is listed: it holds update_max_movement (Fable, #12543).
const PR_12542 = ['backend/app/tasks/task_memory.py',
  'backend/tests/test_task_memory_worker_background_12042.py'];
const PR_12546 = ['backend/app/utils/latency_stats.py', 'backend/app/utils/request_timing.py',
  'backend/tests/test_slow_ring_names_its_query_12529.py'];

test('every app and data file of #12536 (grouped cards, the exam) and #12520 (the merge tool) is listed', () => {
  const {fableHits} = policy();
  for (const name of [...PR_12536, ...PR_12520]) assert.equal(fableHits([name]).length, 1, name);
});

test('the instrumentation files of #12542 and #12546 are not listed; tasks/__init__.py is', () => {
  const {fableHits} = policy();
  for (const name of [...PR_12542, ...PR_12546]) assert.equal(fableHits([name]).length, 0, name);
  assert.equal(fableHits(['backend/app/tasks/__init__.py']).length, 1);
});

test('the house names for repair scripts are destructive', () => {
  const {fableHits} = policy();
  for (const name of ['backend/scripts/fix_orphan_markets.py', 'backend/scripts/seed_teams.py',
    'backend/scripts/populate_slugs.py', 'backend/scripts/ingest_archive.py', 'backend/scripts/import_grades.py',
    'backend/scripts/reconcile_links.py', 'backend/scripts/settle_props.py', 'backend/scripts/cleanup_old.py',
    'backend/scripts/dedup_events.py', 'backend/scripts/prune_rows.py',
    'backend/cleanup_soccer.py', 'backend/deduplicate_snapshots.py'])
    assert.equal(fableHits([name]).length, 1, name);
  assert.equal(fableHits(['backend/scripts/probe_kalshi_retention.py']).length, 0);
});

test('the backend default is flipped: unlisted names need Fable unless they say plumbing', () => {
  const {fableHits} = policy();
  for (const name of ['backend/app/utils/discover_final_seating.py', 'backend/app/utils/calibration_publish_gate.py',
    'backend/app/tasks/precompute_calibration.py', 'backend/app/tasks/prune_unanchored_duplicates.py',
    'backend/app/services/team_identity.py', 'backend/app/utils/live_push.py',
    'backend/app/services/activitykit_push.py', 'backend/app/routes/admin_alerts.py',
    'tools/ranking/scorecard.py', 'tools/reader_walk/walk.py', 'backend/scripts/awards_event_identity_indexes_11935.sql',
    'frontend/next.config.mjs', 'frontend/tailwind.config.ts', 'frontend/vercel.json',
    'docs/discover/sibling-family-exam-2026-11.md', 'backend/tests/test_matching_golden_set_2706.py'])
    assert.equal(fableHits([name]).length, 1, name);
  for (const name of ['backend/app/tasks/calibration_sentinel.py', 'backend/app/tasks/data_quality_watchdog.py',
    'backend/app/tasks/sentinel_filing.py', 'backend/app/tasks/bug_report_github.py', 'backend/app/log_redaction.py',
    'backend/app/tasks/heavy_memory_turns.py', 'backend/app/tasks/calibration_beat_gauge_sampler.py'])
    assert.equal(fableHits([name]).length, 0, name);
});

test('a rename is judged by both names', () => {
  const {fableHits} = policy();
  assert.equal(fableHits([{filename: 'docs/old/seat.py', previous_filename: 'backend/app/utils/discover_final_seating.py'}]).length, 1);
  assert.equal(fableHits([{filename: 'docs/notes.md', previous_filename: 'docs/old.md'}]).length, 0);
});

test('the bot brief says who accepts a PR Fable wrote (122-A)', () => {
  const brief = fs.readFileSync(path.join(repoRoot, 'docs/release-loop/tier-b-review-brief.md'), 'utf8');
  assert.match(brief.replace(/\s+/g, ' '), /A PR that Fable wrote is accepted by the lane its test judges \(an "OK at <head>" on the PR\) and merged by Builder E/);
  assert.match(brief, /122-A/);
});

test('iOS test targets are not reader-visible; the app and the Watch app are (#12553)', () => {
  const {fableHits} = policy();
  for (const name of [
    'ios/Bain Luck/BainLuckTests/ALiveHeroCarriesTheStoryNotTheContext8320Tests.swift',
    'ios/Bain Luck/BainLuckTests/OddsChartNoReadingsTests.swift',
    'ios/Bain Luck/BainLuckUITests/DiscoverUITests.swift',
    'ios/Bain Luck/BainLuckWatchUITests/WatchUITests.swift',
  ]) assert.equal(fableHits([name]).length, 0, name);
  for (const name of [
    'ios/Bain Luck/Bain Luck/Views/EventDetailView.swift',
    'ios/Bain Luck/BainLuckWatch Watch App/ContentView.swift',
    'ios/Bain Luck/BainLuckWidget/SavedItemControl12305.swift',
    'ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj',
  ]) assert.equal(fableHits([name]).length, 1, name);
});
