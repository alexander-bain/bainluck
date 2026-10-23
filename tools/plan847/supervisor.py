#!/usr/bin/env python3
"""#847 plan-only supervisor. The one public entry is run_attempt(); there is no CLI.

    run_attempt(credential=<FRESH_SEPARATELY_AUTHORIZED_PRIVATE_IN_MEMORY_CREDENTIAL>,
                admission=<ROOT_REVIEWED_FRESH_ADMISSION_DICT>,
                owner=<THE_ADMITTED_MEASUREMENT_CONTROLLER_SESSION>)

No SQL, subject, cap, timeout, child or receipt argument exists. Importing this
module does nothing; running it as a script exits 2 and does nothing.

Shape (the conventions of the reviewed #683 native operator, re-bound to #847):
the OWNER (caller) forks one WORKER in its own process group; the worker runs
admission, reserves the single attempt, spawns the native CHILD, reads its output
and writes the receipt. The owner kills only that worker group if it has to. A
successful return is only ever made inside the one wall; an OS-level stall inside
the owner's own close/kill/waitpid cannot be interrupted from Python, so a NO_RESULT
return can come late (measured, and refused by contract.accept). See README.

Bounds, both shared by everything this tool owns, both reserved before work starts:
  * ONE monotonic wall of 15 s from the first line of run_attempt: admission,
    credential handoff, connect, both plans, cleanup, receipt and owner return.
    Cleanup is reserved inside it; nothing resets per plan; nothing late succeeds.
  * ONE cumulative 524288-byte ledger: child stdout + stderr, every receipt byte
    (temp files included, abandoned ones too) and the owner-return metadata.
    The child's share is reserved out of it before the child starts and passed to
    the child, which checks it before every write it makes (its records, its
    refusal, everything on its fd 2). So bytes the worker has not read yet were
    still inside the ledger, and once the child is gone the worker drains both
    pipes to EOF: received_bytes is every byte the child wrote, not what was read
    before a refusal. Two residuals the child cannot pre-charge (the interpreter's
    own startup diagnostics, and a library writing straight to fd 1, which libpq
    does not) are still drained and counted exactly; past the ledger they are
    reported as an overrun, never hidden. This bounds what this tool serializes.
    It is NOT a cap on libpq's internal or wire buffers: the driver holds each full
    result before the child sees it.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

B = Path(__file__).resolve().parent


def _load_contract():
    if 'plan847_contract' in sys.modules:
        return sys.modules['plan847_contract']
    spec = importlib.util.spec_from_file_location('plan847_contract', B / 'contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules['plan847_contract'] = module
    return module


contract = _load_contract()

TOTAL = float(contract.LIMITS['total_seconds'])
CAP = contract.LIMITS['combined_output_bytes']
CLEANUP_RESERVE = 1.5
OWNER_MARGIN = 0.05
OWNER_RESERVE = 2048
REFUSAL_RESERVE = 8192
# Ledger room for what the interpreter may write to stderr before child.py's first
# statement takes fd 2 over; the child's own budget never includes it.
PRESTART_RESERVE = 4096
INPUT_CAP = 16384
RECEIPT_DIR = Path.home() / '.bainluck' / 'plan847-attempts'
# No ambient credentials or libpq defaults reach the child. The pgpass/service paths
# must not exist: libpq ignores a missing file silently, but warns on stderr about a
# non-regular one such as /dev/null, and any stderr byte refuses the attempt.
CHILD_ENV = {'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
             'PGPASSFILE': '/var/empty/plan847-no-pgpass', 'PGSERVICEFILE': '/var/empty/plan847-no-service'}
SUMMARY_KEYS = ('verdict', 'reason', 'admission_id', 'receipt_path', 'candidate_sha256',
                'received_bytes', 'combined_output_bytes', 'exit_code', 'attempt_consumed')

_now = time.monotonic
_wall = time.time


def _child_argv():
    # -E ignores PYTHON* variables and -P never puts the script's directory on sys.path,
    # so nothing planted beside child.py can stand in for the driver. Not -I: that also
    # drops user site-packages, where the operator's installed psycopg2 may live.
    return [sys.executable, '-E', '-P', str(B / 'child.py')]


class OutputExceeded(Exception):
    pass


class Ledger:
    """The single cumulative output ledger. A charge that would pass the cap is refused."""

    def __init__(self):
        self.bytes = 0

    def available(self, reserve):
        return CAP - reserve - self.bytes

    def charge(self, n, reserve):
        if n > self.available(reserve):
            raise OutputExceeded()
        self.bytes += n


def _drain(pipe, deadline):
    """Read a dead child's pipe to EOF. Returns (bytes read, reached EOF)."""
    n = 0
    while _now() < deadline:
        try:
            chunk = os.read(pipe.fileno(), 65536)
        except BlockingIOError:
            # The child is reaped, so another process still holds the write end.
            return n, False
        if not chunk:
            return n, True
        n += len(chunk)
    return n, False


