"""Ruling 394 tests: release on merge with the full test suite running beside it.

Verifies (a)-(d):
  a. `deploy` waits only for `change-scope`, `fast-gate`, and `release-required`,
     never for `backend-tests`, `shard-completeness`, `database-integration`,
     `frontend-build`, or `e2e-contract`, while those full-suite jobs still run
     on every push to master.
  b. Fail-closed classification via `.github/scripts/heroku-release-wait-full.sh`
     + `.github/scripts/ci-deploy-base.sh`: migrations (including renames/moves),
     `.github/` edits, unclassifiable paths / failing scope script, and
     unresolved bases all set `wait_full=true` -> `deploy` skips and
     `deploy-after-full` waits for the full suite before releasing.
  c. Real post-deploy smoke rollback (`post-deploy-smoke` -> `--execute`) runs
     after either `deploy` or `deploy-after-full`.
  d. When the full run beside a release goes red, `master-red-alarm.yml` +
     `master_red_alarm.py` post one line on NOW `#13580` naming the CI run and
     the release and hold further merges until Fable posts a line.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RED_ALARM_YML = REPO_ROOT / ".github" / "workflows" / "master-red-alarm.yml"
WAIT_FULL_SH = REPO_ROOT / ".github" / "scripts" / "heroku-release-wait-full.sh"
DEPLOY_BASE_SH = REPO_ROOT / ".github" / "scripts" / "ci-deploy-base.sh"
CHANGE_SCOPE_SH = REPO_ROOT / ".github" / "scripts" / "ci-change-scope.sh"
CROSS_TIER_MANIFEST = REPO_ROOT / ".github" / "ci-cross-tier-paths.txt"

sys.path.insert(0, str(REPO_ROOT / "backend" / "scripts"))
import master_red_alarm as alarm  # noqa: E402


EVAL_CI_GRAPH_JS = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const jobs = input.wf.jobs;
const scopeOutputs = input.scopeOutputs || { scope: 'full', live: 'false', reuse: 'false' };
const releaseOutputs = input.releaseOutputs || { required: 'true', wait_full: 'false' };
const failJobs = new Set(input.failJobs || []);

function evalExpr(expr, github, needs, parentsPassed) {
  let e = String(expr ?? 'true').replace(/^\$\{\{\s*|\s*\}\}$/g, '')
    .replaceAll('github.event.pull_request.labels.*.name',
      'github.event.pull_request.labels.map(l => l.name)')
    .replace(/needs\.([a-z][a-z0-9-]*)/g, (_, id) => `needs[${JSON.stringify(id)}]`);
  return Boolean(new Function(
    'github', 'needs', 'contains', 'startsWith', 'format', 'cancelled', 'always', 'success',
    `return (${e})`
  )(
    github,
    needs,
    (list, v) => list.includes(v),
    (v, p) => String(v).startsWith(p),
    (f, ...a) => f.replace(/\{(\d+)\}/g, (_, i) => a[+i]),
    () => false,
    () => true,
    () => parentsPassed,
  ));
}

const github = {
  event_name: 'push',
  ref: 'refs/heads/master',
  run_id: 999,
  event: { pull_request: { labels: [] } },
};
const states = {};
const ran = [];
const outputsByJob = {
  'change-scope': scopeOutputs,
  'release-required': releaseOutputs,
};
for (const [name, job] of Object.entries(jobs)) {
  const deps = typeof job.needs === 'string' ? [job.needs] : (job.needs || []);
  const needs = Object.fromEntries(
    deps.map((id) => [id, { result: states[id], outputs: { ...(outputsByJob[id] || {}), deployed: 'true' } }])
  );
  const parentsPassed = deps.every((id) => states[id] === 'success');
  const explicit = /\b(?:always|cancelled|success|failure)\(/.test(String(job.if ?? ''));
  const enabled = (explicit || parentsPassed) && evalExpr(job.if, github, needs, parentsPassed);
  if (enabled) {
    states[name] = failJobs.has(name) ? 'failure' : 'success';
    ran.push(name);
  } else {
    states[name] = 'skipped';
  }
}
process.stdout.write(JSON.stringify({ ran, states }));
"""


def _workflow() -> dict:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))


def _simulate_master_push(*, scope="full", required="true", wait_full="false", fail_jobs=()):
    res = subprocess.run(
        ["node", "-e", EVAL_CI_GRAPH_JS],
        input=json.dumps({
            "wf": _workflow(),
            "scopeOutputs": {"scope": scope, "live": "false", "reuse": "false"},
            "releaseOutputs": {"required": required, "wait_full": wait_full},
            "failJobs": list(fail_jobs),
        }),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(res.stdout)


def _git_repo(tmp_path: Path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True, capture_output=True)

    def commit(files: dict[str, str], msg: str = "c") -> str:
        for rel, content in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", msg], check=True, capture_output=True)
        return subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    def move_and_commit(src: str, dst: str) -> str:
        (tmp_path / dst).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(tmp_path), "mv", src, dst], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "mv"], check=True, capture_output=True)
        return subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    return commit, move_and_commit


