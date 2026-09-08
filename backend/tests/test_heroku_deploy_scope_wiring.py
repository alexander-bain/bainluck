"""SHIP 2 (integrator/150): frontend-only merges must not release Heroku.

WHY THIS EXISTS. Before 2026-09-08 the `deploy` job had no path filter: 549
master merges in seven days, 105 frontend-only by path, all 105 released. The
filter that fixes that is one `if:` away from two much worse failures than the
one it cures, so this file guards both halves.

1. **It stops releasing the backend.** A filter that reads "frontend-only" too
   eagerly -- or a fail-open path where the diff could not be computed -- turns
   a backend fix into a green CI run that never ships. Every degenerate input
   here is asserted to DEPLOY, not to skip.
2. **It never actually skips.** A filter wired to a step whose output nothing
   reads, or a deploy step that lost its `if:`, is 105 needless releases a week
   wearing a green square.

The logic tests call `tools/ci/heroku_deploy_scope.py` directly rather than
re-implementing its rule, so a change to the allowlist has to come here and say
so. The wiring tests parse `ci.yml` -- the same approach, and the same reason,
as `test_golden_floor_ci_wiring_3761.py`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SCOPE_SCRIPT = REPO_ROOT / "tools" / "ci" / "heroku_deploy_scope.py"


def _load_scope_module():
    spec = importlib.util.spec_from_file_location("heroku_deploy_scope", SCOPE_SCRIPT)
    assert spec and spec.loader, f"cannot load {SCOPE_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["heroku_deploy_scope"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scope():
    if not SCOPE_SCRIPT.exists():
        pytest.fail(f"{SCOPE_SCRIPT} is missing — the deploy filter cannot run")
    return _load_scope_module()


@pytest.fixture(scope="module")
def ci_config():
    if not CI_WORKFLOW.exists():
        pytest.fail(f"{CI_WORKFLOW} is missing")
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def deploy_job(ci_config):
    jobs = ci_config.get("jobs", {})
    assert "deploy" in jobs, "the `deploy` job has been renamed or removed"
    return jobs["deploy"]


# --------------------------------------------------------------------------
# The decision itself
# --------------------------------------------------------------------------


def test_a_frontend_only_change_does_not_need_heroku(scope):
    assert (
        scope.heroku_needed(
            [
                "frontend/components/discover/FuturesCard.tsx",
                "frontend/__tests__/components/leaderboardSingleRule3999.test.tsx",
            ]
        )
        is False
    )


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/utils/feed_reasons.py",
        "backend/alembic/versions/abc123_add_column.py",
        "Procfile",
        "requirements.txt",
        "runtime.txt",
        "app.json",
        ".github/workflows/ci.yml",
        "ios/Bain Luck/Bain Luck/Views/EventDetailView.swift",
        "docs/PRODUCT-BRAIN.md",
        "tools/ci/heroku_deploy_scope.py",
        "some-new-top-level-thing/main.py",
    ],
)
def test_anything_outside_the_allowlist_deploys(scope, path):
    """The allowlist is the whole rule; an unrecognised path is never a skip.

    `ios/`, `docs/` and `tools/` are in here on purpose. They are genuinely not
    served by Heroku, and someone will eventually want to add them -- that is a
    measured decision, and until it is made this test is what says so.
    """
    assert scope.heroku_needed([path]) is True


def test_one_backend_path_among_many_frontend_paths_still_deploys(scope):
    """The batch merge case: mixed commits must release."""
    assert (
        scope.heroku_needed(
            [
                "frontend/components/discover/ConceptCard.tsx",
                "frontend/components/SettledOutcomeMark.tsx",
                "backend/app/utils/feed_reasons.py",
            ]
        )
        is True
    )


@pytest.mark.parametrize("paths", [[], [""], ["   "], ["\n"]])
def test_an_unresolved_diff_deploys_rather_than_skipping(scope, paths):
    """ "We could not tell what changed" must never read as "nothing changed"."""
    assert scope.heroku_needed(paths) is True


def test_a_sibling_of_the_allowlisted_prefix_is_not_covered(scope):
    """`frontend/` carries a trailing slash so it cannot swallow a neighbour."""
    assert scope.heroku_needed(["frontend-notes.md"]) is True
    assert scope.heroku_needed(["frontend_config.py"]) is True


def test_the_cli_prints_a_parseable_decision(scope, capsys, tmp_path):
    paths_file = tmp_path / "changed.txt"
    paths_file.write_text("frontend/app/page.tsx\n", encoding="utf-8")

    assert scope.main(["--paths-from", str(paths_file)]) == 0
    assert capsys.readouterr().out.strip() == "heroku_needed=0"

    paths_file.write_text("backend/app/main.py\n", encoding="utf-8")
    assert scope.main(["--paths-from", str(paths_file)]) == 0
    assert capsys.readouterr().out.strip() == "heroku_needed=1"


def test_the_decider_exits_zero_even_when_it_says_deploy(scope, tmp_path):
    """It is a decision, not a gate.

    A non-zero exit would be read by the workflow's fail-closed arm, which is
    correct but wasteful; more importantly a future caller must not be tempted
    to treat the exit code as the answer and invert it.
    """
    paths_file = tmp_path / "changed.txt"
    paths_file.write_text("backend/app/main.py\n", encoding="utf-8")
    assert scope.main(["--paths-from", str(paths_file)]) == 0


# --------------------------------------------------------------------------
# The wiring
# --------------------------------------------------------------------------


def _steps(deploy_job) -> list[dict]:
    return [s for s in deploy_job.get("steps", []) if isinstance(s, dict)]


def test_the_scope_step_exists_and_is_identified(deploy_job):
    ids = {step.get("id") for step in _steps(deploy_job)}
    assert "scope" in ids, (
        "the deploy job has no step with `id: scope` — either the filter was "
        "removed, or its id changed and the deploy step's `if:` now reads an "
        "empty string, which would skip EVERY release"
    )


def test_the_deploy_step_is_gated_on_the_scope_decision(deploy_job):
    deploy_steps = [
        s for s in _steps(deploy_job) if "Deploy to Heroku" in str(s.get("name", ""))
    ]
    assert len(deploy_steps) == 1, "expected exactly one Heroku deploy step"

    condition = str(deploy_steps[0].get("if", ""))
    assert "steps.scope.outputs.heroku_needed" in condition, (
        "the Heroku deploy step is no longer gated on the scope decision — "
        "frontend-only merges are releasing again"
    )
    assert "== '1'" in condition.replace('"', "'"), (
        "the gate must deploy on an explicit '1'. Testing for != '0' would "
        "deploy on a missing output, but testing for truthiness would skip on "
        "one — and a missing output is exactly the fail-closed case."
    )


def test_the_scope_step_is_not_a_needs_dependency(ci_config):
    """A skipped `needs:` skips its dependents — see ci.yml's ~line 214 warning.

    If the scoping logic is ever promoted to its own job and added to
    `deploy.needs`, every release stops. This pins it in-job.
    """
    deploy_needs = ci_config["jobs"]["deploy"].get("needs", [])
    assert "scope" not in deploy_needs
    assert "deploy-scope" not in deploy_needs


def test_the_scope_step_cannot_be_silently_neutralised(deploy_job):
    """No `continue-on-error`, and no `|| true` around the decider."""
    scope_steps = [s for s in _steps(deploy_job) if s.get("id") == "scope"]
    assert scope_steps, "no scope step to check"
    step = scope_steps[0]

    assert not step.get("continue-on-error"), (
        "continue-on-error on the scope step would let a crashed decider leave "
        "`heroku_needed` unset"
    )

    run = step.get("run", "")
    assert "heroku_deploy_scope.py" in run, "the scope step no longer calls the decider"
    assert "|| true" not in run, (
        "a `|| true` around the decider would swallow its failure and leave the "
        "output unset (gotcha #124)"
    )


def test_every_failure_path_in_the_scope_step_deploys(deploy_job):
    """Each early exit in the step must set `heroku_needed=1`, never 0.

    The step has four fail-closed arms (unresolvable `before`, failed diff,
    failed decider, unparseable decision). This asserts the shape rather than
    the prose: the only place `heroku_needed=0` may enter GITHUB_OUTPUT is by
    echoing the decider's own verdict.
    """
    scope_steps = [s for s in _steps(deploy_job) if s.get("id") == "scope"]
    run = scope_steps[0].get("run", "")

    hardcoded_skips = [
        line
        for line in run.splitlines()
        if "heroku_needed=0" in line and "GITHUB_OUTPUT" in line
    ]
    assert not hardcoded_skips, (
        "a literal `heroku_needed=0` is written to GITHUB_OUTPUT: "
        f"{hardcoded_skips}. The skip must only ever come from the decider."
    )

    assert run.count('echo "heroku_needed=1" >> "$GITHUB_OUTPUT"') >= 4, (
        "expected every fail-closed arm to write heroku_needed=1; if an arm was "
        "removed, make sure it did not become a fail-OPEN path"
    )
