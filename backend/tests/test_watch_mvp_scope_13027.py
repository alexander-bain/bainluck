"""#13027 (251: A): watch-mvp-scope.py keeps server-only PRs off macOS runners.

Proves against a real temporary git repository that:
1. A server-only PR that merges a Watch-touching master commit (#12962 / #12970
   shape) emits relevant=false and starts 0 of the 9 macOS Watch jobs.
2. Any PR or push whose real diff touches a Watch, shared iOS, widget, xcodeproj,
   or Watch-tooling path emits relevant=true.
3. Any uncertain or broken input fails closed toward relevant=true.
4. The stdlib path parser matches watch-mvp.yml's YAML paths list verbatim.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "watch-mvp.yml"
SCRIPT = REPO_ROOT / ".github" / "scripts" / "watch-mvp-scope.py"


def _load_scope_module():
    spec = importlib.util.spec_from_file_location("watch_mvp_scope", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.com")


def _commit(root: Path, files: dict[str, str], msg: str) -> str:
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def test_stdlib_parser_matches_yaml_paths_verbatim() -> None:
    mod = _load_scope_module()
    raw = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    on_block = parsed.get("on") or parsed.get(True)
    pr_paths = on_block["pull_request"]["paths"]
    push_paths = on_block["push"]["paths"]
    extracted = mod.extract_watch_paths(raw)
    assert set(extracted) == set(pr_paths) | set(push_paths)
    assert ".github/scripts/watch-mvp-scope.py" in pr_paths
    assert ".github/scripts/watch-mvp-scope.py" in push_paths


def test_server_only_pr_merging_watch_master_is_not_relevant(tmp_path: Path) -> None:
    """Exact #12962 / #12970 shape: server PR merges master carrying Watch edits."""
    mod = _load_scope_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    _commit(
        repo,
        {
            "backend/app/utils/tournament_slate.py": "v1\n",
            "ios/Bain Luck/BainLuckWatch Watch App/App.swift": "v1\n",
        },
        "initial",
    )
    _git(repo, "checkout", "-q", "-b", "codex/server-only")
    _commit(repo, {"backend/app/utils/tournament_slate.py": "v2\n"}, "server change")

    _git(repo, "checkout", "-q", "master")
    new_master = _commit(
        repo,
        {
            "ios/Bain Luck/BainLuckWatch Watch App/App.swift": "v2\n",
            ".github/workflows/watch-mvp.yml": "v2\n",
        },
        "master watch change",
    )

    _git(repo, "checkout", "-q", "codex/server-only")
    _git(repo, "merge", "-q", "--no-edit", "master")
    pr_head = _git(repo, "rev-parse", "HEAD")

    relevant, reason = mod.decide_scope(
        repo=repo,
        event_name="pull_request",
        base_sha=new_master,
        head_sha=pr_head,
        workflow_path=WORKFLOW,
    )
    assert relevant is False, reason
    assert "0/1 changed file(s)" in reason


@pytest.mark.parametrize(
    "changed_path",
    [
        "ios/Bain Luck/BainLuckWatch Watch App/Views/Nested/FaceView.swift",
        "ios/Bain Luck/Bain Luck/Models/PredictionModels.swift",
        "ios/Bain Luck/BainLuckTests/WatchDiscoveryRefreshTests.swift",
        "ios/Bain Luck/BainLuckWidget/LiveActivity.swift",
        "tools/watch-build.sh",
        ".github/scripts/watch-mvp-scope.py",
        ".github/workflows/watch-mvp.yml",
    ],
)
def test_real_watch_or_app_pr_is_relevant(tmp_path: Path, changed_path: str) -> None:
    mod = _load_scope_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    base = _commit(repo, {"README.md": "v1\n"}, "base")
    head = _commit(repo, {changed_path: "v1\n"}, "touch watch/app path")

    relevant, reason = mod.decide_scope(
        repo=repo,
        event_name="pull_request",
        base_sha=base,
        head_sha=head,
        workflow_path=WORKFLOW,
    )
    assert relevant is True, reason


def test_fails_closed_toward_relevant_on_bad_inputs(tmp_path: Path) -> None:
    mod = _load_scope_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    head = _commit(repo, {"README.md": "v1\n"}, "base")

    for kwargs in (
        {"event_name": "pull_request", "base_sha": "0" * 40, "head_sha": head},
        {"event_name": "pull_request", "base_sha": "deadbeef" * 5, "head_sha": head},
        {"event_name": "push", "base_sha": head, "head_sha": head},
        {"event_name": "workflow_dispatch", "base_sha": head, "head_sha": head},
    ):
        relevant, _ = mod.decide_scope(repo=repo, workflow_path=WORKFLOW, **kwargs)
        assert relevant is True, kwargs

    relevant, _ = mod.decide_scope(
        repo=repo,
        event_name="pull_request",
        base_sha=head,
        head_sha=head,
        workflow_path=tmp_path / "missing.yml",
    )
    assert relevant is True


def test_workflow_gates_all_macos_jobs_and_aggregate_behind_watch_scope() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = wf["jobs"]

    scope = jobs["watch-scope"]
    assert scope["runs-on"] == "ubuntu-latest"
    assert scope["outputs"]["relevant"] == "${{ steps.decide.outputs.relevant }}"

    watch_mvp = jobs["watch-mvp"]
    assert watch_mvp["needs"] == "watch-scope"
    assert watch_mvp["if"] == "needs.watch-scope.outputs.relevant == 'true'"

    complete = jobs["watch-ui-complete"]
    assert set(complete["needs"]) == {"watch-scope", "watch-ui-journey"}
    assert "always()" in str(complete["if"])
    assert "needs.watch-scope.outputs.relevant == 'true'" in str(complete["if"])

    # Every macOS job must transitively depend on watch-mvp (hence watch-scope).
    def ancestors(job_name: str) -> set[str]:
        needs = jobs[job_name].get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        seen = set(needs)
        for n in list(needs):
            seen |= ancestors(n)
        return seen

    for name, job in jobs.items():
        runner = str(job.get("runs-on") or "")
        if "macos" in runner or "xcode" in runner:
            assert "watch-scope" in ancestors(name), f"macOS job {name} bypasses watch-scope"
