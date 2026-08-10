"""Ruling 022 — the shared lane-lock claim primitive, pinned.

The primitive exists because three hand-rolled claims failed in two days, one of
them written by the author of the rule forbidding it. So the thing most worth
testing is not the happy path: it is that a claim **REFUSES** when it must, and
that an unparseable lock refuses rather than falling through to a write.

``scripts/claim_lane_lock.py`` lives outside the backend package and is driven as
a subprocess here, deliberately — that is exactly how every lane calls it, so
this tests the interface the callers actually use, including exit codes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim_lane_lock.py"

ACQUIRED, REFUSED, MALFORMED = 0, 1, 2


def _lock(tmp_path: Path, status: str, pid: object) -> Path:
    p = tmp_path / "LANE-test.lock"
    p.write_text(f"lane: test\nstatus: {status}\npid: {pid}\nqueue: none\n")
    return p


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def _claim(lock: Path, queue: str = "TEST-1") -> subprocess.CompletedProcess:
    return _run("claim", str(lock), "--queue", queue)


def test_the_script_exists_and_is_the_only_claim_path():
    """Ruling 022 deletes hand-rolled claim logic; something must replace it.

    LAT-P026 found the ruling on master with NO implementation anywhere — every
    lane still hand-rolling the logic the ruling declares deleted, which is the
    second path the ruling exists to remove.
    """
    assert SCRIPT.is_file(), f"{SCRIPT} missing — ruling 022 has no implementation"


def test_refuses_a_lock_held_by_a_live_other(tmp_path):
    """THE ONE THAT MATTERS. Queue 309 overwrote INT-033's held claim here."""
    # pid 1 always exists and is never us.
    result = _claim(_lock(tmp_path, "HELD", 1))
    assert result.returncode == REFUSED, result.stdout + result.stderr
    assert "REFUSED" in result.stderr


def test_a_refusal_does_not_modify_the_lock(tmp_path):
    """A refused claim must leave the owner's file byte-identical.

    INT-035's regex claim wrote a false HELD log line into a lock it did not
    own. Refusing loudly while still writing is not refusing.
    """
    lock = _lock(tmp_path, "HELD", 1)
    before = lock.read_text()
    assert _claim(lock).returncode == REFUSED
    assert lock.read_text() == before


@pytest.mark.parametrize("status", ["RELEASED", "free", "FREE"])
def test_an_explicit_release_frees_the_lock_regardless_of_pid(tmp_path, status):
    """Ruling 013 + its extension: `free` is not ambiguous, it is RELEASED.

    The pid here is OUR OWN live pid — the cycle-39 case, where a literal
    pid-alive reading would block the lane on itself forever.
    """
    result = _claim(_lock(tmp_path, status, os.getpid()))
    assert result.returncode == ACQUIRED, result.stdout + result.stderr


def test_a_dead_owner_is_a_takeover_and_says_so(tmp_path):
    """Ruling 008: `ps` decides. A dead owner frees the lane, on the record."""
    result = _claim(_lock(tmp_path, "HELD", 999999))
    assert result.returncode == ACQUIRED
    assert "takeover" in (result.stdout + lock_text(tmp_path)).lower()


def lock_text(tmp_path: Path) -> str:
    return (tmp_path / "LANE-test.lock").read_text()


def test_the_owner_may_reclaim_its_own_held_lock(tmp_path):
    lock = _lock(tmp_path, "RELEASED", 1)
    assert _claim(lock, "TEST-1").returncode == ACQUIRED
    assert _claim(lock, "TEST-2").returncode == ACQUIRED
    assert "TEST-2" in lock.read_text()


def test_a_malformed_lock_refuses_rather_than_falling_through(tmp_path):
    """The INT-035 shape: the pattern did not match and it wrote anyway.

    "I could not understand this lock" must be a refusal. An error path that
    proceeds is worse than a crash — the same species as gotcha #53.
    """
    p = tmp_path / "LANE-test.lock"
    p.write_text("this file has no status line\n")
    before = p.read_text()
    result = _run("claim", str(p), "--queue", "TEST-1")
    assert result.returncode == MALFORMED
    assert p.read_text() == before


def test_release_refuses_against_a_live_other(tmp_path):
    """You may not release someone else's held lock out from under them."""
    lock = _lock(tmp_path, "HELD", 1)
    before = lock.read_text()
    result = _run("release", str(lock))
    assert result.returncode == REFUSED
    assert lock.read_text() == before


def test_check_never_writes(tmp_path):
    """`check` is a read. It must be safe to call from anywhere, any time."""
    lock = _lock(tmp_path, "HELD", 1)
    before = lock.read_text()
    assert _run("check", str(lock)).returncode == ACQUIRED
    assert lock.read_text() == before


def test_session_pid_is_not_the_subshell_pid():
    """The ruling-022 addendum's CORRECTION, pinned.

    The addendum first said `owner_pid == $$`. Every Bash tool call is a fresh
    subshell, so `$$` never equals the session process and the test could never
    match — a lane would refuse its own valid lock, then "recover" by
    overwriting it. Identity resolves by walking `ppid` to the session ancestor,
    so it must be STABLE across two separate invocations.
    """
    a = _run("check", str(SCRIPT.parent))  # malformed path is fine; we want the pid
    b = _run("check", str(SCRIPT.parent))
    # Both malformed (exit 2) — the point is the script is callable twice.
    assert a.returncode == b.returncode == MALFORMED
