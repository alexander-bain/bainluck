"""Contract tests for `.github/workflows/master-priority.yml` (Release runs Part 2)."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "master-priority.yml"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_triggers_only_master_push_and_master_ci_completion() -> None:
    wf = _load()
    triggers = wf.get("on") or wf[True]
    assert triggers["push"]["branches"] == ["master"]
    wr = triggers["workflow_run"]
    assert wr["workflows"] == ["CI"]
    assert wr["types"] == ["completed"]
    assert wr["branches"] == ["master"]


def test_yield_and_resume_have_separate_non_cancelling_concurrency_groups() -> None:
    wf = _load()
    assert "concurrency" not in wf
    jobs = wf["jobs"]
    y_conc = jobs["yield-pr-runs"]["concurrency"]
    r_conc = jobs["resume-pr-runs"]["concurrency"]
    assert y_conc["group"] != r_conc["group"]
    assert y_conc["cancel-in-progress"] is False
    assert r_conc["cancel-in-progress"] is False


def test_yield_gates_on_heroku_release_required_and_pages_lists() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "heroku-release-required.sh" in text
    assert "ci-deploy-base.sh" in text
    assert "steps.release_check.outputs.required == 'true'" in text
    assert "gh_paginate_key" in text and "per_page=100&page={page}" in text
    assert "runner queue wait:" in text


def test_no_silent_gh_failures_and_resume_exits_nonzero_on_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "raise RuntimeError" in text
    assert '"paused"' in text and '"resumed"' in text
    assert '"failed_to_resume"' in text
    assert 'if counts["failed_to_resume"] > 0:' in text
    assert "Does NOT assume a standing ruling" not in text
    assert "Awaiting its own ruling" in text


def test_resume_bounds_master_runs_and_artifact_pagination() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ci.yml/runs?branch=master&event=push&status={st}" in text
    assert 'gh_paginate_key(\n              f"repos/{repo}/actions/workflows/ci.yml/runs?branch=master&event=push",' not in text
    assert 'gh_paginate_key(f"repos/{repo}/actions/artifacts"' not in text
    assert "page_has_recent" in text
    assert "created >= cutoff" in text