def _run_wait_full(repo: Path, base: str, head: str, base_status: str = "resolved", *, scope_script: Path | None = None) -> str:
    env = {
        **os.environ,
        "CI_CHANGE_SCOPE_SCRIPT": str(scope_script or CHANGE_SCOPE_SH),
        "CI_CROSS_TIER_MANIFEST": str(CROSS_TIER_MANIFEST),
    }
    proc = subprocess.run(
        ["bash", str(WAIT_FULL_SH), base, head, base_status],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_394a_deploy_waits_only_for_quick_gate_and_release_required_while_full_runs():
    jobs = _workflow()["jobs"]
    deploy = jobs["deploy"]
    assert deploy["needs"] == ["change-scope", "fast-gate", "release-required"]
    for full_job in ("backend-tests", "shard-completeness", "database-integration", "frontend-build", "e2e-contract"):
        assert full_job not in deploy["needs"]

    # Normal server change releases on merge via `deploy` AND still runs every full-suite job beside it.
    sim = _simulate_master_push(scope="full", required="true", wait_full="false")
    for expected in ("deploy", "post-deploy-smoke", "backend-tests", "shard-completeness", "database-integration", "search-recall", "frontend-build", "e2e-contract"):
        assert expected in sim["ran"], (expected, sim["ran"])
    assert "deploy-after-full" not in sim["ran"]

    # Even if the parallel backend shards fail, `deploy` does not depend on them (Ruling 394a vs d).
    sim_red_beside = _simulate_master_push(scope="full", required="true", wait_full="false", fail_jobs=("backend-tests",))
    assert "deploy" in sim_red_beside["ran"]
    assert sim_red_beside["states"]["deploy"] == "success"
    assert "deploy-after-full" not in sim_red_beside["ran"]


def test_394b_migration_proves_wait_full_and_deploy_after_full_blocks_until_full_suite(tmp_path: Path):
    commit, move_and_commit = _git_repo(tmp_path)
    base = commit({"backend/app/routes/feed.py": "x = 1\n", "backend/alembic/versions/0001_init.py": "rev='1'\n"})

    # 1. Adding a migration under backend/alembic/versions/ MUST wait for the full run.
    mig_head = commit({"backend/alembic/versions/20261125_new.py": "rev='2'\n"})
    assert _run_wait_full(tmp_path, base, mig_head) == "true"

    # 2. Editing alembic.ini or alembic/env.py or renaming a migration out of alembic MUST also wait full.
    ini_head = commit({"backend/alembic.ini": "[alembic]\n"})
    assert _run_wait_full(tmp_path, mig_head, ini_head) == "true"
    mv_head = move_and_commit("backend/alembic/versions/0001_init.py", "docs/moved_init.py")
    assert _run_wait_full(tmp_path, ini_head, mv_head) == "true"

    # Graph proof: with wait_full=true, fast `deploy` skips and `deploy-after-full` waits for full suite.
    sim_mig = _simulate_master_push(scope="full", required="true", wait_full="true")
    assert "deploy" not in sim_mig["ran"]
    assert "deploy-after-full" in sim_mig["ran"]
    assert "post-deploy-smoke" in sim_mig["ran"]

    # And if a backend shard fails when wait_full=true, NOTHING deploys!
    sim_mig_red = _simulate_master_push(scope="full", required="true", wait_full="true", fail_jobs=("backend-tests",))
    assert "deploy" not in sim_mig_red["ran"]
    assert "deploy-after-full" not in sim_mig_red["ran"]


def test_394b_fails_closed_for_github_unclassifiable_and_unresolved_base(tmp_path: Path):
    commit, _ = _git_repo(tmp_path)
    base = commit({"backend/app/routes/feed.py": "v1\n"})

    # 1. Any change under .github/ or tools/release/ fails closed.
    gh_head = commit({".github/workflows/ci.yml": "name: CI\n", "backend/app/routes/feed.py": "v2\n"})
    assert _run_wait_full(tmp_path, base, gh_head) == "true"
    rel_head = commit({"tools/release/live_path.py": "# edit\n"})
    assert _run_wait_full(tmp_path, gh_head, rel_head) == "true"

    # 2. Normal server change passes when base is resolved.
    srv_head = commit({"backend/app/routes/feed.py": "v3\n", "backend/tests/test_feed.py": "def test_ok(): pass\n"})
    assert _run_wait_full(tmp_path, rel_head, srv_head, "resolved") == "false"

    # 3. Unresolved base (including real ci-deploy-base.sh failing to resolve /api/health) waits full.
    status_file = tmp_path / "base_status.txt"
    resolved_base = subprocess.check_output(
        ["bash", str(DEPLOY_BASE_SH), rel_head, srv_head],
        cwd=tmp_path,
        env={
            **os.environ,
            "CI_DEPLOYED_SHA_URL": "http://127.0.0.1:9/unreachable",
            "CI_DEPLOYED_SHA_TIMEOUT": "1",
            "CI_DEPLOY_BASE_STATUS_FILE": str(status_file),
        },
        text=True,
    ).strip()
    assert resolved_base == rel_head
    assert status_file.read_text(encoding="utf-8").strip() == "unresolved"
    assert _run_wait_full(tmp_path, resolved_base, srv_head, status_file.read_text().strip()) == "true"
    assert _run_wait_full(tmp_path, "0" * 40, srv_head, "resolved") == "true"
    assert _run_wait_full(tmp_path, "deadbeef" * 5, srv_head, "resolved") == "true"

    # 4. Path outside classified fast-release allowlist (e.g. requirements.txt / Procfile / unknown/) waits full.
    req_head = commit({"backend/requirements.txt": "fastapi==1.0\n"})
    assert _run_wait_full(tmp_path, srv_head, req_head, "resolved") == "true"
    unk_head = commit({"mystery_dir/file.txt": "hello\n"})
    assert _run_wait_full(tmp_path, req_head, unk_head, "resolved") == "true"

    # 5. Scope script failing or returning unclassifiable output fails closed even on a normal server diff.
    broken_scope = tmp_path / "broken_scope.sh"
    broken_scope.write_text("#!/usr/bin/env bash\necho weird\nexit 0\n", encoding="utf-8")
    broken_scope.chmod(0o755)
    assert _run_wait_full(tmp_path, rel_head, srv_head, "resolved", scope_script=broken_scope) == "true"

    fallback_scope = tmp_path / "fallback_scope.sh"
    fallback_scope.write_text("#!/usr/bin/env bash\necho full\necho 'DECISION: full (empty diff)' >&2\nexit 0\n", encoding="utf-8")
    fallback_scope.chmod(0o755)
    assert _run_wait_full(tmp_path, rel_head, srv_head, "resolved", scope_script=fallback_scope) == "true"


def test_394c_post_deploy_smoke_runs_for_real_after_either_deploy_job():
    smoke = _workflow()["jobs"]["post-deploy-smoke"]
    assert smoke["needs"] == ["deploy", "deploy-after-full"]
    assert smoke["permissions"] == {"contents": "read", "issues": "write"}
    step = smoke["steps"][-1]
    assert "--execute" in step["run"]
    assert "--dry-run" not in step["run"]


def test_394d_master_red_alarm_holds_merges_and_names_run_and_release(monkeypatch):
    wf = yaml.safe_load(RED_ALARM_YML.read_text(encoding="utf-8"))
    assert wf["env"]["NOW_LINES_ISSUE"] == "13580"

    posted = []
    reruns = []

    def fake_gh(path, *rest, body=None):
        if path.endswith("/jobs?filter=latest&per_page=100"):
            return json.dumps({
                "jobs": [
                    {"id": 11, "name": "deploy", "conclusion": "success"},
                    {"id": 12, "name": "backend-tests (3)", "conclusion": "failure"},
                ]
            })
        if "/logs" in path:
            return "FAILED tests/test_feed.py::test_x - AssertionError\n"
        if "/issues/13580/comments?per_page=100" in path:
            return ""
        if path.endswith("/rerun-failed-jobs"):
            reruns.append(path)
            return ""
        if path.endswith("/issues/13580/comments"):
            posted.append(body["body"])
            return "{}"
        return json.dumps({
            "id": 777,
            "run_attempt": 1,
            "event": "push",
            "head_branch": "master",
            "conclusion": "failure",
            "head_sha": "c" * 40,
            "display_title": "feat: server change (#13999)",
            "html_url": "https://github.com/o/r/actions/runs/777",
        })

    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setenv("NOW_LINES_ISSUE", "13580")
    monkeypatch.setenv("RUN_ID", "777")
    monkeypatch.setattr(alarm, "_gh", fake_gh)

    assert alarm.main([]) == 0
    assert reruns == []
    assert len(posted) == 1
    msg = posted[0]
    first_line = msg.splitlines()[0]
    assert "beside release `cccccccccc` (#13999)" in first_line
    assert "HOLD (no further merges until Fable posts a line)" in first_line
    assert "[run 777](https://github.com/o/r/actions/runs/777)" in first_line
    assert "No further merge happens until Fable posts a line" in msg
