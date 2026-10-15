"""Record a bounded, read-only snapshot after a Watch gate step has failed.

This is failure evidence only. It never runs a test, never reports acceptance
and never changes the original failure: the caller keeps the original exit
status and decides what to do with this helper's own exit code.

It reads at most:
  * `xcrun simctl list devices --json` and `xcrun simctl list pairs --json`,
    each once (no retry), each bounded to 2 s and both together to 4 s, and
    only when two distinct, canonical device UUIDs were supplied;
  * the last 16 KiB of up to three exact regular files: the host CoreSimulator
    service log and each supplied device's own `system.log`.

No simulator is created, booted, paired, installed, launched, erased or killed,
no directory is globbed and no log stream is started. Anything it cannot read
is recorded as unavailable. Outputs are `failure-evidence.json` and
`failure-evidence-*.log`, which the existing preparation upload already keeps.
"""

import argparse
import codecs
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

SCHEMA = "watch-failure-evidence/1"
EVIDENCE_FILE = "failure-evidence.json"
TAIL_BYTES = 16 * 1024
MAX_TAILS = 3
RPC_TIMEOUT_SECONDS = 2.0
RPC_BUDGET_SECONDS = 4.0
MIN_RPC_SECONDS = 0.05
STDERR_BYTES = 2048
TEXT_LIMIT = 200
DEVICES_COMMAND = ("xcrun", "simctl", "list", "devices", "--json")
PAIRS_COMMAND = ("xcrun", "simctl", "list", "pairs", "--json")
READ_ONLY_COMMANDS = frozenset({DEVICES_COMMAND, PAIRS_COMMAND})
DEVICE_FIELDS = (
    "udid",
    "name",
    "state",
    "isAvailable",
    "availabilityError",
    "deviceTypeIdentifier",
    "lastBootedAt",
)
_UDID = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)


class WriteError(Exception):
    """The evidence file itself could not be written."""


def default_log_root():
    return Path.home() / "Library/Logs/CoreSimulator"


def spawn_bounded(argv, timeout):
    """Keep request and cleanup inside one bound, including interruption."""
    deadline = time.monotonic() + timeout
    cleanup_reserve = min(0.1, timeout / 2)
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(
            timeout=max(0, deadline - time.monotonic() - cleanup_reserve)
        )
    except BaseException:
        # The caller can be interrupted by its unchanged preparation deadline.
        # This private RPC session must not outlive that caller. Do not wait
        # for EOF from an escaped descendant holding a pipe open.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        for stream in (process.stdout, process.stderr):
            stream.close()
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
        raise
    return process.returncode, stdout, stderr


def _bounded_text(value, name):
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text[:TEXT_LIMIT]


def _udid(value):
    """Return (canonical upper-case UDID, problem)."""
    text = (value or "").strip()
    if not text:
        return None, "missing"
    if not _UDID.fullmatch(text):
        return None, "not_uuid"
    if set(text.replace("-", "")) == {"0"}:
        return None, "nil_uuid"
    return text.upper(), None


def _identity(watch_id, phone_id):
    watch, watch_problem = _udid(watch_id)
    phone, phone_problem = _udid(phone_id)
    problems = []
    if watch_problem:
        problems.append(f"watch_id_{watch_problem}")
    if phone_problem:
        problems.append(f"phone_id_{phone_problem}")
    if watch and phone and watch == phone:
        problems.append("ids_not_distinct")
    return {
        "watch_id": watch or (watch_id or "")[:TEXT_LIMIT],
        "phone_id": phone or (phone_id or "")[:TEXT_LIMIT],
        "complete": not problems,
        "problems": problems,
    }, ((watch, phone) if not problems else None)


def _stderr_tail(data):
    return (data or b"")[-STDERR_BYTES:].decode("utf-8", errors="replace")


