"""Leave time to upload an unpaid Watch gate's evidence before job cancellation.

This runs the entire unchanged gate exactly once. It is not a test receipt and
cannot make a failed/unfinished suite pass. Only its own new process group is
signalled; no simulator/daemon cleanup or global process matching is performed.
"""

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

MAX_SECONDS = 50 * 60


class Interrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def _write(path, data):
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def _stop(process, grace_seconds):
    # Signal only our private group. Do not use signal-0 liveness probes: a
    # leader can exit while descendants still need the full flush interval.
    first_error = None
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            break
        except OSError as error:
            first_error = first_error or error
            continue  # Still attempt the remaining bounded shutdown stages.
        if signum == signal.SIGKILL:
            break
        deadline = time.monotonic() + grace_seconds
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
        # Reaping the leader does not prove its descendants have exited.
        time.sleep(max(0, deadline - time.monotonic()))
    process.wait(timeout=5)
    if first_error is not None:
        raise first_error


def run_gate(command, output_dir, *, seconds=MAX_SECONDS, grace_seconds=15):
    if not command or not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS:
        raise ValueError("A command and bounded gate deadline are required")
    if not math.isfinite(grace_seconds) or not 0 < grace_seconds <= 15:
        raise ValueError("Invalid shutdown grace")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    record = {
        "status": "RUNNING",
        "exit_code": None,
        "attempts": 1,
        "budget_seconds": seconds,
        "scope": "gate_process_only",
    }
    _write(output / "deadline.json", record)
    started = time.monotonic()
    process = None
    phase = "launch"
    try:
        with (output / "gate-supervisor.log").open("w") as log:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            phase = "wait"
            try:
                code = process.wait(timeout=seconds)
                record["status"] = "COMPLETED" if code == 0 else "FAILED"
                record["exit_code"] = code if code >= 0 else 128 - code
            except subprocess.TimeoutExpired:
                record.update(status="DEADLINE", exit_code=124)
            except Interrupted as error:
                record.update(status="CANCELLED", exit_code=128 + error.signum)
            finally:
                if record["status"] in {"DEADLINE", "CANCELLED"}:
                    phase = "stop"
                    _stop(process, grace_seconds)
    except (OSError, subprocess.TimeoutExpired) as error:
        record.update(
            status="LAUNCH_FAILED" if process is None else "PROCESS_CONTROL_FAILED",
            exit_code=127 if process is None else 1,
            error_phase=phase,
            error_type=type(error).__name__,
            error_errno=getattr(error, "errno", None),
        )
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _write(output / "deadline.json", record)
        if record["exit_code"] != 0:
            # The full-suite validator remains the sole PASS authority. A gate
            # interrupted after writing a receipt must still be unpaid.
            receipt = output / "receipt.json"
            prior = {}
            if receipt.exists():
                try:
                    prior = json.loads(receipt.read_text())
                except (ValueError, OSError):
                    pass
            _write(
                receipt,
                {
                    **prior,
                    "verdict": "UNPAID",
                    "reason": "Gate supervisor: " + record["status"],
                },
            )
    return record["exit_code"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command

    def interrupted(signum, _frame):
        signal.signal(signum, signal.SIG_IGN)
        raise Interrupted(signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    raise SystemExit(run_gate(command, args.output_dir))


if __name__ == "__main__":
    main()
