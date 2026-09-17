"""ci.yml's workflow-level concurrency: a superseded PR sha stops holding runners,
and NOTHING about master, reruns, the job set or release serialization changes.

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
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or REPO_ROOT / ".github" / "workflows" / "ci.yml")

REQUIRED_JOBS = {
    "change-scope", "backend-tests", "shard-completeness", "golden-baseline-floor",
    "search-recall", "frontend-build", "e2e-contract", "release-required", "deploy",
}
DEPLOY_NEEDS = {
    "backend-tests", "shard-completeness", "search-recall", "frontend-build",
    "e2e-contract", "release-required",
}


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text())


def _evaluate(expr, github: dict):
    """GitHub expression subset -> value. `&&`/`||` return operands, as Python's do."""
    if isinstance(expr, bool):
        return expr
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", str(expr), re.S)
    assert m, f"expected a ${{{{ }}}} expression or a bool, got {expr!r}"
    src = m.group(1).replace("&&", " and ").replace("||", " or ")

    def ctx(match):
        node = github
        for part in match.group(0).split(".")[1:]:
            node = node.get(part) if isinstance(node, dict) else None
        return repr(node)

    src = re.sub(r"\bgithub(?:\.[A-Za-z_]+)+", ctx, src)
    fmt = lambda s, *a: re.sub(r"\{(\d+)\}", lambda k: str(a[int(k.group(1))]), s)  # noqa: E731
    return eval(src, {"__builtins__": {}}, {"format": fmt})  # noqa: S307 - input is this repo's ci.yml


def _slot(github: dict):
    conc = _workflow().get("concurrency")
    assert conc, "ci.yml has no workflow-level concurrency: every superseded PR sha runs to completion"
    return _evaluate(conc["group"], github), bool(_evaluate(conc["cancel-in-progress"], github))


def _pr(number, sha, run_id):
    return {"event_name": "pull_request", "sha": sha, "run_id": run_id, "ref": f"refs/pull/{number}/merge",
            "event": {"pull_request": {"number": number}}}


def _push(sha, run_id):
    return {"event_name": "push", "sha": sha, "run_id": run_id, "ref": "refs/heads/master", "event": {}}


def test_a_newer_sha_on_the_same_pr_cancels_the_older_run():
    old, new = _slot(_pr(6731, "4db0b32", 1)), _slot(_pr(6731, "e76539d", 2))
    assert old[0] == new[0], "two shas of one PR must share a group or nothing is superseded"
    assert new[1] is True


def test_two_different_prs_never_touch_each_other():
    assert _slot(_pr(6744, "d9359dc", 1))[0] != _slot(_pr(6745, "fb76de7", 2))[0]


def test_master_pushes_are_never_cancelled_and_never_share_a_group():
    # A group holds ONE pending run and drops the rest - it is not a FIFO queue. Two merges
    # three minutes apart (95bd39868, 10740513e) must therefore not share one.
    a, b = _slot(_push("95bd398", 10)), _slot(_push("1074051", 11))
    assert a[0] != b[0], "master runs share a concurrency group: a third merge would drop the second's tests"
    assert a[1] is False and b[1] is False, "a master run became cancellable"


def test_a_rerun_of_a_master_run_is_alone_in_its_group():
    first, rerun, other = _slot(_push("95bd398", 10)), _slot(_push("95bd398", 10)), _slot(_push("1074051", 11))
    assert first == rerun and rerun[0] != other[0] and rerun[1] is False


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
    assert old_sha_rerun[1] is True, "cancellation is on for PR runs, so the head run is the one that dies"


def test_a_pr_run_and_a_master_run_never_share_a_group_even_on_one_sha():
    assert _slot(_pr(6744, "d9359dc", 1))[0] != _slot(_push("d9359dc", 2))[0]


def test_cancel_in_progress_is_not_a_bare_true():
    raw = (_workflow().get("concurrency") or {}).get("cancel-in-progress")
    assert raw is not None, "ci.yml has no workflow-level concurrency"
    assert raw is not True, "a literal `true` would cancel master runs"


def test_triggers_jobs_and_release_serialization_are_untouched():
    wf = _workflow()
    on = wf.get("on", wf.get(True))
    assert set(on) == {"pull_request", "push"} and on["push"] == {"branches": ["master"]} and not on["pull_request"]
    assert REQUIRED_JOBS <= set(wf["jobs"]), f"missing jobs: {REQUIRED_JOBS - set(wf['jobs'])}"
    deploy = wf["jobs"]["deploy"]
    assert set(deploy["needs"]) == DEPLOY_NEEDS
    assert deploy["concurrency"] == {"group": "heroku-deploy", "cancel-in-progress": False}
    assert not any("concurrency" in job for name, job in wf["jobs"].items() if name != "deploy")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1; print(f"FAIL {name}: {str(exc)[:110]}")
    sys.exit(1 if failed else 0)