def _call(argv, runner, clock, deadline):
    """One read-only call, never retried, inside the shared RPC budget."""
    argv = tuple(argv)
    if argv not in READ_ONLY_COMMANDS:
        raise ValueError(f"Refusing non-read-only command: {argv!r}")
    record = {"argv": list(argv), "attempts": 0}
    remaining = deadline - clock()
    if remaining < MIN_RPC_SECONDS:
        record["outcome"] = "budget_exhausted"
        return record, None
    timeout = min(RPC_TIMEOUT_SECONDS, remaining)
    record["timeout_seconds"] = round(timeout, 3)
    record["attempts"] = 1
    started = clock()
    try:
        returncode, stdout, stderr = runner(argv, timeout)
    except subprocess.TimeoutExpired:
        record["outcome"] = "timeout"
        return record, None
    except OSError as error:
        record["outcome"] = "unavailable"
        record["error"] = f"{type(error).__name__}: {error}"[:TEXT_LIMIT]
        return record, None
    finally:
        record["elapsed_seconds"] = round(max(0.0, clock() - started), 3)
    if returncode != 0:
        record["outcome"] = "nonzero_exit"
        record["returncode"] = returncode
        record["stderr_tail"] = _stderr_tail(stderr)
        return record, None
    try:
        parsed = json.loads(stdout)
    except (ValueError, TypeError) as error:
        record["outcome"] = "malformed_json"
        record["error"] = str(error)[:TEXT_LIMIT]
        return record, None
    if not isinstance(parsed, dict):
        record["outcome"] = "malformed_json"
        record["error"] = "top level is not an object"
        return record, None
    record["outcome"] = "ok"
    return record, parsed


def _select_devices(parsed, watch, phone):
    found = {"watch": {"found": False}, "phone": {"found": False}}
    wanted = {watch: "watch", phone: "phone"}
    devices = parsed.get("devices")
    if not isinstance(devices, dict):
        return found, "devices is not an object"
    for runtime, entries in devices.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            role = wanted.get(str(entry.get("udid", "")).upper())
            if role is None:
                continue
            record = {"found": True, "runtime": runtime}
            record.update({k: entry[k] for k in DEVICE_FIELDS if k in entry})
            found[role] = record
    return found, None


def _pair_member(pair, side):
    member = pair.get(side)
    if not isinstance(member, dict):
        return {}
    return {k: member[k] for k in ("udid", "name", "state") if k in member}


def _select_pairs(parsed, watch, phone):
    pairs = parsed.get("pairs")
    if not isinstance(pairs, dict):
        return {"error": "pairs is not an object"}
    exact, partial = [], []
    for pair_id, pair in pairs.items():
        if not isinstance(pair, dict):
            continue
        member_watch = _pair_member(pair, "watch")
        member_phone = _pair_member(pair, "phone")
        has_watch = str(member_watch.get("udid", "")).upper() == watch
        has_phone = str(member_phone.get("udid", "")).upper() == phone
        if not (has_watch or has_phone):
            continue
        record = {
            "pair_id": pair_id,
            "state": pair.get("state"),
            "watch": member_watch,
            "phone": member_phone,
        }
        (exact if has_watch and has_phone else partial).append(record)
    return {
        "selected_pair": exact[0] if len(exact) == 1 else None,
        "exact_pair_count": len(exact),
        "exact_pairs": exact,
        "pairs_with_only_one_device": partial,
    }


