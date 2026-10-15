"""Current composed master must pass its own broad CI before Heroku promotion.

The scratch fixture distills authority/129's note-policy/membership mismatch:
base f57121f5, components 3f421a9e46 (#4954) and 37ca9d96e2 (#5139).
This is a literal minimal semantic reproducer, NOT a replay of those historical
commits, their database, environment, whole suites, or production behavior.

The production path rebuilds/tests source and accepts no artifact credit. We
reuse the actual matrix guard; existing DB aggregate and deployGuard.contract
controls own executable DB outcome and deploy-script behavior. GitHub's
success-only dependency scheduling remains a platform contract. No failing
hosted run, production deployment, or artifact-promotion API is introduced.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest
import yaml

from tests.test_ci_matrix_required_contexts import RUNS, _validate_backend_partition
from tests.test_ci_supersede_concurrency import DEPLOY_NEEDS

ROOT = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or ROOT / ".github/workflows/ci.yml")
DEPLOY_IF = (
    "github.ref == 'refs/heads/master' && github.event_name == 'push' && "
    "needs.release-required.outputs.required != 'false'"
)
# Exact approved shell grammar prevents overwriting FILES, component-only tests
# or swallowing assertions while leaving the expected command as a substring.
BACKEND_COMMAND = """set -o pipefail
FILES="$(python scripts/ci_shard.py --shard ${{ matrix.shard }} --of ${{ strategy.job-total }})"
if [ -z "$FILES" ]; then
  echo "::error::shard ${{ matrix.shard }} resolved to ZERO test files — the"
  echo "::error::partition is broken and this leg would pass without testing anything."
  exit 1
