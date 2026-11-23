"""#13027 (251: A): watch-mvp.yml and codeql.yml cancel superseded runs.

Previously, watch-mvp.yml left watch-ui-products with no concurrency group,
iphone-compatibility with cancel-in-progress: false, and master pushes keyed on
github.run_id — letting stale PR pushes and stacked master pushes hold the
5-slot macOS runner pool. codeql.yml had no concurrency block at all, so
stacked master pushes burned parallel Ubuntu CodeQL runs.

Both workflows now enforce a single workflow-level concurrency group keyed by
PR number on pull_request and github.ref on push/schedule, with
cancel-in-progress: true. The latest head of every PR and branch still runs
every job intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _load_workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("filename", "prefix"),
    [
        ("watch-mvp.yml", "watch-mvp-"),
        ("codeql.yml", "codeql-"),
    ],
)
def test_workflow_cancels_superseded_pr_and_branch_runs(
    filename: str, prefix: str
) -> None:
    wf = _load_workflow(filename)
    conc = wf.get("concurrency")
    assert isinstance(conc, dict), f"{filename} must define workflow-level concurrency"
    assert conc.get("cancel-in-progress") is True, (
        f"{filename} must set cancel-in-progress: true so superseded heads free runners"
    )
    group = str(conc.get("group") or "")
    assert prefix in group
    assert "github.event.pull_request.number" in group, (
        f"{filename} must key pull_request runs by PR number"
    )
    assert "github.ref" in group, (
        f"{filename} must key branch runs by github.ref, not github.run_id"
    )
    assert "github.run_id" not in group, (
        f"{filename} must not fall back to github.run_id, which prevents superseding"
    )
    job_concurrencies = [
        name for name, job in (wf.get("jobs") or {}).items() if "concurrency" in job
    ]
    assert job_concurrencies == [], (
        f"{filename} should not carry redundant per-job concurrency: {job_concurrencies}"
    )


def test_watch_mvp_preserves_all_jobs_without_reducing_coverage() -> None:
    wf = _load_workflow("watch-mvp.yml")
    expected = {
        "watch-mvp",
        "iphone-compatibility",
        "watch-ui-products",
        "watch-ui-journey",
        "watch-ui-complete",
        "companion-archive",
    }
    assert expected.issubset(set((wf.get("jobs") or {}).keys()))


def test_codeql_preserves_python_and_js_matrix() -> None:
    wf = _load_workflow("codeql.yml")
    langs = wf["jobs"]["analyze"]["strategy"]["matrix"]["language"]
    assert langs == ["python", "javascript-typescript"]