def _read_tail(path):
    """Return (record, text) for the last TAIL_BYTES of one exact regular file."""
    record = {"source": str(path)}
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        record["outcome"] = "missing"
        return record, None
    except PermissionError:
        record["outcome"] = "permission_denied"
        return record, None
    except OSError as error:
        record["outcome"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"[:TEXT_LIMIT]
        return record, None
    if not stat.S_ISREG(info.st_mode):
        record["outcome"] = "not_regular_file"
        return record, None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except PermissionError:
        record["outcome"] = "permission_denied"
        return record, None
    except OSError as error:
        record["outcome"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"[:TEXT_LIMIT]
        return record, None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            record["outcome"] = "not_regular_file"
            return record, None
        start = max(0, opened.st_size - TAIL_BYTES)
        os.lseek(descriptor, start, os.SEEK_SET)
        chunks, remaining = [], TAIL_BYTES
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError as error:
        record["outcome"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"[:TEXT_LIMIT]
        return record, None
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    record.update(file_size=opened.st_size, bytes_read=len(data), truncated=start > 0)
    lead = 0
    if start > 0:  # The cut may land inside one multi-byte character.
        while lead < min(3, len(data)) and 0x80 <= data[lead] <= 0xBF:
            lead += 1
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        text = decoder.decode(data[lead:], final=False)
    except UnicodeDecodeError as error:
        record["outcome"] = "encoding_error"
        record["error"] = str(error)[:TEXT_LIMIT]
        return record, None
    record["outcome"] = "ok"
    return record, text


def _write_atomic(path, text):
    pending = path.with_name(path.name + ".pending")
    try:
        pending.write_text(text, encoding="utf-8")
        pending.replace(path)
    except OSError:
        try:
            pending.unlink()
        except OSError:
            pass
        raise


def collect_failure(
    output_dir,
    watch_id,
    phone_id,
    phase,
    exit_code,
    sha,
    *,
    runner=spawn_bounded,
    clock=time.monotonic,
    log_root=None,
    now=None,
):
    """Write failure-evidence.json (+ tails) and return the recorded dict.

    Raises ValueError for an unusable failure identity and WriteError when the
    evidence file cannot be written. Every diagnostic problem is recorded.
    """
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise ValueError("exit_code must be an integer")
    if exit_code == 0:
        raise ValueError("exit_code 0 is not a failure; nothing to record")
    phase = _bounded_text(phase, "phase")
    sha = _bounded_text(sha, "sha")
    output_dir = Path(output_dir)
    log_root = Path(log_root) if log_root is not None else default_log_root()
    stamp = (now or datetime.now(timezone.utc)).isoformat()

    identity, pair = _identity(watch_id, phone_id)
    unavailable = []
    evidence = {
        "schema": SCHEMA,
        "kind": "failure_evidence",
        "test_receipt": False,
        "original_failure": {
            "status": "unpaid",
            "phase": phase,
            "exit_code": exit_code,
            "sha": sha,
        },
        "collected_at": stamp,
        "identity": identity,
        "rpc": {
            "per_call_timeout_seconds": RPC_TIMEOUT_SECONDS,
            "budget_seconds": RPC_BUDGET_SECONDS,
            "retries": 0,
            "calls": [],
        },
        "devices": None,
        "pairs": None,
        "log_tails": [],
        "diagnostics_unavailable": unavailable,
    }

    if pair is None:
        evidence["rpc"]["skipped"] = "missing_identity"
        unavailable.extend(["simctl_devices", "simctl_pairs"])
    else:
        watch, phone = pair
        deadline = clock() + RPC_BUDGET_SECONDS
        for name, argv in (
            ("simctl_devices", DEVICES_COMMAND),
            ("simctl_pairs", PAIRS_COMMAND),
        ):
            record, parsed = _call(argv, runner, clock, deadline)
            evidence["rpc"]["calls"].append(record)
            if parsed is None:
                unavailable.append(name)
                continue
            if argv == DEVICES_COMMAND:
                devices, error = _select_devices(parsed, watch, phone)
                evidence["devices"] = devices
                if error:
                    record["outcome"] = "malformed_json"
                    record["error"] = error
                    unavailable.append(name)
            else:
                evidence["pairs"] = _select_pairs(parsed, watch, phone)
                if "error" in evidence["pairs"]:
                    record["outcome"] = "malformed_json"
                    unavailable.append(name)

    tails = [("coresimulator", log_root / "CoreSimulator.log")]
    if pair is not None:
        tails.append(("watch-system", log_root / pair[0] / "system.log"))
        tails.append(("phone-system", log_root / pair[1] / "system.log"))
    if len(tails) > MAX_TAILS:
        raise AssertionError("At most three log tails may be read")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WriteError(f"Cannot create {output_dir}: {error}") from error
    for role, source in tails:
        record, text = _read_tail(source)
        record["role"] = role
        if text is not None:
            target = output_dir / f"failure-evidence-{role}.log"
            try:
                _write_atomic(target, text)
                record["output_file"] = target.name
            except OSError as error:
                record["outcome"] = "write_error"
                record["error"] = f"{type(error).__name__}: {error}"[:TEXT_LIMIT]
        if record["outcome"] != "ok":
            unavailable.append(f"log_{role}")
        evidence["log_tails"].append(record)

    try:
        _write_atomic(output_dir / EVIDENCE_FILE, json.dumps(evidence, indent=2) + "\n")
    except OSError as error:
        raise WriteError(f"Cannot write {EVIDENCE_FILE}: {error}") from error
    return evidence


def install_interrupt_handlers():
    def interrupted(_signum, _frame):
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, signal.SIG_IGN)
        raise KeyboardInterrupt

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)


def main(argv=None, *, runner=spawn_bounded, log_root=None):
    install_interrupt_handlers()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--watch-id", required=True)
    parser.add_argument("--phone-id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = collect_failure(
            args.output_dir,
            args.watch_id,
            args.phone_id,
            args.phase,
            args.exit_code,
            args.sha,
            runner=runner,
            log_root=log_root,
        )
    except ValueError as error:
        parser.error(str(error))
    except WriteError as error:
        print(f"Watch failure evidence not written: {error}", file=sys.stderr)
        return 3
    missing = ", ".join(evidence["diagnostics_unavailable"]) or "none"
    print(
        f"Watch failure evidence recorded for {evidence['original_failure']['phase']} "
        f"(original exit {evidence['original_failure']['exit_code']}); unavailable: {missing}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