fi
echo "shard ${{ matrix.shard }}/${{ strategy.job-total }}: $(echo $FILES | wc -w) test files"
python -m pytest $FILES -q --durations=0
"""


def _workflow():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _jobs():
    return _workflow()["jobs"]


def _step(job, prefix):
    found = [s for s in job["steps"] if s.get("name", "").startswith(prefix)]
    assert len(found) == 1, f"one actual {prefix!r} step required"
    return found[0]


def _current_checkout(job):
    found = [
        s
        for s in job["steps"]
        if str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(found) == 1, "one checkout of current workflow source"
    step = found[0]
    inputs = step.get("with", {})
    assert inputs.get("ref") in (None, "${{ github.sha }}"), "old/component source"
    assert set(inputs) <= {
        "ref",
        "fetch-depth",
        "filter",
    }, "foreign/relocated/unreviewed checkout"
    assert step.get("if") in (None, RUNS)
    assert "GITHUB_SHA" not in job.get("env", {})
    assert all("GITHUB_SHA" not in s.get("env", {}) for s in job["steps"])
    return step


def _validate_current_composed_promotion(jobs, *, workflow_defaults=None):
    """A narrow current-workflow contract, not an arbitrary shell interpreter."""
    if workflow_defaults is None:
        workflow_defaults = _workflow().get("defaults", {})
    # A custom shell may exit successfully without executing {0}, regardless
    # of the guarded run bytes. All three inheritance scopes must retain the
    # reviewed runner-default shell, including sibling/aggregate gate jobs.
    assert "shell" not in workflow_defaults.get("run", {}), "unreviewed workflow shell"
    for name, job in jobs.items():
        assert "shell" not in job.get("defaults", {}).get(
            "run", {}
        ), f"{name} job shell"
        assert all(
            "shell" not in step for step in job.get("steps", [])
        ), f"{name} step shell"
    _validate_backend_partition(jobs)
    deploy = jobs["deploy"]
    assert set(deploy["needs"]) == DEPLOY_NEEDS, "all broad gates precede promotion"
    assert deploy.get("if") == DEPLOY_IF, "no always/failure/cancelled bypass"
    assert "if" not in jobs["backend-tests"], "backend matrix must expand"
    for name in DEPLOY_NEEDS | {"change-scope", "database-integration", "deploy"}:
        job = jobs[name]
        assert "continue-on-error" not in job, f"{name} failure cannot be waived"
        for step in job["steps"]:
            assert (
                "continue-on-error" not in step
            ), f"{name} step failure cannot be waived"
            assert (
                "artifact" not in str(step.get("uses", "")).lower()
            ), "no artifact credit"
    for name in ("backend-tests", "shard-completeness", "database-integration"):
        job = jobs[name]
        checkout = _current_checkout(job)
        assert job["defaults"]["run"]["working-directory"] == "backend"
        install = _step(job, "Install dependencies")
        assert (
            install["run"].strip() == "pip install -r requirements.txt"
        ), "current dependencies"
        assert "working-directory" not in install
        assert install.get("if") == (RUNS if name == "backend-tests" else None)
        assert job["steps"].index(checkout) < job["steps"].index(install)
    backend = jobs["backend-tests"]
    command = _step(backend, "Run tests")
    assert command.get("if") == RUNS
    assert (
        command["run"].strip() == BACKEND_COMMAND.strip()
    ), "full current partition execution"
    assert "working-directory" not in command
    assert backend["steps"].index(_step(backend, "Install dependencies")) < backend[
        "steps"
    ].index(command)
    assert len(backend["steps"]) == 5, "new source preparation needs review"
    verifier = jobs["shard-completeness"]
    assert verifier.get("if") == RUNS
    assert verifier["steps"][-1].get("if") is None
    aggregate = jobs["search-recall"]
    assert set(aggregate["needs"]) == {"change-scope", "database-integration"}
    assert aggregate["if"] == f"always() && {RUNS}"
    for name in ("frontend-build", "e2e-contract", "release-required", "deploy"):
        _current_checkout(jobs[name])
    assert jobs["frontend-build"].get("if") is None
    assert jobs["e2e-contract"].get("if") is None
    assert len(deploy["steps"]) == 2, "no artifact substitution step"
    assert _current_checkout(deploy) is deploy["steps"][0]
    program = _step(deploy, "Deploy to Heroku")["run"]
    lines = [
        s.strip()
        for s in program.splitlines()
        if s.strip() and not s.lstrip().startswith("#")
    ]
    assert [s for s in lines if s.startswith("git remote add ")] == [
        "git remote add heroku https://heroku:$HEROKU_API_KEY@git.heroku.com/bainluck.git 2>/dev/null || true"
    ], "fixed main app target"
    pushes = [s for s in lines if re.match(r"(?:if )?git push\b", s)]
    assert len(pushes) == 3, "normal/retry/tip recovery remain explicit source pushes"
    for line in pushes:
        tokens = shlex.split(re.sub(r";\s*then$", "", line.removeprefix("if ")))
        assert tokens[:4] == [
            "git",
            "push",
            "heroku",
            "$GITHUB_SHA:refs/heads/master",
        ], "exact run SHA"
        assert tokens[4:] in ([], ["--force"])


def test_actual_workflow_requires_current_composed_source_before_main_promotion():
    _validate_current_composed_promotion(_jobs())


@pytest.mark.parametrize(
    "mutation",
    [
        "lost_backend_dependency",
        "job_allow_failure",
        "step_allow_failure",
        "deploy_allow_failure",
        "failure_override",
        "old_backend_checkout",
        "old_deploy_checkout",
        "component_checkout",
        "foreign_checkout",
        "old_dependencies",
        "dependency_workdir",
        "component_only_tests",
        "overwritten_partition",
        "swallowed_assertion",
        "wrong_app",
        "component_push",
        "artifact_substitution",
        "lost_database_aggregate",
        "conditional_verifier",
    ],
)
def test_current_source_guard_rejects_substituted_or_partial_promotion(mutation):
    jobs = copy.deepcopy(_jobs())
    backend, deploy = jobs["backend-tests"], jobs["deploy"]
    if mutation == "lost_backend_dependency":
        deploy["needs"].remove("backend-tests")
    elif mutation in ("job_allow_failure", "deploy_allow_failure"):
        (backend if mutation == "job_allow_failure" else deploy)[
            "continue-on-error"
        ] = True
    elif mutation == "step_allow_failure":
        _step(backend, "Run tests")["continue-on-error"] = True
    elif mutation == "failure_override":
        deploy["if"] = f"always() && ({DEPLOY_IF})"
    elif mutation in (
        "old_backend_checkout",
        "old_deploy_checkout",
        "component_checkout",
        "foreign_checkout",
    ):
        inputs = _current_checkout(
            deploy if mutation == "old_deploy_checkout" else backend
        ).setdefault("with", {})
        if mutation == "foreign_checkout":
            inputs["repository"] = "example/component"
        else:
            inputs["ref"] = (
                "component-a" if mutation == "component_checkout" else "f57121f5"
            )
    elif mutation == "old_dependencies":
        _step(backend, "Install dependencies")[
            "run"
        ] = "git show f57121f5:backend/requirements.txt > /tmp/old.txt\npip install -r /tmp/old.txt"
    elif mutation == "dependency_workdir":
        _step(backend, "Install dependencies")[
            "working-directory"
        ] = "../component/backend"
    elif mutation in (
        "component_only_tests",
        "overwritten_partition",
        "swallowed_assertion",
    ):
        step = _step(backend, "Run tests")
        if mutation == "component_only_tests":
            step["run"] = step["run"].replace(
                "python -m pytest $FILES", "python -m pytest tests/test_startup.py"
            )
        elif mutation == "overwritten_partition":
            step["run"] = step["run"].replace(
                "python -m pytest", "FILES=tests/test_startup.py\npython -m pytest"
            )
        else:
            step["run"] += "true\n"
    elif mutation in ("wrong_app", "component_push"):
        step = _step(deploy, "Deploy to Heroku")
        old, new = (
            ("/bainluck.git", "/other-app.git")
            if mutation == "wrong_app"
            else ("$GITHUB_SHA:refs/heads/master", "component-a:refs/heads/master")
        )
        step["run"] = step["run"].replace(old, new)
    elif mutation == "artifact_substitution":
        deploy["steps"].insert(
            1,
            {
                "uses": "actions/download-artifact@v4",
                "with": {"name": "component-green"},
            },
        )
    elif mutation == "lost_database_aggregate":
        jobs["search-recall"]["needs"].remove("database-integration")
    else:
        jobs["shard-completeness"]["steps"][-1]["if"] = "false"
    with pytest.raises(AssertionError):
        _validate_current_composed_promotion(jobs)


@pytest.mark.parametrize(
    "scope,job_name,step_prefix",
    [
        ("workflow", None, None),
        ("job", "backend-tests", None),
        ("job", "shard-completeness", None),
        ("job", "search-recall", None),
        ("job", "deploy", None),
        ("step", "backend-tests", "Run tests"),
        ("step", "database-integration", "Install dependencies"),
        ("step", "deploy", "Deploy to Heroku"),
    ],
)
def test_custom_shell_cannot_skip_guarded_run_body(scope, job_name, step_prefix):
    workflow = copy.deepcopy(_workflow())
    jobs = workflow["jobs"]
    bypass = "bash -c 'exit 0' {0}"
    if scope == "workflow":
        workflow.setdefault("defaults", {}).setdefault("run", {})["shell"] = bypass
    elif scope == "job":
        jobs[job_name].setdefault("defaults", {}).setdefault("run", {})[
            "shell"
        ] = bypass
    else:
        _step(jobs[job_name], step_prefix)["shell"] = bypass
    with pytest.raises(AssertionError, match="shell"):
        _validate_current_composed_promotion(
            jobs, workflow_defaults=workflow.get("defaults", {})
        )


# Literal minimal historical shape, not historical dependency reconstruction.
POLICY = """RULED = frozenset({"americanfootball_nfl"})
STANDING = {"americanfootball_nfl": "espn"}

