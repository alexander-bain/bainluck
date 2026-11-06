"""Run the native workflow's admission/control/merge-policy checks in CI."""

from pathlib import Path
import json
import subprocess

import yaml


def test_eval_candidates_bypass_ci_without_authorizing_a_merge():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "node",
            "--test",
            "tests/release/reviewer_eval_candidate.test.cjs",
            "tests/release/tier_b.test.cjs",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_actual_ci_job_graph_queues_no_runner_for_an_eval_candidate():
    """Include jobs with explicit status functions, which bypass skipped needs."""
    root = Path(__file__).resolve().parents[2]
    jobs = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const jobs = JSON.parse(fs.readFileSync(0, 'utf8'));
function queued(labels, eventName = 'pull_request') {
  const github = {event_name: eventName,
    ref: eventName === 'push' ? 'refs/heads/master' : 'refs/pull/12169/merge',
    event: {pull_request: {labels: labels.map(name => ({name}))}}};
  const states = {}, selected = [];
  for (const [name, job] of Object.entries(jobs)) {
    const dependencies = typeof job.needs === 'string' ? [job.needs] : job.needs || [];
    const needs = Object.fromEntries(dependencies.map(id => [id, {result: states[id], outputs: {}}]));
    const parentsPassed = dependencies.every(id => states[id] === 'success');
    let expression = String(job.if ?? 'true').replace(/^\$\{\{\s*|\s*\}\}$/g, '')
      .replaceAll('github.event.pull_request.labels.*.name',
        'github.event.pull_request.labels.map(label => label.name)')
      .replace(/needs\.([a-z][a-z0-9-]*)/g, (_, id) => `needs[${JSON.stringify(id)}]`);
    const explicitStatus = /\b(?:always|cancelled|success|failure)\(/.test(expression);
    const enabled = (explicitStatus || parentsPassed) && Boolean(
      new Function('github', 'needs', 'contains', 'startsWith', 'cancelled', 'always', 'success',
        `return (${expression})`)(github, needs, (list, value) => list.includes(value),
          (value, prefix) => value.startsWith(prefix), () => false, () => true, () => parentsPassed));
    states[name] = enabled ? 'success' : 'skipped';
    if (enabled) selected.push(name);
  }
  return selected;
}
assert.deepEqual(queued(['tier-b', 'eval-candidate']), []);
const ordinary = queued(['tier-b']);
for (const name of ['change-scope', 'backend-tests', 'database-integration', 'frontend-build', 'search-recall'])
  assert.ok(ordinary.includes(name), `${name} disappeared from ordinary PR CI`);
assert.ok(!ordinary.includes('deploy'));
assert.ok(queued([], 'push').includes('deploy'), 'master pushes retain their release path');
"""
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(jobs),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
