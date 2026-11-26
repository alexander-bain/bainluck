"""ci.yml's workflow-level concurrency: a superseded PR sha stops holding runners,
and (Decide 76) a newer push to a ref displaces that ref's older PENDING run while
an in-progress push run is never cancelled; the job set and release
serialization do not change.

Evaluates the actual `${{ }}` expressions in ci.yml against the four event shapes
(pull_request sync, push to master / merge, rerun, push+PR on one sha) rather
than asserting on their text. Runs under pytest, or standalone:
    CI_WORKFLOW_PATH=path/to/ci.yml python3 backend/tests/test_ci_supersede_concurrency.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = Path(
    os.environ.get("CI_WORKFLOW_PATH") or REPO_ROOT / ".github" / "workflows" / "ci.yml"
)

REQUIRED_JOBS = {
    "change-scope",
    "backend-tests",
    "shard-completeness",
    "golden-baseline-floor",
    "search-recall",
    "frontend-build",
    "e2e-contract",
    "release-required",
    "deploy",
    "deploy-after-full",
    "post-deploy-smoke",
}
DEPLOY_NEEDS = {
    "release-required",
    "change-scope",
    "fast-gate",
}
DEPLOY_AFTER_FULL_NEEDS = {
    "backend-tests",
    "shard-completeness",
    # Fable, Wed Nov 18: deploy-after-full reads the integration groups itself, not via search-recall.
    "database-integration",
    "frontend-build",
    "e2e-contract",
    "release-required",
    "change-scope",
    "fast-gate",
}


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text())


def _evaluate(
    expr,
    github: dict,
    *,
    matrix: dict | None = None,
    needs: dict | None = None,
):
    """GitHub expression subset -> value. `&&`/`||` return operands, as Python's do."""
    if isinstance(expr, bool):
        return expr
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", str(expr), re.S)
    assert m, f"expected a ${{{{ }}}} expression or a bool, got {expr!r}"
    src = m.group(1).replace("&&", " and ").replace("||", " or ")

    roots = {
        "github": github,
        "matrix": matrix or {},
        "needs": needs or {},
    }

    def ctx(match):
        parts = match.group(0).split(".")
        node = roots.get(parts[0])
        for part in parts[1:]:
            node = node.get(part) if isinstance(node, dict) else None
        return repr(node)

    src = re.sub(r"\b(?:github|matrix|needs)(?:\.[A-Za-z0-9_-]+)+", ctx, src)
    fmt = lambda s, *a: re.sub(
        r"\{(\d+)\}", lambda k: str(a[int(k.group(1))]), s
    )  # noqa: E731
    return eval(
        src, {"__builtins__": {}}, {"format": fmt}
    )  # noqa: S307 - input is this repo's ci.yml


def _slot(github: dict):
    conc = _workflow().get("concurrency")
    assert (
        conc
    ), "ci.yml has no workflow-level concurrency: every superseded PR sha runs to completion"
    return _evaluate(conc["group"], github), bool(
        _evaluate(conc["cancel-in-progress"], github)
    )


def _job_slot(
    job_name: str,
    github: dict,
    *,
    matrix: dict | None = None,
    needs: dict | None = None,
):
    conc = _workflow()["jobs"][job_name].get("concurrency")
    assert conc, f"{job_name} has no job-level concurrency"
    return (
        _evaluate(conc["group"], github, matrix=matrix, needs=needs),
        bool(_evaluate(conc["cancel-in-progress"], github, matrix=matrix, needs=needs)),
    )


def _pr(number, sha, run_id):
    return {
        "event_name": "pull_request",
        "sha": sha,
        "run_id": run_id,
        "ref": f"refs/pull/{number}/merge",
        "event": {"pull_request": {"number": number}},
    }


def _push(sha, run_id):
    return {
        "event_name": "push",
        "sha": sha,
        "run_id": run_id,
        "ref": "refs/heads/master",
        "event": {},
    }


def test_a_newer_sha_on_the_same_pr_cancels_the_older_run():
    old, new = _slot(_pr(6731, "4db0b32", 1)), _slot(_pr(6731, "e76539d", 2))
    assert (
        old[0] == new[0]
    ), "two shas of one PR must share a group or nothing is superseded"
    assert new[1] is True