def _remaining(deadline):
    remaining = deadline - _now()
    if remaining <= 0:
        raise TimeoutError('WALL_EXPIRED')
    return remaining


def _chunks(value):
    # Bounded encoding; never builds one string of the whole receipt.
    if isinstance(value, dict):
        yield b'{'
        for i, (key, item) in enumerate(value.items()):
            if i:
                yield b','
            yield from _chunks(key)
            yield b':'
            yield from _chunks(item)
        yield b'}'
    elif isinstance(value, (list, tuple)):
        yield b'['
        for i, item in enumerate(value):
            if i:
                yield b','
            yield from _chunks(item)
        yield b']'
    elif isinstance(value, str):
        yield b'"'
        for i in range(0, len(value), 512):
            yield json.dumps(value[i:i + 512], ensure_ascii=True)[1:-1].encode('ascii')
        yield b'"'
    else:
        yield json.dumps(value, allow_nan=False, separators=(',', ':')).encode('ascii')


def _serialize(value, path, *, first, deadline, ledger, reserve):
    """Write a receipt. Every byte is charged BEFORE it reaches the sink."""
    _remaining(deadline)
    fd, name = tempfile.mkstemp(prefix='.plan847-', dir=path.parent)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, 'wb') as f:
            for raw in _chunks(value):
                _remaining(deadline)
                ledger.charge(len(raw), reserve)
                digest.update(raw)
                f.write(raw)
            ledger.charge(1, reserve)
            digest.update(b'\n')
            f.write(b'\n')
            _remaining(deadline)
            f.flush()
            _remaining(deadline)
            os.fsync(f.fileno())
            _remaining(deadline)
        if first:
            os.link(name, path)
            os.unlink(name)
            name = None
            _remaining(deadline)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            _remaining(deadline)
        else:
            os.replace(name, path)
            name = None
        return digest.hexdigest()
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except OSError:
                pass


