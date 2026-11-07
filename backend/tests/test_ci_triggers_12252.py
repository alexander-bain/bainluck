"""#12252 (79-B part A, item 1): CI runs only for events that change what is tested.

Nov 6: 169 of 360 PR runs were re-triggers on an UNCHANGED commit. CI fired on
`labeled`, `unlabeled` and `edited`, so `gh pr create --label` started two runs in
one second (and the cancelled one blocked the merge), and a description edit
re-ran the suite and cancelled the run in flight.

Evaluated, not read: the job graph and the concurrency expressions in ci.yml are
run against each event shape by a small evaluator (the same approach as
test_eval_candidate_workflow_12235.py). Pinned here:

* `unlabeled` never triggers; a label other than `eval-candidate`, or an edit
  that does not change the base, queues NO job and sits in its own concurrency
  group, so it can never cancel the real run;
* opened / synchronize / reopened / a base change run everything, superseding
  the PR's older run as before; an `eval-candidate` label still cancels the
  full run and queues nothing (#12235);
* green-by-skip is impossible: in a no-op run `backend-tests` is skipped at the
  JOB level, so its matrix never expands and the required `backend-tests (N)`
  contexts can only come from a real run on that commit.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or ROOT / ".github" / "workflows" / "ci.yml")

FULL = ["change-scope", "fast-gate", "backend-tests", "database-integration", "frontend-build", "search-recall"]

EVALUATOR = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const wf = JSON.parse(fs.readFileSync(0, 'utf8'));
const jobs = wf.jobs;
function evaluate(expr, github, needs = {}, parentsPassed = true) {
  let e = String(expr ?? 'true').replace(/^\$\{\{\s*|\s*\}\}$/g, '')
    .replaceAll('github.event.pull_request.labels.*.name', 'github.event.pull_request.labels.map(l => l.name)')
    .replace(/needs\.([a-z][a-z0-9-]*)/g, (_, id) => `needs[${JSON.stringify(id)}]`);
  return new Function('github', 'needs', 'contains', 'startsWith', 'format', 'cancelled', 'always', 'success',
    `return (${e})`)(github, needs, (list, v) => list.includes(v), (v, p) => String(v).startsWith(p),
      (f, ...a) => f.replace(/\{(\d+)\}/g, (_, i) => a[+i]), () => false, () => true, () => parentsPassed);
}
function shape(action, extra = {}) {
  const labels = (extra.labels || ['tier-b']).map(name => ({name}));
  const event = {action, pull_request: {number: 777, labels}, ...(extra.changes ? {changes: extra.changes} : {}),
                 ...(extra.label ? {label: {name: extra.label}} : {})};
  return extra.push
    ? {event_name: 'push', ref: 'refs/heads/master', run_id: 42, event: {pull_request: {labels: []}, changes: {}, label: {}}}
    : {event_name: 'pull_request', ref: 'refs/pull/777/merge', run_id: 42, event};
}
function queued(github) {
  const states = {}, selected = [];
  for (const [name, job] of Object.entries(jobs)) {
    const deps = typeof job.needs === 'string' ? [job.needs] : job.needs || [];
    const needs = Object.fromEntries(deps.map(id => [id, {result: states[id], outputs: {}}]));
    const parentsPassed = deps.every(id => states[id] === 'success');
    const explicit = /\b(?:always|cancelled|success|failure)\(/.test(String(job.if ?? ''));
    const enabled = (explicit || parentsPassed) && Boolean(evaluate(job.if, github, needs, parentsPassed));
    states[name] = enabled ? 'success' : 'skipped';
    if (enabled) selected.push(name);
  }
  return {selected, states};
}
function slot(github) {
  return [evaluate(wf.concurrency.group, github), Boolean(evaluate(wf.concurrency['cancel-in-progress'], github))];
}
const cases = {
  opened: shape('opened'), synchronize: shape('synchronize'), reopened: shape('reopened'),
  base_change: shape('edited', {changes: {base: {ref: {from: 'lane1/q362'}, sha: {from: 'abc'}}}}),
  body_edit: shape('edited', {changes: {body: {from: 'old'}}}),
  title_edit: shape('edited', {changes: {title: {from: 'old'}}}),
  label_tier_b: shape('labeled', {label: 'tier-b'}),
  label_other: shape('labeled', {label: 'priority:p1', labels: ['tier-b', 'priority:p1']}),
  label_eval: shape('labeled', {label: 'eval-candidate', labels: ['tier-b', 'eval-candidate']}),
  push: shape(null, {push: true}),
};
const out = {};
for (const [k, g] of Object.entries(cases)) out[k] = {...queued(g), slot: slot(g)};
process.stdout.write(JSON.stringify(out));
"""


def _workflow() -> dict:
    wf = yaml.safe_load(CI.read_text())
    wf["on"] = wf.get("on", wf.get(True))
    wf.pop(True, None)
    return wf


def _run() -> dict:
    result = subprocess.run(
        ["node", "-e", EVALUATOR], input=json.dumps(_workflow()), capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_the_triggers_are_the_reviewed_five():
    assert _workflow()["on"]["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "labeled",
        "edited",
    ]


def test_a_label_or_a_title_or_body_edit_queues_nothing_and_cancels_nothing():
    out = _run()
    for case in ("body_edit", "title_edit", "label_tier_b", "label_other"):
        assert out[case]["selected"] == [], (case, out[case]["selected"])
        group, cancel = out[case]["slot"]
        assert group == "ci-noop-42" and cancel is False, (case, out[case]["slot"])


def test_a_commit_or_a_base_change_runs_everything_and_supersedes_the_older_run():
    out = _run()
    for case in ("opened", "synchronize", "reopened", "base_change"):
        for job in FULL:
            assert job in out[case]["selected"], (case, job)
        assert out[case]["slot"] == ["ci-pr-777", True], (case, out[case]["slot"])


def test_an_eval_candidate_label_still_cancels_the_full_run_and_queues_nothing():
    out = _run()
    assert out["label_eval"]["selected"] == []
    assert out["label_eval"]["slot"] == ["ci-pr-777", True]


def test_master_pushes_keep_their_release_path_and_group():
    out = _run()
    assert "deploy" in out["push"]["selected"]
    assert out["push"]["slot"] == ["ci-push-refs/heads/master", False]


def test_a_no_op_run_can_never_create_the_required_matrix_contexts():
    """Green-by-skip guard: `backend-tests (1)`..`(8)` are required contexts. In a
    no-op run the job is skipped at JOB level, which never expands the matrix, so
    those contexts exist only if a real run created them on the same commit."""
    wf = _workflow()
    shards = wf["jobs"]["backend-tests"]["strategy"]["matrix"]["shard"]
    assert shards, "backend-tests must stay a matrix job"
    out = _run()
    for case in ("body_edit", "title_edit", "label_tier_b", "label_other"):
        assert out[case]["states"]["backend-tests"] == "skipped", case
        assert out[case]["states"]["change-scope"] == "skipped", case