def authority_note(sport):
    if sport in RULED:
        return "Alex ruled this sport may fail over WITHOUT a certification streak"
    return "Flipping needs seven consecutive daily gate states"
"""
BASE_CHECK = """import unittest
from policy import authority_note
class NoteCheck(unittest.TestCase):
    def test_unruled_sport_remains_gated(self):
        self.assertIn("seven consecutive", authority_note("icehockey_nhl"))
"""
FLIPPED_POLICY = POLICY.replace('"espn"', '"statpal"').replace(
    "    if sport in RULED:",
    '    if STANDING.get(sport) == "statpal":\n        return "THIS SPORT HAS FLIPPED. StatPal is its standing source of record"\n    if sport in RULED:',
)
STANDING_CHECK = """import unittest
from policy import STANDING, authority_note
class StandingCheck(unittest.TestCase):
    def test_football_is_standing(self):
        self.assertEqual(STANDING["americanfootball_nfl"], "statpal")
        self.assertIn("THIS SPORT HAS FLIPPED", authority_note("americanfootball_nfl"))
"""
MEMBERSHIP_CHECK = """import unittest
from policy import RULED, authority_note
class MembershipCheck(unittest.TestCase):
    def test_every_ruled_sport_says_so_on_its_own_row(self):
        for sport in ("americanfootball_nfl", "icehockey_nhl"):
            ruled_by_note = "may fail over WITHOUT a certification streak" in authority_note(sport)
            self.assertEqual(ruled_by_note, sport in RULED, sport)
