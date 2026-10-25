"""Actual existing lock helper and filesystem latches, no production access."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.services.dnpl_operation_hold import (
    DeskHold,
    OperationHoldRefused,
    consume_once,
    HELPER,
)


@pytest.fixture
def hold(tmp_path):
    started = subprocess.check_output(
        ["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True
    ).strip()
    lock = tmp_path / "lane.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: integrator-local-test\nowner_pid: {os.getpid()}\nowner_started: {started}\nclaimed_epoch_s: 1\n"
    )
    return DeskHold(lock, "integrator-local-test", os.getpid(), started, 1)


def test_real_helper_confirms_owner_and_continuous_flock_excludes_transition(hold):
    with hold.held():
        hold.check()
        script = """import importlib.util, sys
spec=importlib.util.spec_from_file_location('helper',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with m._exclusive(sys.argv[2],timeout=0.01):
    raise AssertionError('must not enter while wrapper owns hold')
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(HELPER), str(hold.path)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        assert result.returncode == 3
        assert "NOT SERIALIZED" in result.stderr
    assert Path(str(hold.path) + ".claimlock").is_file()
    with hold.held():
        hold.check()


def test_helper_exit_zero_for_other_owner_is_not_accepted(hold):
    other = DeskHold(
        hold.path, "different-caller", hold.owner_pid, hold.owner_started, 1
    )
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "check",
            str(hold.path),
            "--identity",
            "different-caller",
        ],
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 0
    assert "HELD by a LIVE other" in result.stdout
    with pytest.raises(OperationHoldRefused, match="exact live owner"):
        with other.held():
            pytest.fail("must not enter")


def test_replaced_serialization_inode_refuses(hold):
    with pytest.raises(OperationHoldRefused, match="inode changed"):
        with hold.held():
            sidecar = Path(str(hold.path) + ".claimlock")
            # Only this disposable test file is replaced; never a real lane lock.
            sidecar.unlink()
            sidecar.touch()


def test_owner_start_mismatch_refuses_even_with_live_pid(hold):
    other = DeskHold(
        hold.path, hold.identity, hold.owner_pid, "different process start", 1
    )
    with pytest.raises(OperationHoldRefused, match="process identity"):
        with other.held():
            pytest.fail("must not enter")


def test_current_lock_shape_without_start_field_uses_captured_process_start(hold):
    hold.path.write_text(
        "\n".join(
            line
            for line in hold.path.read_text().splitlines()
            if not line.startswith("owner_started:")
        )
        + "\n"
    )
    with hold.held():
        hold.check()


def test_same_owner_reclaim_does_not_restore_interval(hold):
    with pytest.raises(OperationHoldRefused, match="claim interval changed"):
        with hold.held():
            hold.path.write_text(
                hold.path.read_text().replace(
                    "claimed_epoch_s: 1", "claimed_epoch_s: 2"
                )
            )


def test_capture_uses_live_helper_and_never_accepts_a_supplied_record(hold, tmp_path):
    run = tmp_path / "operation"
    run.mkdir(mode=0o700)
    with DeskHold.capture(hold.path, hold.identity, run) as captured:
        captured.check()
        assert captured.owner_pid == os.getpid()
        assert (run / "lock-identity").is_file()
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        with DeskHold.capture(hold.path, hold.identity, run):
            pytest.fail("must not resume from a caller-supplied receipt")


def test_unacquired_hold_and_symlink_refuse(hold, tmp_path):
    with pytest.raises(OperationHoldRefused, match="not acquired"):
        hold.check()
    target = tmp_path / "target"
    target.touch()
    Path(str(hold.path) + ".claimlock").symlink_to(target)
    with pytest.raises(OSError):
        with hold.held():
            pytest.fail("must not enter")


def test_consumption_has_one_winner_and_recreation_cannot_overwrite(tmp_path):
    tmp_path.chmod(0o700)
    command = {"run": "local", "step": "arm", "authority": "exact", "primary": "exact"}

    def consume():
        try:
            return consume_once(tmp_path, command)
        except OperationHoldRefused:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: consume(), range(8)))
    assert sum(result is not None for result in results) == 1
    original = next(result for result in results if result is not None).read_bytes()
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        consume_once(tmp_path, dict(reversed(list(command.items()))))
    assert (
        next(result for result in results if result is not None).read_bytes()
        == original
    )


def test_failed_fsync_burns_send_instead_of_authorizing_retry(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    with monkeypatch.context() as patch:
        patch.setattr(
            os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("injected"))
        )
        with pytest.raises(OSError, match="injected"):
            consume_once(tmp_path, {"step": "initialize"})
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        consume_once(tmp_path, {"step": "initialize"})


def test_shared_or_symlink_run_directory_refuses(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(OperationHoldRefused, match="private owned"):
        consume_once(tmp_path, {"step": "arm"})
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        consume_once(link, {"step": "arm"})