def run_attempt(*, credential, admission, owner):
    """The only entry. One attempt under one 15 s wall; success is only returned within it.

    A returned verdict of PLAN_ONLY_PENDING_ROOT_REVIEW is still not a result by
    itself: read the receipt bytes and pass both to contract.accept(). A disk
    receipt without this timely return is never evidence.

    Every owned resource (worker group, pipe, selector) is released BEFORE success
    is eligible and before the elapsed stamp is taken, so owner finalization is
    inside the measured wall. Any exception, failed or late cleanup is NO_RESULT;
    the first failure is the reason and a later one never replaces it.
    """
    started = _now()
    deadline = started + TOTAL
    stop = deadline - OWNER_MARGIN
    rd = wr = None
    refused = 'PIPE_REFUSED'
    try:
        rd, wr = os.pipe()
        refused = 'FORK_REFUSED'
        pid = os.fork()
    except BaseException:
        for fd in (rd, wr):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        return dict(verdict='NO_RESULT', reason=refused, owner_completed=True, admission_id=None,
                    receipt_path=None, candidate_sha256=None, received_bytes=None,
                    combined_output_bytes=None, exit_code=None, attempt_consumed=False,
                    no_retry=True, elapsed_seconds=_now() - started)
    if pid == 0:
        code = 125
        try:
            os.setpgid(0, 0)
            os.close(rd)
            summary, ledger = _worker(credential=credential, admission=admission, owner=owner, deadline=stop)
            raw = (json.dumps(summary, separators=(',', ':'), allow_nan=False) + '\n').encode()
            if len(raw) <= OWNER_RESERVE:
                ledger.charge(len(raw), 0)
                _remaining(stop)
                os.write(wr, raw)
                code = 0
        except BaseException:
            code = 125
        finally:
            os._exit(code)
    # From here the worker exists: every path below runs the owned cleanup.
    failure = None
    candidate = None
    status = None
    selector = None
    phase = 'OWNER_SETUP_FAILED'
    try:
        os.close(wr)
        wr = None
        try:
            os.setpgid(pid, pid)
        except OSError:
            pass
        os.set_blocking(rd, False)
        selector = selectors.DefaultSelector()
        selector.register(rd, selectors.EVENT_READ)
        phase = 'OWNER_READ_FAILED'
        data = bytearray()
        while _now() < stop:
            got, code = os.waitpid(pid, os.WNOHANG)
            if got:
                status = code
            for _key, _mask in selector.select(min(.005, max(0, stop - _now()))):
                chunk = os.read(rd, OWNER_RESERVE + 1 - len(data))
                if chunk:
                    data.extend(chunk)
                else:
                    selector.unregister(rd)
            if len(data) > OWNER_RESERVE or status is not None:
                break
        if status is not None and _now() < stop:
            # Drain what the worker wrote before it exited.
            try:
                while len(data) <= OWNER_RESERVE:
                    chunk = os.read(rd, OWNER_RESERVE + 1 - len(data))
                    if not chunk:
                        break
                    data.extend(chunk)
            except BlockingIOError:
                pass
            candidate = _owner_result(status, bytes(data))
        if candidate is None:
            failure = 'WALL_EXPIRED_OR_UNAVAILABLE'
    except BaseException:
        failure = phase
        candidate = None
    reaped = status is not None
    if candidate is None:
        reaped = _reclaim(pid, reaped, deadline)
    if not _release(selector, rd, wr) and failure is None:
        failure = 'OWNER_CLEANUP_FAILED'
    # The stamp is taken only now, after the last owned release.
    elapsed = _now() - started
    if failure is None and elapsed > TOTAL:
        failure = 'OWNER_FINALIZATION_LATE'
    if failure is None:
        candidate['owner_completed'] = True
        candidate['elapsed_seconds'] = elapsed
        candidate['no_retry'] = True
        return candidate
    return dict(verdict='NO_RESULT', reason=failure, owner_completed=False,
                admission_id=None, receipt_path=None, candidate_sha256=None, received_bytes=None,
                combined_output_bytes=None, exit_code=None, attempt_consumed=None,
                worker_reaped=reaped, no_retry=True, elapsed_seconds=elapsed)


def _reclaim(pid, reaped, deadline):
    """Kill only the newly owned worker group (worker + its native child); reap within the wall."""
    try:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        while not reaped and _now() < deadline - .002:
            got, _code = os.waitpid(pid, os.WNOHANG)
            if got:
                return True
            time.sleep(.002)
    except BaseException:
        pass
    return reaped


def _release(selector, *fds):
    """Close every owned descriptor; True only if all of them closed cleanly."""
    clean = True
    if selector is not None:
        try:
            selector.close()
        except BaseException:
            clean = False
    for fd in fds:
        if fd is not None:
            try:
                os.close(fd)
            except BaseException:
                clean = False
    return clean


def _owner_result(status, raw):
    if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0) or not raw.endswith(b'\n'):
        return None
    try:
        summary = contract.loads(raw)
    except contract.Refused:
        return None
    if type(summary) is not dict or tuple(summary) != SUMMARY_KEYS:
        return None
    return summary


