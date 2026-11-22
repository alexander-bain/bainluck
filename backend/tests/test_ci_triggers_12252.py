"""#12252 (79-B part A, item 1): CI runs only for events that change the commit.

Nov 6: 169 of 360 PR runs were re-triggers on an UNCHANGED commit. CI fired on
`labeled`, `unlabeled` and `edited`, so `gh pr create --label` started two runs in
one second (the cancelled one blocked the merge, #12220) and a description edit
re-ran the suite and cancelled the run in flight.

Why the events are gone and not filtered (Fable, Nov 7): a run that skips every job
still creates check runs named `change-scope`, `fast-gate`, `frontend-build`, … with
conclusion `skipped`, and a skipped job is a PASSING required check. A label or an
edit after a red real run could land a skipped result on the same commit. With no
trigger there is no run object at all, so no required context can go green by skip.

Evaluated, not read, for the parts that still matter: the job graph and the
concurrency expressions are run against each remaining event shape by a small
evaluator (the approach of test_eval_candidate_workflow_12235.py).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or ROOT / ".github" / "workflows" / "ci.yml")

FULL = ["change-scope", "fast-gate", "backend-tests", "database-integration", "frontend-build", "search-recall"]

EVALUATOR = r"""
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
function shape(action, labels = ['tier-b']) {
  return action === 'push'
    ? {event_name: 'push', ref: 'refs/heads/master', run_id: 42, event: {pull_request: {labels: []}}}
    : {event_name: 'pull_request', ref: 'refs/pull/777/merge', run_id: 42,
       event: {action, pull_request: {number: 777, labels: labels.map(name => ({name}))}}};
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
  return selected;
}
const out = {};
for (const [k, g] of Object.entries({
  opened: shape('opened'), synchronize: shape('synchronize'), reopened: shape('reopened'),
  eval_synchronize: shape('synchronize', ['tier-b', 'eval-candidate']), push: shape('push'),
})) out[k] = {selected: queued(g),
              slot: [evaluate(wf.concurrency.group, g), Boolean(evaluate(wf.concurrency['cancel-in-progress'], g))]};
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


def test_only_events_that_change_the_commit_trigger_a_pull_request_run():
    assert _workflow()["on"]["pull_request"]["types"] == ["opened", "synchronize", "reopened"]


def test_no_condition_is_left_reading_an_event_that_can_no_longer_arrive():
    """Dead branches for `labeled`/`edited` would read as if those events still ran."""
    text = CI.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"github\.event\.action\s*==\s*'(?:labeled|unlabeled|edited)'", code)
    assert "github.event.changes" not in code and "github.event.label.name" not in code


def test_a_commit_runs_everything_and_supersedes_the_older_run():
    out = _run()
    for case in ("opened", "synchronize", "reopened"):
        for job in FULL:
            assert job in out[case]["selected"], (case, job)
        assert out[case]["slot"] == ["ci-pr-777", True], (case, out[case]["slot"])


def test_an_eval_candidate_pr_still_queues_nothing_on_its_next_commit():
    out = _run()
    assert out["eval_synchronize"]["selected"] == []


def test_master_pushes_keep_their_release_path_and_group():
    out = _run()
    assert "deploy" in out["push"]["selected"]
    assert out["push"]["slot"] == ["ci-push-refs/heads/master", False]