def test_two_different_prs_never_touch_each_other():
    assert _slot(_pr(6744, "d9359dc", 1))[0] != _slot(_pr(6745, "fb76de7", 2))[0]


def test_master_pushes_share_one_group_and_an_in_progress_run_is_never_cancelled():
    """Ruling 394 Change 3: workflow-level master push runs use one group per SHA so
    merges 2-4 release immediately without queuing behind merge 1's full suite, while
    integrator/compose-* keeps one non-cancellable group per ref.
    Heavy beside-release full-suite jobs supersede older master runs at the job level.
    """
    a, b = _slot(_push("95bd398", 10)), _slot(_push("1074051", 11))
    assert a[0] == "ci-push-master-95bd398" and b[0] == "ci-push-master-1074051", (a, b)
    assert a[1] is False and b[1] is False, "a master workflow run became cancellable in progress"

    compose = {
        "event_name": "push",
        "sha": "abc1234",
        "run_id": 12,
        "ref": "refs/heads/integrator/compose-1",
        "event": {},
    }
    assert _slot(compose) == ("ci-push-refs/heads/integrator/compose-1", False)


def test_a_rerun_of_a_master_run_rejoins_the_master_group__known_and_operational():
    """Ruling 394 Change 3: two runs on the same master SHA share one group without cancellation,
    while heavy full-suite jobs supersede older master SHAs and leave PR & compose runs untouched.
    """
    first, rerun, other = (
        _slot(_push("95bd398", 10)),
        _slot(_push("95bd398", 10)),
        _slot(_push("1074051", 11)),
    )
    assert first == rerun and rerun[0] != other[0] and rerun[1] is False

    pr_ctx = _pr(6744, "d9359dc", 20)
    master_ctx = _push("1074051", 21)
    compose_ctx = {
        "event_name": "push",
        "sha": "abc1234",
        "run_id": 22,
        "ref": "refs/heads/integrator/compose-1",
        "event": {},
    }
    full_needs = {"change-scope": {"outputs": {"scope": "full", "live": "false"}}}
    fe_needs = {"change-scope": {"outputs": {"scope": "frontend", "live": "false"}}}

    assert _job_slot("backend-tests", master_ctx, matrix={"shard": 3}, needs=full_needs) == (
        "ci-master-full-backend-tests-3",
        True,
    )
    assert _job_slot("backend-tests", master_ctx, matrix={"shard": 3}, needs=fe_needs) == (
        "ci-run-21-backend-tests-3",
        False,
    )
    assert _job_slot("backend-tests", pr_ctx, matrix={"shard": 3}, needs=full_needs) == (
        "ci-run-20-backend-tests-3",
        False,
    )
    assert _job_slot("backend-tests", compose_ctx, matrix={"shard": 3}, needs=full_needs) == (
        "ci-run-22-backend-tests-3",
        False,
    )
    assert _job_slot("database-integration", master_ctx, matrix={"group": "shared"}) == (
        "ci-master-full-db-shared",
        True,
    )
    assert _job_slot("frontend-build", master_ctx) == (
        "ci-master-full-frontend-build",
        True,
    )
    assert _job_slot("frontend-build", pr_ctx) == ("ci-run-20-frontend-build", False)


def test_deploy_keeps_never_backwards_guard():
    deploy_script = (REPO_ROOT / ".github" / "scripts" / "heroku-deploy.sh").read_text()
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" "$LIVE"' in deploy_script
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" "$LIVE_NOW"' in deploy_script
    for job_name in ("deploy", "deploy-after-full"):
        deploy_steps = _workflow()["jobs"][job_name]["steps"]
        deploy_run = next(s["run"] for s in deploy_steps if "Deploy to Heroku" in s.get("name", ""))
        assert deploy_run.strip() == "bash .github/scripts/heroku-deploy.sh"