def _worker(*, credential, admission, owner, deadline):
    """Runs in the forked worker. Every failure is NO_RESULT with a fixed reason code."""
    ledger = Ledger()
    summary = dict(verdict='NO_RESULT', reason='INCOMPLETE', admission_id=None, receipt_path=None,
                   candidate_sha256=None, received_bytes=0, combined_output_bytes=None,
                   exit_code=None, attempt_consumed=False)
    # Admission is pure and consumes nothing: a refused admission leaves no marker,
    # no receipt and never reaches a child or a driver.
    try:
        _remaining(deadline)
        contract.packet()
        _remaining(deadline)
        admitted, admission_digest = contract.admit(admission, owner, _wall(), TOTAL)
        _remaining(deadline)
    except contract.Refused as exc:
        summary['reason'] = exc.args[0] if exc.args and exc.args[0] in contract.CODES else 'REFUSED'
        return summary, ledger
    except BaseException:
        summary['reason'] = 'REFUSED'
        return summary, ledger
    aid = admitted['admission_id']
    summary['admission_id'] = aid
    path = RECEIPT_DIR / f'{aid}.json'
    # One attempt per admission: the marker exists before anything can spawn.
    try:
        RECEIPT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.close(os.open(str(RECEIPT_DIR / f'{aid}.used'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        summary['reason'] = 'SINGLE_USE_REFUSED'
        return summary, ledger
    except BaseException:
        summary['reason'] = 'REFUSED'
        return summary, ledger
    summary['attempt_consumed'] = True
    summary['receipt_path'] = str(path)
    receipt = dict(
        schema='plan847-attempt-receipt/v1', subject=contract.SUBJECT, mode=contract.MODE,
        admission_id=aid, admission_sha256=admission_digest, binding_sha256=admitted['binding_sha256'],
        seal_sha256=contract.SEAL_SHA256, manifest_sha256=contract.MANIFEST_SHA256,
        source_ref=contract.SOURCE_REF, sql_sha256=admitted['sql_sha256'], limits=contract.LIMITS,
        root_review_id=admitted['root_review_id'], admission_owner=admitted['admission_owner'],
        controller_session=admitted['controller_session'], window=admitted['window'],
        prerequisites_declared_not_verified=admitted['prerequisites'],
        started_utc=datetime.datetime.fromtimestamp(_wall(), datetime.timezone.utc).isoformat(),
        verdict='NO_RESULT', reason='INCOMPLETE', no_retry=True, received_bytes=0, exit_code=None)
    reason = None
    proc = None
    output = bytearray()
    total = stderr_bytes = overrun = 0
    selector = selectors.DefaultSelector()
    try:
        _serialize(receipt, path, first=True, deadline=deadline, ledger=ledger,
                   reserve=OWNER_RESERVE + REFUSAL_RESERVE)
        if type(credential) is not str or not credential or '\0' in credential or len(credential.encode()) > 12000:
            raise ValueError('INPUT_REFUSED')
        # The child's whole share of the ledger, fixed before it starts.
        budget = ledger.available(OWNER_RESERVE + REFUSAL_RESERVE + PRESTART_RESERVE)
        if budget <= 0:
            raise OutputExceeded()
        payload = (json.dumps(dict(credential=credential, admission=admission, owner=owner,
                                   output_budget=budget),
                              separators=(',', ':'), allow_nan=False) + '\n').encode()
        if len(payload) > INPUT_CAP:
            raise ValueError('INPUT_REFUSED')
        if _now() >= deadline - CLEANUP_RESERVE:
            raise TimeoutError()
        proc = subprocess.Popen(_child_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=CHILD_ENV, close_fds=True, cwd='/')
        for pipe in (proc.stdout, proc.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdin, selectors.EVENT_WRITE)
        pending = memoryview(payload)
        while selector.get_map() or proc.poll() is None:
            remaining = deadline - CLEANUP_RESERVE - _now()
            if remaining <= 0:
                reason = 'WALL_EXPIRED'
                break
            for key, _mask in selector.select(min(remaining, .05)):
                pipe = key.fileobj
                if pipe is proc.stdin:
                    try:
                        if pending:
                            n = os.write(pipe.fileno(), pending[:4096])
                            pending = pending[n:]
                    except BrokenPipeError:
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(pipe)
                        pipe.close()
                    continue
                allowance = ledger.available(OWNER_RESERVE + REFUSAL_RESERVE)
                if allowance <= 0:
                    reason = 'OUTPUT_EXCEEDED'
                    break
                chunk = os.read(pipe.fileno(), min(8192, allowance))
                if not chunk:
                    selector.unregister(pipe)
                    pipe.close()
                    continue
                ledger.charge(len(chunk), OWNER_RESERVE + REFUSAL_RESERVE)
                total += len(chunk)
                if pipe is proc.stderr:
                    stderr_bytes += len(chunk)  # counted, never retained
                else:
                    output.extend(chunk)
            if reason:
                break
        if not reason and _now() > deadline - CLEANUP_RESERVE:
            # The child phase overran its share; the cleanup reserve is not spare time.
            reason = 'WALL_EXPIRED'
        if not reason:
            if proc.returncode != 0:
                reason = 'NONZERO_EXIT'
            elif stderr_bytes:
                reason = 'STDERR_REFUSED'
            else:
                receipt['candidate_evidence'] = contract.evidence(bytes(output))
    except TimeoutError:
        reason = 'WALL_EXPIRED'
    except OutputExceeded:
        reason = 'OUTPUT_EXCEEDED'
    except contract.Refused as exc:
        reason = exc.args[0] if exc.args and exc.args[0] in contract.CODES else 'REFUSED'
    except BaseException:
        reason = 'REFUSED'  # fixed text only; no DSN, driver exception or raw stderr
    finally:
        if proc is not None:
            if proc.poll() is None:
                if not reason:
                    reason = 'CLEANUP_UNCERTAIN'
                proc.terminate()  # owned PID only; its handler closes its own connection
                try:
                    proc.wait(timeout=min(.1, max(0.001, deadline - _now())))
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=min(1, max(0.001, deadline - _now())))
                    except subprocess.TimeoutExpired:
                        # No fresh allowance: the owner kills this whole group.
                        raise TimeoutError('WALL_EXPIRED')
            # The child is gone: what it left in its pipes is output it wrote. Count
            # every byte (never retain it); no reported number stops at the last read.
            for pipe in (proc.stdout, proc.stderr):
                if pipe.closed:
                    continue
                n, eof = _drain(pipe, deadline)
                total += n
                if pipe is proc.stderr:
                    stderr_bytes += n
                try:
                    ledger.charge(n, OWNER_RESERVE + REFUSAL_RESERVE)
                except OutputExceeded:
                    overrun += n
                    reason = reason or 'OUTPUT_EXCEEDED'
                if not eof:
                    reason = reason or 'CLEANUP_UNCERTAIN'
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if not pipe.closed:
                    pipe.close()
            receipt['exit_code'] = proc.returncode
        selector.close()
    if _now() >= deadline:
        reason = 'WALL_EXPIRED'
    receipt['received_bytes'] = total
    summary.update(received_bytes=total, exit_code=receipt['exit_code'])
    if reason:
        receipt.pop('candidate_evidence', None)
        receipt.update(verdict='NO_RESULT', reason=reason)
    else:
        # Disk alone always reads NO_RESULT; only the owner's timely return binds it.
        receipt.update(verdict='NO_RESULT', reason='OWNER_CONFIRMATION_REQUIRED')
    try:
        candidate_hash = _serialize(receipt, path, first=False, deadline=deadline, ledger=ledger,
                                    reserve=OWNER_RESERVE + REFUSAL_RESERVE)
    except BaseException as exc:
        reason = 'WALL_EXPIRED' if isinstance(exc, TimeoutError) or _now() >= deadline else 'OUTPUT_EXCEEDED'
        receipt.pop('candidate_evidence', None)
        receipt.update(verdict='NO_RESULT', reason=reason)
        _remaining(deadline)
        candidate_hash = _serialize(receipt, path, first=False, deadline=deadline, ledger=ledger,
                                    reserve=OWNER_RESERVE)
    _remaining(deadline)
    summary.update(verdict='NO_RESULT' if reason else 'PLAN_ONLY_PENDING_ROOT_REVIEW',
                   reason=reason, candidate_sha256=None if reason else candidate_hash,
                   combined_output_bytes=ledger.bytes + OWNER_RESERVE + overrun)
    return summary, ledger


if __name__ == '__main__':
    # No console entry and no CLI admission.
    sys.exit(2)
