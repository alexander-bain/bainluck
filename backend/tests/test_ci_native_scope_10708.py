"""#10708 (Alex 77: A): a pure-ios/ pull request runs the native backend readers,
not the full backend.

Executed, not read: the change-scope `decide` step is lifted out of ci.yml and run
against a scratch repository, so the three ways back to `full` (a push, a refused
or empty native test set, a mixed candidate) are each proved by the bytes CI runs.

Pinned here, each one a way the saving silently becomes a hole:

* a push is never native, so the deploy path always runs everything;
* the native test set is the roster PLUS every test that names a native path,
  and any refusal prints nothing (no partial list) and falls back to full;
* on native, the six omitted jobs skip, `native-backend-readers` runs, and every
  `backend-tests` leg (a required context) carries that job's result.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or REPO / ".github" / "workflows" / "ci.yml")
GH = REPO / ".github"
NATIVE_TESTS = GH / "scripts" / "ci-native-tests.sh"
SWIFT = "ios/Bain Luck/Bain Luck/Views/DiscoverView.swift"

OMITTED = (
    "shard-completeness",
    "golden-baseline-floor",
    "database-integration",
    "search-recall",
    "frontend-build",
)
NOT_NATIVE = "needs.change-scope.outputs.scope != 'native'"


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text())["jobs"]


def _decide_script() -> str:
    steps = _jobs()["change-scope"]["steps"]
    return next(s for s in steps if s.get("id") == "decide")["run"]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class Scratch:
    def __init__(self, root: Path):
        self.path = root
        _git(root, "init", "-q", "-b", "master")
        _git(root, "config", "user.email", "t@example.com")
        _git(root, "config", "user.name", "t")
        for rel in (
            "scripts/ci-change-scope.sh",
            "scripts/ci-native-tests.sh",
            "scripts/ci-native-backend-readers.sh",
            "ci-cross-tier-paths.txt",
        ):
            (root / ".github" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(GH / rel, root / ".github" / rel)
        tests = root / "backend" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_rostered.py").write_text("def test_a():\n    pass\n")
        (tests / "test_reads_swift.py").write_text(
            "P = 'ios/Bain Luck/x.swift'\n\ndef test_b():\n    pass\n"
        )
        (tests / "test_unrelated.py").write_text("def test_c():\n    pass\n")
        self.roster("tests/test_rostered.py\n")

    def roster(self, body: str) -> None:
        (self.path / ".github" / "ci-native-backend-readers.txt").write_text(body)

    def commit(self, files: dict[str, str]) -> str:
        for rel, body in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", "x", "--allow-empty")
        return _git(self.path, "rev-parse", "HEAD")

    def decide(self, event: str, base: str, head: str, tmp: Path) -> dict[str, str]:
        script = _decide_script()
        for expr, value in {
            "github.event_name": event,
            "github.event.pull_request.base.sha": base,
            "github.event.pull_request.head.sha": head,
            "github.sha": head,
            "github.event.before": base,
        }.items():
            script = script.replace("${{ " + expr + " }}", value)
        assert "${{" not in script, "an unmodelled expression reached the decide step"
        output = tmp / f"out-{event}-{head[:7]}"
        output.write_text("")
        subprocess.run(
            ["bash", "-c", script],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
            env={
                "PATH": os.environ["PATH"],
                "GITHUB_OUTPUT": str(output),
                "GITHUB_REF": "refs/heads/master" if event == "push" else "refs/pull/1/merge",
            },
        )
        return dict(
            line.split("=", 1) for line in output.read_text().splitlines() if "=" in line
        )


@pytest.fixture
def scratch(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return Scratch(root)


def test_a_pure_ios_pull_request_is_native_with_roster_and_text_readers(scratch, tmp_path):
    base = scratch.commit({SWIFT: "a"})
    head = scratch.commit({SWIFT: "b"})
    out = scratch.decide("pull_request", base, head, tmp_path)
    assert out["scope"] == "native"
    assert out["native_tests"].split() == ["tests/test_reads_swift.py", "tests/test_rostered.py"]


def test_the_same_ios_change_on_a_push_is_always_full(scratch, tmp_path):
    base = scratch.commit({SWIFT: "a"})
    head = scratch.commit({SWIFT: "b"})
    out = scratch.decide("push", base, head, tmp_path)
    assert out["scope"] == "full" and out["native_tests"] == ""


def test_a_refused_roster_falls_back_to_full(scratch, tmp_path):
    scratch.roster("tests/test_missing.py\n")
    base = scratch.commit({SWIFT: "a"})
    head = scratch.commit({SWIFT: "b"})
    out = scratch.decide("pull_request", base, head, tmp_path)
    assert out["scope"] == "full" and out["native_tests"] == ""


def test_negative_control_a_mixed_ios_and_backend_diff_is_full(scratch, tmp_path):
    base = scratch.commit({SWIFT: "a", "backend/app/main.py": "a"})
    head = scratch.commit({SWIFT: "b", "backend/app/main.py": "b"})
    out = scratch.decide("pull_request", base, head, tmp_path)
    assert out["scope"] == "full" and out["native_tests"] == ""


def test_a_frontend_pull_request_is_unchanged(scratch, tmp_path):
    page = "/".join(("frontend", "app", "page.tsx"))  # not a read of the real file
    base = scratch.commit({page: "a"})
    head = scratch.commit({page: "b"})
    out = scratch.decide("pull_request", base, head, tmp_path)
    assert out["scope"] == "frontend" and out["native_tests"] == ""


# --- the native test set on the real tree ------------------------------------


def _native_tests(env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(NATIVE_TESTS)],
        cwd=REPO / "backend",
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **(env or {})},
    )


def test_the_real_native_set_covers_the_roster_and_every_ios_path_reader():
    result = _native_tests()
    assert result.returncode == 0, result.stderr
    selected = result.stdout.split()
    assert selected == sorted(set(selected))
    roster = [
        v
        for raw in (GH / "ci-native-backend-readers.txt").read_text().splitlines()
        if (v := raw.split("#", 1)[0].strip())
    ]
    assert set(roster) <= set(selected)
    tests = REPO / "backend" / "tests"
    readers = {
        p.relative_to(REPO / "backend").as_posix()
        for p in tests.rglob("test_*.py")
        if "ios/" in p.read_text(encoding="utf-8")
    }
    assert readers and readers <= set(selected)
    assert "tests/test_ci_native_scope_10708.py" in selected  # this file names ios/


def test_a_refused_roster_prints_no_partial_list(tmp_path):
    bad = tmp_path / "roster.txt"
    bad.write_text("tests/test_cold_path_charter.py\ntests/test_cold_path_charter.py\n")
    result = _native_tests({"CI_NATIVE_BACKEND_READERS": str(bad)})
    assert result.returncode != 0 and result.stdout == ""


# --- the job graph on a native candidate -------------------------------------


def test_the_omitted_jobs_skip_on_native_and_only_on_native():
    jobs = _jobs()
    for name in OMITTED:
        condition = str(jobs[name]["if"])
        assert NOT_NATIVE in condition, (name, condition)
    for name in ("fast-gate", "e2e-contract", "release-required", "deploy", "change-scope"):
        assert "native" not in str(jobs[name].get("if", "")), name


def test_the_native_job_runs_the_computed_set_and_feeds_every_backend_leg():
    jobs = _jobs()
    native = jobs["native-backend-readers"]
    assert native["needs"] == ["change-scope", "fast-gate"]
    assert native["if"] == (
        "needs.change-scope.outputs.scope == 'native' && needs.change-scope.outputs.live != 'true'"
    )
    run = next(s for s in native["steps"] if s.get("name") == "Run the native backend readers")
    assert run["env"] == {"NATIVE_TESTS": "${{ needs.change-scope.outputs.native_tests }}"}
    assert "python -m pytest $NATIVE_TESTS" in run["run"] and "exit 1" in run["run"]
    assert "test files" in run["run"]  # the count is printed
    backend = jobs["backend-tests"]
    assert "native-backend-readers" in backend["needs"]
    leg = next(s for s in backend["steps"] if str(s.get("name", "")).startswith("Native candidate"))
    assert leg["env"] == {"NATIVE_RESULT": "${{ needs.native-backend-readers.result }}"}
    assert re.search(r'if \[ "\$NATIVE_RESULT" != "success" \]', leg["run"])
    assert jobs["change-scope"]["outputs"]["native_tests"] == "${{ steps.decide.outputs.native_tests }}"


def test_the_deploy_gate_is_untouched():
    deploy = _jobs()["deploy"]
    assert "native-backend-readers" not in deploy["needs"]
    assert "native" not in deploy["if"]


def test_the_native_job_runs_the_ios_guard_suites():
    """Fable, Nov 9: frontend-build is skipped on native, and it was the only job
    running frontend/__tests__/ios (the jest suites that read Swift sources).
    #12436, #12441 and #12443 skipped them; the native job now runs them."""
    steps = _jobs()["native-backend-readers"]["steps"]
    node = [s for s in steps if str(s.get("uses", "")).startswith("actions/setup-node@")]
    assert node and node[0]["with"]["cache-dependency-path"].split("/") == ["frontend", "package-lock.json"]
    run = next(s for s in steps if s.get("name") == "Run the iOS guard suites (frontend/__tests__/ios)")
    assert run["working-directory"] == "frontend"
    assert "npm ci" in run["run"]
    assert re.search(r"npx jest --ci __tests__/ios/\s*$", run["run"])
    # No escape hatches: a red guard is a red native job, so a red required context.
    assert "continue-on-error" not in run and "--passWithNoTests" not in run["run"]
    assert steps.index(node[0]) < steps.index(run)