def test_rerunning_an_OLD_pr_sha_cancels_that_prs_head_run__known_and_fail_closed():
    """The one hazard this design accepts, pinned so it stays a decision and not a surprise.

    Re-running an OLD sha's run on PR #N puts it in `ci-pr-N` — the SAME group as the head
    sha's in-flight run — with cancellation enabled, so the head run dies. The head sha is the
    only one the desk may merge (notice 28 reads CI for the exact sha), so the damage is a
    re-run, never a bad merge: the gate finds no successful run for the head and REFUSES. Fail
    closed. Recovery is to re-run the head sha's run.

    Why this is documented rather than fixed: the obvious fix — disabling cancellation for
    re-runs via `github.run_attempt` — only half-works, and a half-fix here is worse than the
    honest hazard because it reads as safety. It would spare an IN-PROGRESS head run, but a
    concurrency group holds exactly one PENDING run and a newly queued run displaces the
    previously pending one regardless of `cancel-in-progress` (the same asymmetry the deploy
    job's own comment records at ci.yml's `heroku-deploy` block). A head run still waiting for
    a runner — which, on the burst days that motivated this change, is most of a run's life —
    would still be dropped. So the rule is operational, not configurable, and it is stated in
    ci.yml: re-run the head sha's run, never an older one.
    """
    head_run = _slot(_pr(6744, "d9359dc", 20))
    old_sha_rerun = _slot(_pr(6744, "4db0b32", 19))

    assert old_sha_rerun[0] == head_run[0], (
        "an old-sha re-run left the PR's group — if this ever passes by landing in a DIFFERENT "
        "group, the hazard is gone and this test should be replaced by the stronger claim"
    )
    assert (
        old_sha_rerun[1] is True
    ), "cancellation is on for PR runs, so the head run is the one that dies"


def test_a_pr_run_and_a_master_run_never_share_a_group_even_on_one_sha():
    assert _slot(_pr(6744, "d9359dc", 1))[0] != _slot(_push("d9359dc", 2))[0]


def test_cancel_in_progress_is_not_a_bare_true():
    raw = (_workflow().get("concurrency") or {}).get("cancel-in-progress")
    assert raw is not None, "ci.yml has no workflow-level concurrency"
    assert raw is not True, "a literal `true` would cancel master runs"


def test_triggers_jobs_and_release_serialization_are_untouched():
    wf = _workflow()
    on = wf.get("on", wf.get(True))
    assert (
        set(on) == {"pull_request", "push"}
        and on["push"] == {"branches": ["master", "integrator/compose-**"]}
        and "branches" not in on["pull_request"]
    )
    assert REQUIRED_JOBS <= set(
        wf["jobs"]
    ), f"missing jobs: {REQUIRED_JOBS - set(wf['jobs'])}"
    deploy = wf["jobs"]["deploy"]
    assert set(deploy["needs"]) == DEPLOY_NEEDS
    assert deploy["concurrency"] == {
        "group": "heroku-deploy",
        "cancel-in-progress": False,
    }
    deploy_full = wf["jobs"]["deploy-after-full"]
    assert set(deploy_full["needs"]) == DEPLOY_AFTER_FULL_NEEDS
    assert deploy_full["concurrency"] == {
        "group": "heroku-deploy",
        "cancel-in-progress": False,
    }
    allowed_concurrency_jobs = {
        "deploy",
        "deploy-after-full",
        "backend-tests",
        "shard-completeness",
        "database-integration",
        "flaky-canary",
        "search-recall",
        "frontend-build",
    }
    assert not any(
        "concurrency" in job for name, job in wf["jobs"].items() if name not in allowed_concurrency_jobs
    )


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {str(exc)[:110]}")
    sys.exit(1 if failed else 0)


def test_compose_pushes_are_independent_and_cannot_release():
    a, b = _push("one", 30), _push("two", 31)
    a["ref"] = b["ref"] = "refs/heads/integrator/compose-example"
    # Decide 76: pushes group by ref, so one compose branch supersedes its own
    # pending run, and never touches master's or another compose branch's.
    c = _push("three", 32)
    c["ref"] = "refs/heads/integrator/compose-other"
    assert _slot(a)[0] == _slot(b)[0] == "ci-push-refs/heads/integrator/compose-example"
    assert _slot(a)[0] != _slot(c)[0] != _slot(_push("four", 33))[0]
    assert _slot(a)[1] is False
    for name in ("release-required", "deploy", "deploy-after-full"):
        assert "github.ref == 'refs/heads/master'" in _workflow()["jobs"][name]["if"]
