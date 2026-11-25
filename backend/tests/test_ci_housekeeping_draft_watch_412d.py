"""Tests for 412: D — fast-gate housekeeping, draft CI skip, and Watch MVP nightly split."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WATCH_YML = REPO_ROOT / ".github" / "workflows" / "watch-mvp.yml"
MANIFEST = REPO_ROOT / ".github" / "ci-fast-gate-housekeeping-tests.txt"
RUNNER_SCRIPT = REPO_ROOT / ".github" / "scripts" / "run_fast_gate_housekeeping.py"
CI_SHARD_SCRIPT = REPO_ROOT / "backend" / "scripts" / "ci_shard.py"

EXPECTED_CORE_HOUSEKEEPING = {
    "tests/test_mutation_guard.py",
    "tests/test_wall_clock_dated_fixtures_12252.py",
    "tests/test_tasks_wiring.py",
    "tests/test_pre_offer_gate.py",
    "tests/test_ci_cross_tier_manifest.py",
}

HEAVY_PR_JOBS = {
    "backend-tests",
    "database-integration",
    "search-recall",
    "frontend-build",
    "shard-completeness",
}

EVAL_CI_AND_WATCH = r"""
const fs = require('node:fs');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
function evalExpr(expr, github, needs = {}, parentsPassed = true) {
  let e = String(expr ?? 'true').replace(/^\$\{\{\s*|\s*\}\}$/g, '')
    .replaceAll('github.event.pull_request.labels.*.name', 'github.event.pull_request.labels.map(l => l.name)')
    .replace(/needs\.([a-z][a-z0-9-]*)/g, (_, id) => `needs[${JSON.stringify(id)}]`);
  return new Function('github', 'needs', 'contains', 'startsWith', 'format', 'cancelled', 'always', 'success',
    `return (${e})`)(
      github,
      needs,
      (list, v) => list.includes(v),
      (v, p) => String(v).startsWith(p),
      (f, ...a) => f.replace(/\{(\d+)\}/g, (_, i) => a[+i]),
      () => false,
      () => true,
      () => parentsPassed,
    );
}
function selectJobs(jobs, github, extraOutputs = {}) {
  const states = {}, selected = [];
  for (const [name, job] of Object.entries(jobs)) {
    const deps = typeof job.needs === 'string' ? [job.needs] : job.needs || [];
    const needs = Object.fromEntries(deps.map(id => [
      id,
      {result: states[id], outputs: extraOutputs[id] || {}},
    ]));
    const parentsPassed = deps.every(id => states[id] === 'success');
    const explicit = /\b(?:always|cancelled|success|failure)\(/.test(String(job.if ?? ''));
    const enabled = (explicit || parentsPassed) && Boolean(evalExpr(job.if, github, needs, parentsPassed));
    states[name] = enabled ? 'success' : 'skipped';
    if (enabled) selected.push(name);
  }
  return selected;
}
function prShape(action, draft = false, labels = []) {
  return {
    event_name: 'pull_request',
    ref: 'refs/pull/412/merge',
    run_id: 412,
    event: {action, pull_request: {number: 412, draft, labels: labels.map(name => ({name}))}},
  };
}
function eventShape(event_name) {
  return {
    event_name,
    ref: 'refs/heads/master',
    run_id: 412,
    event: {pull_request: {draft: false, labels: []}},
  };
}
const ciOutputs = {
  'change-scope': {scope: 'full', reuse: 'false', live: 'false', quarantine: '["tests/test_x.py::test_y"]'},
};
const watchOutputs = {'watch-scope': {relevant: 'true'}};
const out = {
  ci: {
    draft_opened: selectJobs(payload.ci.jobs, prShape('opened', true), ciOutputs),
    draft_sync: selectJobs(payload.ci.jobs, prShape('synchronize', true), ciOutputs),
    ready_for_review: selectJobs(payload.ci.jobs, prShape('ready_for_review', false), ciOutputs),
    ready_sync: selectJobs(payload.ci.jobs, prShape('synchronize', false), ciOutputs),
    push_master: selectJobs(payload.ci.jobs, eventShape('push'), ciOutputs),
  },
  watch: {
    pr_relevant: selectJobs(payload.watch.jobs, prShape('opened', false), watchOutputs),
    push_master: selectJobs(payload.watch.jobs, eventShape('push'), watchOutputs),
    nightly_schedule: selectJobs(payload.watch.jobs, eventShape('schedule'), watchOutputs),
    manual_dispatch: selectJobs(payload.watch.jobs, eventShape('workflow_dispatch'), watchOutputs),
  },
};
process.stdout.write(JSON.stringify(out));
"""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eval_workflows() -> dict:
    ci_wf = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    watch_wf = yaml.safe_load(WATCH_YML.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["node", "-e", EVAL_CI_AND_WATCH],
        input=json.dumps({"ci": ci_wf, "watch": watch_wf}),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_housekeeping_manifest_and_shard_exclusion_are_total_and_disjoint():
    runner = _load_module("run_fast_gate_housekeeping", RUNNER_SCRIPT)
    ci_shard = _load_module("ci_shard", CI_SHARD_SCRIPT)

    manifest_files = set(runner.load_housekeeping_manifest(MANIFEST))
    assert EXPECTED_CORE_HOUSEKEEPING.issubset(manifest_files)

    buckets = runner.lpt_buckets(sorted(manifest_files), 4, {})
    assert len(buckets) == 4
    flattened = [f for b in buckets for f in b]
    assert sorted(flattened) == sorted(manifest_files)

    sharded_files = set(ci_shard.discover_test_files())
    assert sharded_files.isdisjoint(manifest_files), (
        f"overlap between shards and fast-gate housekeeping: {sharded_files & manifest_files}"
    )

    on_disk = {
        p.relative_to(REPO_ROOT / "backend").as_posix()
        for p in (REPO_ROOT / "backend" / "tests").rglob("test_*.py")
        if "__pycache__" not in p.parts
    }
    assert sharded_files | manifest_files == on_disk


def test_fast_gate_runs_housekeeping_unconditionally_inside_ci_yml():
    ci_wf = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    fast_gate = ci_wf["jobs"]["fast-gate"]
    hk_step = next(
        s for s in fast_gate["steps"] if "run_fast_gate_housekeeping.py" in str(s.get("run", ""))
    )
    assert "if" not in hk_step
    setup_py = next(
        s for s in fast_gate["steps"] if str(s.get("uses", "")).startswith("actions/setup-python")
    )
    assert "if" not in setup_py
    install_step = next(
        s for s in fast_gate["steps"] if s.get("name") == "Install dependencies"
    )
    assert "if" not in install_step


def test_heavy_ci_jobs_skip_draft_prs_and_run_on_ready_and_master_pushes():
    ci_wf = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    on_block = ci_wf.get("on") or ci_wf.get(True)
    assert on_block["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    ]

    out = _eval_workflows()["ci"]
    for key in ("draft_opened", "draft_sync"):
        selected = set(out[key])
        assert "change-scope" in selected
        assert "fast-gate" in selected
        assert HEAVY_PR_JOBS.isdisjoint(selected), (key, selected)
        assert "flaky-canary" not in selected

    for key in ("ready_for_review", "ready_sync", "push_master"):
        selected = set(out[key])
        assert HEAVY_PR_JOBS.issubset(selected), (key, selected)


def test_watch_mvp_runs_only_behavior_and_unsigned_builds_on_prs_and_journeys_nightly():
    watch_wf = yaml.safe_load(WATCH_YML.read_text(encoding="utf-8"))
    on_block = watch_wf.get("on") or watch_wf.get(True)
    assert "schedule" in on_block and on_block["schedule"]
    assert watch_wf["jobs"]["watch-mvp"]["name"] == "Watch behavior and unsigned builds"

    out = _eval_workflows()["watch"]
    assert set(out["pr_relevant"]) == {"watch-scope", "watch-mvp"}
    assert set(out["push_master"]) == {"watch-scope", "watch-mvp"}

    expected_nightly = {
        "watch-scope",
        "watch-mvp",
        "iphone-compatibility",
        "watch-ui-products",
        "watch-ui-journey",
        "watch-ui-complete",
        "companion-archive",
    }
    assert expected_nightly.issubset(set(out["nightly_schedule"]))
    assert expected_nightly.issubset(set(out["manual_dispatch"]))
