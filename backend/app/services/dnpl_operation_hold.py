"""Local recovery-wrapper primitives, not an all-writer stop certificate.

Hold the existing lane helper's serialization inode continuously and verify its
actual owner output. This excludes cooperative helper claim/release operations;
it cannot exclude direct Heroku calls, external writers or arbitrary same-UID
file changes. No production command currently constructs this hold.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

HELPER = Path(__file__).resolve().parents[3] / "scripts/claim_lane_lock.py"
HELPER_SHA256 = "7a93a40fec479a6e18c64c667d8fffdcfb2b6c764db161c2b2b34bf8a0192e92"
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class OperationHoldRefused(RuntimeError):
    pass


def _owned_regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise OperationHoldRefused("regular file owned by this uid required")
    return info.st_dev, info.st_ino


class DeskHold:
    """Continuous cooperative hold; no writer-state or provider claim."""

    def __init__(
        self,
        lock_path: Path,
        identity: str,
        owner_pid: int,
        owner_started: str,
        claimed_epoch_s: int,
    ):
        if (
            not _IDENTITY.fullmatch(identity)
            or type(owner_pid) is not int
            or owner_pid <= 0
        ):
            raise ValueError("explicit owner identity and pid required")
        if not owner_started or "\n" in owner_started:
            raise ValueError("exact owner process start required")
        if type(claimed_epoch_s) is not int or claimed_epoch_s <= 0:
            raise ValueError("exact original claim epoch required")
        if not lock_path.is_absolute():
            raise ValueError("absolute lock path required")
        self.path = lock_path
        self.identity = identity
        self.owner_pid = owner_pid
        self.owner_started = owner_started
        self.claimed_epoch_s = claimed_epoch_s
        self._fd = None
        self._inode = None

    @classmethod
    @contextmanager
    def capture(cls, lock_path: Path, identity: str, run_dir: Path):
        """Capture from the actual helper/lock now; never load a supplied receipt."""
        fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            _owned_regular(fd)
            with os.fdopen(os.dup(fd)) as source:
                content = source.read(65537)
            if len(content) > 65536:
                raise OperationHoldRefused("lock file too large")
        finally:
            os.close(fd)
        pids = re.findall(r"(?m)^owner_pid:\s*(\d+)\s*$", content)
        epochs = re.findall(r"(?m)^claimed_epoch_s:\s*(\d+)\s*$", content)
        if len(pids) != 1 or len(epochs) != 1:
            raise OperationHoldRefused("lock owner pid and claim epoch required")
        started = subprocess.run(
            ["ps", "-p", pids[0], "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if started.returncode != 0 or not started.stdout.strip():
            raise OperationHoldRefused("owner process not running")
        hold = cls(
            lock_path, identity, int(pids[0]), started.stdout.strip(), int(epochs[0])
        )
        with hold.held():
            record = {
                "identity": identity,
                "owner_pid": hold.owner_pid,
                "owner_started": hold.owner_started,
                "claimed_epoch_s": hold.claimed_epoch_s,
                "lock_path": str(lock_path),
            }
            _write_once(
                run_dir, "lock-identity", json.dumps(record, sort_keys=True).encode()
            )
            yield hold

    def check(self):
        if self._fd is None:
            raise OperationHoldRefused("continuous hold not acquired")
        sidecar = Path(str(self.path) + ".claimlock")
        current = sidecar.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != self._inode
        ):
            raise OperationHoldRefused("serialization inode changed")
        if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA256:
            raise OperationHoldRefused("lock helper source changed")
        # The helper delegates to the script owning the lock's repository.
        # Verify those actual bytes too, rather than pinning only the launcher.
        parent = self.path.parent.resolve()
        while True:
            delegated = parent / "scripts/claim_lane_lock.py"
            if delegated.is_file():
                if hashlib.sha256(delegated.read_bytes()).hexdigest() != HELPER_SHA256:
                    raise OperationHoldRefused("owning repository helper changed")
                break
            if parent == parent.parent:
                break
            parent = parent.parent
        # Prevent the helper's own optional test override changing its contract.
        env = dict(os.environ)
        env.pop("BAINLUCK_LANE_LOCK_NO_DELEGATE", None)
        env.pop("BAINLUCK_LANE_LOCK_DELEGATED", None)
        result = subprocess.run(
            [
                sys.executable,
                str(HELPER),
                "check",
                str(self.path),
                "--identity",
                self.identity,
            ],
            capture_output=True,
            text=True,
            timeout=2,
            env=env,
        )
        prefix = f"status=HELD owner_identity={self.identity} owner_pid={self.owner_pid} alive=True "
        suffix = f" me={self.identity} -> HELD BY ME"
        output = result.stdout.strip()
        if (
            result.returncode != 0
            or len(output.splitlines()) != 1
            or not output.startswith(prefix)
            or not output.endswith(suffix)
        ):
            raise OperationHoldRefused("lock helper does not confirm exact live owner")
        started = subprocess.run(
            ["ps", "-p", str(self.owner_pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if started.returncode != 0 or started.stdout.strip() != self.owner_started:
            raise OperationHoldRefused("owner process identity changed")
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            _owned_regular(fd)
            with os.fdopen(os.dup(fd)) as source:
                content = source.read(65537)
            if len(content) > 65536:
                raise OperationHoldRefused("lock file too large")
            matches = re.findall(r"(?m)^owner_started:\s*(.+)$", content)
            if matches and (
                len(matches) != 1
                or not (
                    matches[0] == self.owner_started
                    or matches[0].startswith(self.owner_started + "  (")
                )
            ):
                raise OperationHoldRefused("lock does not bind owner start")
            epochs = re.findall(r"(?m)^claimed_epoch_s:\s*(\d+)\s*$", content)
            if epochs != [str(self.claimed_epoch_s)]:
                raise OperationHoldRefused("lock claim interval changed")
        finally:
            os.close(fd)

    @contextmanager
    def held(self):
        if self._fd is not None:
            raise OperationHoldRefused("hold already entered")
        fd = os.open(
            str(self.path) + ".claimlock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644
        )
        try:
            inode = _owned_regular(fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise OperationHoldRefused(
                    "another helper transition owns serialization"
                ) from exc
            self._fd, self._inode = fd, inode
            self.check()
            yield self
            self.check()
        finally:
            self._fd = self._inode = None
            os.close(fd)
        # Never unlink the serialization inode: the existing helper relies on it.


def consume_once(run_dir: Path, command_identity: dict) -> Path:
    """Persist a no-overwrite send latch; its contents confer NO authorization.

    The caller owns its operation hold and has already invoked the verifier.
    Failure after creating this file burns the send, including fsync errors.
    A readback path uses a different command kind and never deletes this latch.
    """
    encoded = json.dumps(
        command_identity, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if len(encoded) > 4096:
        raise ValueError("command identity too large")
    name = hashlib.sha256(encoded).hexdigest() + ".send-consumed"
    return _write_once(run_dir, name, encoded)


def _write_once(run_dir: Path, name: str, encoded: bytes) -> Path:
    directory = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise OperationHoldRefused("private owned run directory required")
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
        except FileExistsError as exc:
            raise OperationHoldRefused("record already consumed; use readback") from exc
        try:
            with os.fdopen(fd, "wb", closefd=False) as receipt:
                receipt.write(encoded)
                receipt.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        return run_dir / name
    finally:
        os.close(directory)
