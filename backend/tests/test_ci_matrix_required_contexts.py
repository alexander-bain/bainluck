"""A matrix job's legs must always EXPAND, or its required contexts are never created.

`backend-tests (1)`..`(4)` are required status checks on master. GitHub creates
those per-leg contexts only when the matrix expands; a matrix job skipped at JOB
level records a single bare `backend-tests` check instead, and the four required
names never exist. Absent is not failed: CI reads `completed/success`, every
merge notice passes, and the PR sits MERGEABLE/BLOCKED with nothing red
(ux/1464, 2026-09-23 — every frontend-only PR, #8253 and #8261 among them; a
rebase cannot help because change-scope reads only the file set).

So #5007's frontend-only saving lives on the STEPS: the legs expand, report
`success`, and do no work. These tests hold both halves: the contexts exist, and
the saving is still real.

A non-matrix job skipped at job level is fine: its single `skipped` context
satisfies branch protection (`shard-completeness`, `search-recall` on
`ef81eafb9b`, read 2026-09-23).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or REPO_ROOT / ".github" / "workflows" / "ci.yml")

RUNS = "needs.change-scope.outputs.scope != 'frontend'"
MARKER = "needs.change-scope.outputs.scope == 'frontend'"


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text())["jobs"]


def _evaluate(cond: str | None, scope) -> bool:
    """The two conditions this job uses, evaluated for a change-scope output.

    An unset output reads as '' in GitHub expressions. Anything else is refused
    rather than guessed, so a new condition shape fails here instead of passing.
    """
    value = "" if scope is None else scope
    if cond is None:
        return True
    if cond.strip() == RUNS:
        return value != "frontend"
    if cond.strip() == MARKER:
        return value == "frontend"
    raise AssertionError(f"unrecognised backend-tests step condition: {cond!r}")


def test_no_matrix_job_is_skipped_at_job_level_by_change_scope():
    offenders = [
        name
        for name, job in _jobs().items()
        if (job.get("strategy") or {}).get("matrix") and "change-scope" in str(job.get("if", ""))
    ]
    assert not offenders, (
        f"{offenders} skip a MATRIX job at job level on change-scope. A job-level skip never "
        "expands the matrix, so its per-leg contexts (e.g. `backend-tests (1)`) are never "
        "created, and those are required on master: every frontend-only PR goes BLOCKED with "
        "CI green. Put the condition on each step instead (see the backend-tests header)."
    )


def test_backend_tests_is_still_a_matrix():
    matrix = (_jobs()["backend-tests"].get("strategy") or {}).get("matrix") or {}
    assert matrix.get("shard") == [1, 2, 3, 4], (
        "backend-tests' shard list changed; branch protection's required contexts "
        "`backend-tests (1)`..`(4)` must be changed with it."
    )


def test_every_backend_tests_step_carries_one_of_the_two_scope_conditions():
    steps = _jobs()["backend-tests"]["steps"]
    for step in steps:
        label = step.get("name") or step.get("uses")
        assert step.get("if") in (RUNS, MARKER), (
            f"backend-tests step {label!r} has condition {step.get('if')!r}. Every step must "
            f"carry `{RUNS}` (real work) or be the frontend marker; an unconditioned step "
            "runs on a frontend-only candidate with no checkout and spends #5007's saving."
        )
    assert sum(s.get("if") == MARKER for s in steps) == 1, "exactly one frontend marker step"


def test_the_marker_step_needs_no_checkout():
    marker = next(s for s in _jobs()["backend-tests"]["steps"] if s.get("if") == MARKER)
    # The job default is `working-directory: backend`, which does not exist before checkout.
    assert marker.get("working-directory") == ".", marker
    assert "uses" not in marker, marker


@pytest.mark.parametrize("scope", ["frontend", "full", "", None])
def test_a_frontend_scope_runs_only_the_marker_and_anything_else_runs_everything(scope):
    steps = _jobs()["backend-tests"]["steps"]
    ran = [s.get("name") or s.get("uses") for s in steps if _evaluate(s.get("if"), scope)]
    real = [s.get("name") or s.get("uses") for s in steps if s.get("if") == RUNS]
    if scope == "frontend":
        assert len(ran) == 1 and ran[0].startswith("Frontend-only candidate"), ran
    else:
        assert ran == real, (scope, ran)
        assert any("Run tests" in r for r in ran)


def test_deploy_still_waits_on_the_sibling_gates_that_skip_on_frontend():
    jobs = _jobs()
    assert {"backend-tests", "shard-completeness", "search-recall"} <= set(jobs["deploy"]["needs"])
    for name in ("shard-completeness", "search-recall"):
        job = jobs[name]
        assert not (job.get("strategy") or {}).get("matrix"), (
            f"{name} became a matrix job; a job-level skip would then drop its required contexts"
        )
        assert job.get("if") == RUNS, (name, job.get("if"))
