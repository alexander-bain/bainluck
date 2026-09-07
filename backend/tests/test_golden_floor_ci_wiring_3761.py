"""#3761: the golden floor guard has to RUN, and has to be able to FAIL.

WHY THIS EXISTS. `scripts/check_golden_baseline_floor.py` (CERT-2166/2170) and
`test_golden_baseline_floor_guard_3564.py` between them prove the guard's LOGIC
is right. Neither proves it is ever pointed at a real proposal. It shipped as a
command a merge desk could type, which means the read integrator/239 did by hand
on 2026-09-06 -- a branch carrying `passing_count: 665` over master's 668, with
no conflict, no reviewable diff line and `git merge-tree` exit 0 -- depended on
somebody remembering to type it.

So this file guards the WIRING, and it guards it against the two ways a wired
gate is still not a gate:

1. **It never runs.** No job, a renamed script, or a checkout too shallow for
   `origin/master` to exist -- the last one being the interesting case, because
   the script then exits 2 and says "The comparison did NOT run", to a log that
   nobody opens on a run whose square is green.
2. **It runs and cannot fail.** `continue-on-error`, a `|| true`, or a pipe that
   replaces the command's exit code with the pipeline's (gotcha #124).

And it pins the reason the job is PULL-REQUEST ONLY, which is the part most
likely to look like an oversight and get "fixed": the script defends the working
tree against `--target origin/master`, so on a push to master it compares the
tip against ITSELF. `test_a_push_run_would_be_structurally_incapable_of_failing`
demonstrates that with the script's own comparator rather than asserting it, so
that if the default target ever changes to something a push COULD fail against,
this file goes red and asks for the exclusion to be reconsidered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_golden_baseline_floor import compare_baselines  # noqa: E402

JOB_NAME = "golden-baseline-floor"
SCRIPT_REL = "scripts/check_golden_baseline_floor.py"


@pytest.fixture(scope="module")
def job() -> dict:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    jobs = workflow["jobs"]
    assert JOB_NAME in jobs, (
        f"ci.yml has no `{JOB_NAME}` job. The golden floor guard is then a "
        "command nobody runs, and a baseline can drop its floor on a PR with no "
        "conflict and no reviewable diff line -- see #3564 and the CERT-2152 "
        "bounce. Re-add the job; do not delete this test."
    )
    return jobs[JOB_NAME]


def _run_steps(job: dict) -> list[dict]:
    return [s for s in job["steps"] if "run" in s]


# =============================================================================
# 1 -- it runs
# =============================================================================


def test_the_job_actually_invokes_the_floor_script(job):
    commands = " ".join(s["run"] for s in _run_steps(job))
    assert SCRIPT_REL in commands, (
        f"the `{JOB_NAME}` job does not invoke {SCRIPT_REL}. A job that installs "
        "python and runs nothing is a green square, which is worse than an "
        f"absent job because it reads as coverage. Steps ran: {commands!r}"
    )


def test_the_script_the_job_names_exists_on_disk(job):
    """A rename would exit 2 in CI; catch it here, where the message is cheap."""
    assert (BACKEND_ROOT / SCRIPT_REL).is_file(), (
        f"ci.yml's `{JOB_NAME}` job runs {SCRIPT_REL}, which does not exist "
        f"under {BACKEND_ROOT}. Update both together."
    )


def test_the_checkout_is_deep_enough_for_origin_master_to_exist(job):
    """The whole gate turns into exit 2 without this, and exit 2 is not a pass.

    A default `actions/checkout` on a pull_request lands a detached merge ref at
    depth 1. `origin/master` does not exist there, `git show origin/master:<blob>`
    fails, and the script raises BlobUnreadable and returns 2. It says so loudly
    on stderr, but a shallow checkout is the kind of change made for speed by
    someone who will never read this job's log.
    """
    checkouts = [s for s in job["steps"] if "actions/checkout" in s.get("uses", "")]
    assert checkouts, f"`{JOB_NAME}` has no checkout step at all"
    depth = checkouts[0].get("with", {}).get("fetch-depth")
    assert depth == 0, (
        f"`{JOB_NAME}` checks out with fetch-depth={depth!r}. It must be 0, or "
        "`origin/master` will not exist in the PR checkout, the script will exit "
        "2 (`The comparison did NOT run`), and the only signal will be in a log. "
        "backend-tests carries the same pair for the same reason."
    )


# =============================================================================
# 2 -- it can fail
# =============================================================================


def test_nothing_swallows_the_scripts_exit_code(job):
    """gotcha #124: 1 is a result, 2 is a story about the harness, both must fail."""
    assert not job.get("continue-on-error"), (
        f"`{JOB_NAME}` sets continue-on-error, so a fallen floor reports green."
    )
    for step in _run_steps(job):
        assert not step.get("continue-on-error"), (
            f"a step in `{JOB_NAME}` sets continue-on-error: {step.get('name')!r}"
        )
        command = step["run"]
        if SCRIPT_REL not in command:
            continue
        for swallower in ("|| true", "|| :", "; true", "|"):
            assert swallower not in command, (
                f"the floor check is written as {command!r}, which contains "
                f"{swallower!r}. The step's exit status must BE the script's: "
                "exit 1 means the floor fell without naming what fell, exit 2 "
                "means the comparison never ran. Neither may report success."
            )


# =============================================================================
# 3 -- the pull-request-only exclusion is reasoned, and stays reasoned
# =============================================================================


def test_the_job_is_restricted_to_pull_requests(job):
    condition = job.get("if", "")
    assert "pull_request" in condition, (
        f"`{JOB_NAME}` is expected to carry an `if` restricting it to "
        f"pull_request events; found {condition!r}. See the next test for why: "
        "a push run compares master against itself and cannot fail."
    )


def test_a_push_run_would_be_structurally_incapable_of_failing():
    """The reason for the exclusion, demonstrated rather than asserted.

    On a push to master the working tree IS `origin/master`, so target and
    proposal are the same blob. Shown with ONE baseline judged twice: the exact
    blob a PR run refuses -- a pair silently stopped passing, no reset_reason --
    is accepted when it is compared against itself. Same content, same
    comparator, opposite verdict; the only variable is the target.

    That is the whole argument for the `if:`. If the job's default target ever
    becomes something a push could genuinely fail against, this test goes red
    first, in a file that explains the trade, instead of the exclusion quietly
    outliving its reason.
    """

    def _b(pairs: dict[str, bool], reset_reason=None) -> dict:
        return {
            "pair_count": len(pairs),
            "passing_count": sum(pairs.values()),
            "reset_reason": reset_reason,
            "pairs": pairs,
        }

    floor_of_record = _b({"kalshi:one": True, "kalshi:two": True})
    silent_drop = _b({"kalshi:one": True, "kalshi:two": False})

    on_a_pull_request = compare_baselines(floor_of_record, silent_drop)
    assert not on_a_pull_request.ok, (
        "the control failed: a pair silently dropping was expected to REFUSE "
        "against the floor of record, and the contrast below means nothing "
        f"without it. Verdict: {on_a_pull_request}"
    )
    assert on_a_pull_request.fell == ["kalshi:two"]

    on_a_push = compare_baselines(silent_drop, silent_drop)
    assert on_a_push.ok, (
        "a self-comparison was expected to ACCEPT; if it can now refuse, a push "
        "run carries real signal and the pull_request-only `if` should be "
        f"reconsidered. Problems reported: {on_a_push.problems}"
    )
    assert on_a_push.fell == [] and on_a_push.dropped == []