"""


def test_conflict_free_components_cannot_replace_composed_master_assertions(tmp_path):
    repo = tmp_path / "composition"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )

    def commit(branch, message):
        assert git("symbolic-ref", "--short", "HEAD").stdout.strip() == branch
        git("add", ".")
        git("commit", "-qm", message)
        return git("rev-parse", "HEAD").stdout.strip()

    def check():
        # -B prevents stale equal-size/mtime bytecode from hiding source changes.
        # Pure unittest avoids importing project fixtures/plugins in scratch Git.
        return subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                ".",
                "-p",
                "test_*.py",
                "-q",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=20,
        )

    git("init", "-q", "-b", "codex/base")
    git("config", "user.name", "Composition fixture")
    git("config", "user.email", "composition@example.invalid")
    (repo / "policy.py").write_text(POLICY)
    (repo / "test_note.py").write_text(BASE_CHECK)
    base = commit("codex/base", "minimal baseline; provenance f57121f5")
    result = check()
    assert result.returncode == 0, result.stderr
    assert "Ran 1 test" in result.stderr
    git("switch", "-qc", "codex/component-a")
    (repo / "policy.py").write_text(FLIPPED_POLICY)
    (repo / "test_standing.py").write_text(STANDING_CHECK)
    a = commit("codex/component-a", "standing-note change; provenance 3f421a9e46")
    result = check()
    assert result.returncode == 0, result.stderr
    assert "Ran 2 tests" in result.stderr
    git("switch", "-qc", "codex/component-b", base)
    (repo / "test_membership.py").write_text(MEMBERSHIP_CHECK)
    b = commit("codex/component-b", "membership-note assertion; provenance 37ca9d96e2")
    result = check()
    assert result.returncode == 0, result.stderr
    assert "Ran 2 tests" in result.stderr
    conflict_check = git("merge-tree", "--write-tree", a, b)
    composed_tree = conflict_check.stdout.strip().splitlines()[0]
    git("switch", "codex/component-a")
    assert (
        git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "codex/component-a"
    )
    git("merge", "--no-ff", "--no-edit", b)
    composed_head = git("rev-parse", "HEAD").stdout.strip()
    assert git("rev-parse", "HEAD^{tree}").stdout.strip() == composed_tree
    assert len({base, a, b, composed_head}) == 4
    result = check()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AssertionError: False != True : americanfootball_nfl" in result.stderr
    assert "FAILED (failures=1)" in result.stderr and "Ran 3 tests" in result.stderr
    # Existing actual workflow wiring, with no component-result substitution.
    # Platform scheduling itself is not simulated by this local assertion.
    _validate_current_composed_promotion(_jobs())
