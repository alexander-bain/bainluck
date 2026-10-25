"""#11091 EXPLICIT POLICY CHANGE: compose PUSH evidence may pay master test work.

Current composed source still passes every broad gate before Heroku promotion.
Only complete actual-commit compose push evidence with matching master base may
pay a master's repeated execution; PR merge-ref/equal-tree credit is forbidden.

The scratch fixture distills authority/129's note-policy/membership mismatch:
base f57121f5, components 3f421a9e46 (#4954) and 37ca9d96e2 (#5139).
This is a literal minimal semantic reproducer, NOT a replay of those historical
commits, their database, environment, whole suites, or production behavior.

The production path still builds source on Heroku; no build-artifact promotion.
Only authenticated same-commit test provenance may authorize step-level reuse. We
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

from tests.test_ci_matrix_required_contexts import (
    RUNS,
    REUSE,
    SCOPE_RUNS,
    _validate_backend_partition,
)
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


# These are only reviewed workflow-defined keys, not a claim that runner,
# installed-package, test and production environments are equivalent.
JOB_ENV_KEYS = {
    "database-integration": {"DATABASE_URL", "SEARCH_TEST_DATABASE_URL"},
    "deploy": {"HEROKU_API_KEY"},
}
STEP_ENV_KEYS = {
    ("change-scope", "Validate prior exact-commit evidence"): {"GH_TOKEN"},
    (
        "database-integration",
        "#7351 an ordinary market's chart serves the venue history our polls missed",
    ): {"REDIS_URL", "KALSHI_API_KEY"},
    (
        "database-integration",
        "#8000 supported venue history survives display selection",
    ): {"REDIS_URL", "KALSHI_API_KEY"},
    (
        "database-integration",
        "#7547 the phone's selected range keeps the venue's genuine turns",
    ): {"REDIS_URL", "KALSHI_API_KEY"},
    (
        "database-integration",
        "#7548 a ~$45 trade print is not a championship probability",
    ): {"REDIS_URL"},
    # #10090: Discover's ported real-Redis steps each get a private loopback
    # database on the job's redis:7 service (db 13 and db 12); no secret.
    (
        "database-integration",
        "#10090 a slow removal notification never stalls another game or a "
        "healthy price; a recycled worker adopts every owed removal "
        "(real Postgres + Redis)",
    ): {"PM_WITHDRAWAL_REDIS_URL"},
    (
        "database-integration",
        "#10090 an open or reopened page always learns the source removals it "
        "owes, never via an old price (real Postgres + Redis)",
    ): {"PM_WITHDRAWAL_REDIS_URL"},
    # #10090 attempt151's ported controls: loopback redis:7 db 11; no secret.
    # F3's capacity case reuses the job's bl_searchtest under its own random
    # schema (created and dropped by the case); no secret.
    (
        "database-integration",
        "#10090 a held page receives the last committed price after a "
        "publication outage, without a new venue tick (real Postgres + Redis)",
    ): {"PM_WITHDRAWAL_REDIS_URL", "BLEND_DEADLOCK_DATABASE_URL"},
    (
        "database-integration",
        "#10090 a lock-held KALSHI price row stamps the received quote; "
        "a restart cannot undo it (real Postgres)",
    ): {"EVENT_FRAME_REDIS_SERVER", "EVENT_FRAME_REDIS_REQUIRED"},
    ("search-recall", "Every database integration group passed"): {
        "SCOPE_RESULT",
        "INTEGRATION_RESULT",
    },
}

# Receipt values are data, never workflow-expression interpolation in shell.
for _receipt_job in (
    "backend-tests",
    "shard-completeness",
    "database-integration",
    "frontend-build",
):
    STEP_ENV_KEYS[(_receipt_job, "Reused exact-commit test evidence")] = {
        "REUSE_RUN",
        "REUSE_ATTEMPT",
        "REUSE_HEAD",
        "REUSE_BASE",
    }


def _allowed_environment(env, allowed, scope):
    env = {} if env is None else env
    assert isinstance(env, dict), f"{scope} environment must be a mapping"
    assert (
        set(env) <= allowed
    ), f"unreviewed {scope} environment keys: {set(env) - allowed}"


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
    assert step.get("if") in (None, RUNS, REUSE)
    assert "GITHUB_SHA" not in job.get("env", {})
    assert all("GITHUB_SHA" not in s.get("env", {}) for s in job["steps"])
    return step


def _validate_current_composed_promotion(
    jobs, *, workflow_defaults=None, workflow_env=None
):
    """A narrow current-workflow contract, not an arbitrary shell interpreter."""
    if workflow_defaults is None:
        workflow_defaults = _workflow().get("defaults", {})
    if workflow_env is None:
        workflow_env = _workflow().get("env", {})
    _allowed_environment(workflow_env, set(), "workflow")
    for name, job in jobs.items():
        _allowed_environment(
            job.get("env"), JOB_ENV_KEYS.get(name, set()), f"{name} job"
        )
        for step in job.get("steps", []):
            _allowed_environment(
                step.get("env"),
                STEP_ENV_KEYS.get((name, step.get("name")), set()),
                f"{name}/{step.get('name', step.get('uses'))} step",
            )
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
            assert "artifact" not in str(step.get("uses", "")).lower() or (
                name in ("change-scope", "backend-tests")
                and step.get("uses") == "actions/upload-artifact@v4"
                and step.get("name") == "Publish compose checkout provenance"
            ), "only explicit compose test-provenance upload; no build artifact credit"
    for name in ("backend-tests", "shard-completeness", "database-integration"):
        job = jobs[name]
        checkout = _current_checkout(job)
        assert job["defaults"]["run"]["working-directory"] == "backend"
        install = _step(job, "Install dependencies")
        assert (
            install["run"].strip() == "pip install -r requirements.txt"
        ), "current dependencies"
        assert "working-directory" not in install
        assert install.get("if") == (RUNS if name == "backend-tests" else REUSE)
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
    assert len(backend["steps"]) == 9, "new source preparation needs review"
    # #10090 attempt163, the one reviewed addition: a test binary supplied
    # outside the checkout. It runs no git and installs nothing, so it cannot
    # change the source, the dependencies or the test selection under test.
    redis = _step(backend, "Private redis-server binary")
    assert redis.get("if") == RUNS
    steps = backend["steps"]
    assert steps.index(_step(backend, "Install dependencies")) < steps.index(
        redis
    ) < steps.index(command)
    assert "git " not in redis["run"] and "pip install" not in redis["run"]
    exported = [
        line.split("=", 1)[0].removeprefix('echo "')
        for line in redis["run"].splitlines()
        if "GITHUB_ENV" in line
    ]
    assert sorted(exported) == [
        "EVENT_FRAME_REDIS_REQUIRED",
        "EVENT_FRAME_REDIS_SERVER",
    ], exported
    verifier = jobs["shard-completeness"]
    assert verifier.get("if") == SCOPE_RUNS
    assert verifier["steps"][-1].get("if") == REUSE
    aggregate = jobs["search-recall"]
    assert set(aggregate["needs"]) == {"change-scope", "database-integration"}
    assert aggregate["if"] == f"always() && {SCOPE_RUNS}"
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


@pytest.mark.parametrize(
    "scope,job_name,step_prefix,key,value",
    [
        ("workflow", None, None, "PYTEST_ADDOPTS", "-k startup"),
        ("workflow", None, None, "BASH_ENV", "/tmp/skip-body.sh"),
        ("job", "backend-tests", None, "PYTEST_ADDOPTS", "-k startup"),
        ("job", "shard-completeness", None, "PYTEST_ADDOPTS", "-k startup"),
        ("job", "database-integration", None, "PYTEST_ADDOPTS", "-k startup"),
        ("job", "deploy", None, "BASH_ENV", "/tmp/skip-body.sh"),
        ("step", "backend-tests", "Run tests", "BASH_ENV", "/tmp/skip-body.sh"),
        ("step", "backend-tests", "Run tests", "PYTEST_ADDOPTS", "-k startup"),
        (
            "step",
            "backend-tests",
            "Install dependencies",
            "PIP_CONFIG_FILE",
            "/tmp/component-pip.conf",
        ),
        (
            "step",
            "database-integration",
            "#7351 an ordinary market's chart serves the venue history our polls missed",
            "PYTEST_ADDOPTS",
            "-k startup",
        ),
        (
            "step",
            "search-recall",
            "Every database integration group passed",
            "BASH_ENV",
            "/tmp/skip-body.sh",
        ),
        ("step", "deploy", "Deploy to Heroku", "BASH_ENV", "/tmp/skip-body.sh"),
    ],
)
def test_unreviewed_environment_cannot_change_the_guarded_execution(
    scope, job_name, step_prefix, key, value
):
    workflow = copy.deepcopy(_workflow())
    jobs = workflow["jobs"]
    if scope == "workflow":
        workflow.setdefault("env", {})[key] = value
    elif scope == "job":
        jobs[job_name].setdefault("env", {})[key] = value
    else:
        _step(jobs[job_name], step_prefix).setdefault("env", {})[key] = value
    with pytest.raises(AssertionError, match="environment"):
        _validate_current_composed_promotion(jobs, workflow_env=workflow.get("env", {}))


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
