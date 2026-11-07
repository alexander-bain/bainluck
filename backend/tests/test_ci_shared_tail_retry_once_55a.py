"""Decide 55-A (Alex, Nov 6): the shared tail re-runs a failed test once, logged.

The shared-tail rigs (real Postgres + Redis, timing-sensitive) failed four of
seven attempts on Nov 6 on near-identical code, and each hit cost a hand re-run
and a deploy. The rule Alex picked: retry once inside the job; a second failure
still fails; every retry stays visible. The real fix (barrier, not clock) is a
dated Todo under #10090.

Pinned here, each one a way the retry silently becomes a waiver:

* the retry count is exactly 1, and it applies to the shared tail ONLY;
* the plugin is the pinned wheel, checked by sha256, installed without deps;
* a retry prints a `::warning::` annotation, so a pass-on-retry is never a
  clean green.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

import yaml

from tests.conftest import rerun_annotation

REPO = Path(__file__).resolve().parents[2]
CI = Path(os.environ.get("CI_WORKFLOW_PATH") or REPO / ".github" / "workflows" / "ci.yml")
PLUGIN_STEP = "#55-A shared tail — provision the pinned retry-once plugin"
WHEEL_SHA = "edf1886209c2b7dafe35b5bf1708d6ec40ccf6c6b357f0f02807efcec0204c99"


def _worker() -> dict:
    return yaml.safe_load(CI.read_text())["jobs"]["database-integration"]


def _addopts_for(group: str) -> str:
    expr = _worker()["env"]["PYTEST_ADDOPTS"]
    m = re.fullmatch(
        r"\$\{\{ matrix\.group == '([\w-]+)' && '([^']*)' \|\| '' \}\}", expr
    )
    assert m, f"PYTEST_ADDOPTS is not the reviewed one-group expression: {expr!r}"
    return m.group(2) if group == m.group(1) else ""


def test_only_the_shared_tail_retries_and_only_once():
    assert _addopts_for("shared-tail") == "--reruns 1 -rR"
    for group in _worker()["strategy"]["matrix"]["group"]:
        if group != "shared-tail":
            assert _addopts_for(group) == "", group


def test_the_plugin_is_the_pinned_wheel_checked_by_hash_without_deps():
    steps = _worker()["steps"]
    step = next(s for s in steps if s.get("name") == PLUGIN_STEP)
    assert "matrix.group == 'shared-tail'" in step["if"]
    run = step["run"]
    assert "pytest-rerunfailures==16.7" in run
    assert f"{WHEEL_SHA}  $dir/$wheel" in run and "sha256sum -c -" in run
    assert "pip download --no-deps --only-binary=:all:" in run
    assert 'pip install --no-deps "$dir/$wheel"' in run
    assert "set -euo pipefail" in run
    # Installed before the tail's first test step, after the shared setup.
    names = [s.get("name") for s in steps]
    first_tail_test = next(
        i
        for i, s in enumerate(steps)
        if "matrix.group == 'shared-tail'" in str(s.get("if"))
        and "python -m pytest" in str(s.get("run"))
    )
    assert names.index("Install dependencies") < names.index(PLUGIN_STEP) < first_tail_test


def test_a_retry_becomes_a_warning_and_nothing_else_does():
    rerun = SimpleNamespace(outcome="rerun", nodeid="tests/integration/x_pg.py::test_a")
    line = rerun_annotation(rerun)
    assert line.startswith("::warning title=Retried once (55-A)::")
    assert "tests/integration/x_pg.py::test_a" in line
    for outcome in ("passed", "failed", "skipped"):
        assert rerun_annotation(SimpleNamespace(outcome=outcome, nodeid="t")) is None


def test_the_live_path_watchdog_retries_exactly_like_ci():
    watch = yaml.safe_load(
        (REPO / ".github" / "workflows" / "live-path-watchdog.yml").read_text()
    )["jobs"]["database-integration"]
    worker = _worker()
    assert watch["env"]["PYTEST_ADDOPTS"] == worker["env"]["PYTEST_ADDOPTS"]
    mirror = next(s for s in watch["steps"] if s.get("name") == PLUGIN_STEP)
    original = next(s for s in worker["steps"] if s.get("name") == PLUGIN_STEP)
    assert mirror["run"] == original["run"] and mirror["if"] == original["if"]
