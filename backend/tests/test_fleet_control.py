"""Operator controls must preserve work and prevent duplicate expensive sessions."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "scripts/lane_control.py"


def invoke(env, *args):
    return subprocess.run(
        [sys.executable, str(CONTROL), *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )


@pytest.fixture
def env(tmp_path):
    return {**os.environ, "LANE_CONTROL_ROOT": str(tmp_path / "control")}


def test_pause_persists_and_resume_preserves_other_pauses(env, tmp_path):
    marker = tmp_path / "executed"
    invoke(env, "pause", "all")
    invoke(env, "pause", "native")
    result = invoke(
        env,
        "run",
        "live",
        "--",
        sys.executable,
        "-c",
        f'open({str(marker)!r}, "w").close()',
    )
    assert result.returncode == 75 and not marker.exists()
    invoke(env, "resume", "all")
    assert invoke(env, "check", "live").returncode == 0
    assert invoke(env, "check", "native").returncode == 1


def test_capacity_and_subject_exclusion_release_after_exit(env, tmp_path):
    invoke(env, "mode", "quiet")
    ready = tmp_path / "ready"
    finish = tmp_path / "finish"
    code = f"import pathlib,time;pathlib.Path({str(ready)!r}).touch()\nwhile not pathlib.Path({str(finish)!r}).exists(): time.sleep(.02)"
    child = subprocess.Popen(
        [
            sys.executable,
            str(CONTROL),
            "run",
            "review-A",
            "--",
            sys.executable,
            "-c",
            code,
        ],
        env=env,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        assert invoke(env, "run", "review-A", "--", "true").returncode == 75
        assert invoke(env, "run", "live", "--", "true").returncode == 75
        invoke(env, "pause", "review")
        assert child.poll() is None  # pause never terminates active work
        finish.touch()
        assert child.wait(timeout=10) == 0
        assert invoke(env, "run", "live", "--", "true").returncode == 0
    finally:
        finish.touch()
        child.wait(timeout=10)


def test_context_is_explicit_and_not_incidental_prose(env, tmp_path):
    p = tmp_path / "note.md"
    p.write_text("A report mentions FYI but asks for a repair.\n")
    assert invoke(env, "context", str(p)).returncode == 1
    p.write_text("dispatch: context\nFYI, preserved for next assignment\n")
    assert invoke(env, "context", str(p)).returncode == 0


def test_integrator_unchanged_input_sleeps_but_new_offer_wakes(env, tmp_path):
    inbox = tmp_path / "runner-inbox/integrator"
    inbox.mkdir(parents=True)
    assert invoke(env, "integrator-ready", str(tmp_path)).returncode == 0
    assert invoke(env, "integrator-ready", str(tmp_path)).returncode == 1
    (inbox / "SELF-repeat.md").write_text("nothing new")
    assert invoke(env, "integrator-ready", str(tmp_path)).returncode == 1
    (inbox / "offer.md").write_text("exact new source")
    assert invoke(env, "integrator-ready", str(tmp_path)).returncode == 0


def test_collector_access_failure_and_unchanged_input_need_no_model(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "monitor", ROOT / "scripts/lane_monitor.py"
    )
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def fail(url):
        raise OSError("network unavailable")

    assert monitor.collect(tmp_path, fail, lambda: {"version": 1}) == 69

    def expire():
        p = tmp_path / "state.json"
        d = json.loads(p.read_text())
        d["checked_at"] = 0
        p.write_text(json.dumps(d))

    expire()
    assert (
        monitor.collect(
            tmp_path,
            lambda url: {"commit": "abc", "items": [{"id": 1}]},
            lambda: {"version": 1},
        )
        == 0
    )
    monitor.acknowledge(tmp_path)
    expire()
    assert (
        monitor.collect(
            tmp_path,
            lambda url: {"commit": "abc", "items": [{"id": 1}]},
            lambda: {"version": 1},
        )
        == 75
    )
    expire()
    assert (
        monitor.collect(
            tmp_path,
            lambda url: {"commit": "def", "items": [{"id": 1}]},
            lambda: {"version": 1},
        )
        == 0
    )


def test_concurrent_start_requests_open_only_one_window(env, tmp_path):
    binpath = tmp_path / "bin"
    binpath.mkdir()
    calls = tmp_path / "calls"
    stub = binpath / "osascript"
    stub.write_text(f'#!/bin/sh\ncat >/dev/null\necho window >> "{calls}"\nsleep .2\n')
    stub.chmod(0o755)
    env["PATH"] = str(binpath) + ":" + env["PATH"]
    args = [sys.executable, str(CONTROL), "launch", "live", "/nonexistent/fleet-worker"]
    procs = [
        subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL) for _ in range(2)
    ]
    assert [p.wait(timeout=10) for p in procs] == [0, 0]
    assert calls.read_text().splitlines() == ["window"]
    assert invoke(env, "launch", "live", "/nonexistent/fleet-worker").returncode == 0
    assert calls.read_text().splitlines() == ["window"]


def test_review_pause_covers_all_subjects(env):
    invoke(env, "pause", "review")
    assert invoke(env, "run", "review-CERT-123", "--", "true").returncode == 75


def test_child_runs_at_lower_cpu_priority(env):
    result = invoke(
        env,
        "run",
        "live",
        "--",
        sys.executable,
        "-c",
        "import os; print(os.getpriority(os.PRIO_PROCESS, 0))",
    )
    assert result.returncode == 0
    assert int(result.stdout.strip()) >= 10


def test_lower_limit_counts_sessions_in_higher_slots(env):
    import fcntl

    locks = Path(env["LANE_CONTROL_ROOT"]) / "locks"
    locks.mkdir(parents=True)
    with (locks / "slot-5.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        invoke(env, "mode", "quiet")
        assert invoke(env, "run", "live", "--", "true").returncode == 75
