"""#12513: stop xcodebuild when a timed-out test leaves it waiting in silence.

Run 44094233390 (widgets shard): PickerCurrentGameJourneyTests asked the
simulator to launch the Watch app at 15:16:36. The simulator never answered.
xcodebuild reported the 5-minute overrun and then waited 38 more minutes for the
launch request to return ("Simulator device failed to launch ...: RequestDenied,
launch-failed") before it restarted the runner. That wait used up the time the one
infra retry needs.

After an overrun, xcodebuild normally restarts the runner within seconds and logs
"Restarting after unexpected exit, crash, or test timeout". This watchdog acts only
when an overrun is the newest event in the log and the log has then been silent for
QUIET_SECONDS. It stops xcodebuild and writes hang-watchdog.json. It never judges a
test. Whether the run may be retried is decided afterwards by watch_ui_infra_retry.py
from the log alone, and a test that hung in its own steps is never retried.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

QUIET_SECONDS = 180
POLL_SECONDS = 10
SIMCTL_TERMINATE_TIMEOUT = 25
LAUNCHCTL_LIST_TIMEOUT = 20
MID_TEST_STALL_THRESHOLD = 3
MAX_RECOVERY_ATTEMPTS_PER_WEDGE = 3
OVERRUN = "exceeded execution time allowance"
RESTART = "Restarting after unexpected exit, crash, or test timeout"
CLOCKFACE_IDLE = "Wait for com.apple.clockface to idle"
ANIM_TIMEOUT = "App animations complete notification not received, will attempt to continue."
SAFE_BOUNDARY = re.compile(
    r"^(?:Test Case '-\[BainLuckWatchUITests\.\w+ test\w+\]' (?:passed|failed) \(|"
    r"Restarting after unexpected exit, crash, or test timeout)"
)
TEST_STARTED = re.compile(r"^Test Case '-\[BainLuckWatchUITests\.\w+ test\w+\]' started\.$")
WATCH_APP_ELEMENT_WAIT = re.compile(r'Waiting [0-9.]+s for "watch\.(?!complication\.)')


def waiting_after_overrun(log: str) -> bool:
    """True when the newest overrun has not been followed by a runner restart."""
    overrun = log.rfind(OVERRUN)
    return overrun >= 0 and log.rfind(RESTART) < overrun


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(pid: int) -> None:
    for signum, grace in ((signal.SIGTERM, 30), (signal.SIGKILL, 0)):
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and alive(pid):
            time.sleep(1)
        if not alive(pid):
            return


def _sigkill_clockface_via_launchctl(
    watch_udid: str,
    primary_error: str,
    started: float,
) -> dict[str, object]:
    """Verify running ClockFace PID via launchctl + ps comm, then SIGKILL."""
    try:
        listing = subprocess.run(
            ["xcrun", "simctl", "spawn", watch_udid, "launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=LAUNCHCTL_LIST_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "method": "launchctl_sigkill",
            "returncode": -1,
            "simctl_error": primary_error,
            "stderr": f"{type(error).__name__}: {error}",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    if listing.returncode != 0:
        return {
            "method": "launchctl_sigkill",
            "returncode": -1,
            "simctl_error": primary_error,
            "stderr": listing.stderr.strip() or f"launchctl list exited {listing.returncode}",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    candidates: list[tuple[int, str]] = []
    for raw_line in listing.stdout.splitlines():
        parts = raw_line.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        label = parts[2].strip()
        if pid > 1 and (
            label == "com.apple.clockface"
            or label.startswith("UIKitApplication:com.apple.clockface[")
        ):
            candidates.append((pid, label))

    killed_pids: list[int] = []
    killed_labels: list[str] = []
    errors: list[str] = []
    for pid, label in candidates:
        try:
            ps_proc = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(f"ps pid {pid}: {type(error).__name__}: {error}")
            continue
        comm_name = Path(ps_proc.stdout.strip()).name if ps_proc.stdout.strip() else ""
        if ps_proc.returncode != 0 or comm_name != "ClockFace":
            errors.append(
                f"pid {pid} ({label}) skipped: comm={comm_name!r} rc={ps_proc.returncode}"
            )
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            killed_pids.append(pid)
            killed_labels.append(label)
        except ProcessLookupError:
            killed_pids.append(pid)
            killed_labels.append(label)
        except OSError as error:
            errors.append(f"kill pid {pid}: {type(error).__name__}: {error}")

    if killed_pids:
        return {
            "method": "launchctl_sigkill",
            "returncode": 0,
            "pids": killed_pids,
            "labels": killed_labels,
            "simctl_error": primary_error,
            "stderr": "; ".join(errors),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    return {
        "method": "launchctl_sigkill",
        "returncode": -1,
        "simctl_error": primary_error,
        "stderr": "; ".join(errors) if errors else "no running com.apple.clockface PID found",
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def terminate_clockface(watch_udid: str) -> dict[str, object]:
    """Terminate only the wedged watchOS ClockFace daemon so launchd respawns it."""
    started = time.monotonic()
    primary_error = ""
    try:
        proc = subprocess.run(
            ["xcrun", "simctl", "terminate", watch_udid, "com.apple.clockface"],
            capture_output=True,
            text=True,
            timeout=SIMCTL_TERMINATE_TIMEOUT,
        )
        if proc.returncode == 0:
            return {
                "method": "simctl_terminate",
                "returncode": 0,
                "stderr": proc.stderr.strip(),
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        primary_error = proc.stderr.strip() or f"simctl terminate exited {proc.returncode}"
    except (OSError, subprocess.SubprocessError) as error:
        primary_error = f"{type(error).__name__}: {error}"
    return _sigkill_clockface_via_launchctl(watch_udid, primary_error, started)


def watch(
    log_path: Path,
    pid: int,
    receipt: Path,
    quiet: float = QUIET_SECONDS,
    poll: float = POLL_SECONDS,
    watch_udid: str | None = None,
    clockface_receipt: Path | None = None,
    clockface_terminator: Callable[[str], dict[str, object]] = terminate_clockface,
) -> bool:
    """Returns True if it stopped xcodebuild."""
    last_size, last_change = -1, time.monotonic()
    scan_offset = 0
    prev_line = ""
    wedge_armed = False
    stalls_in_case = 0
    mid_test_recovered = False
    attempts_for_wedge = 0
    recoveries: list[dict[str, object]] = []

    def attempt_recovery(boundary: str, trigger: str) -> None:
        nonlocal wedge_armed, stalls_in_case, attempts_for_wedge
        assert watch_udid is not None
        outcome = clockface_terminator(watch_udid)
        attempts_for_wedge += 1
        recoveries.append({"boundary": boundary, "trigger": trigger, **outcome})
        if clockface_receipt is not None:
            clockface_receipt.write_text(
                json.dumps(
                    {"count": len(recoveries), "recoveries": recoveries},
                    indent=2,
                )
                + "\n"
            )
        if outcome.get("returncode") == 0:
            wedge_armed = False
            stalls_in_case = 0
            attempts_for_wedge = 0
        elif attempts_for_wedge >= MAX_RECOVERY_ATTEMPTS_PER_WEDGE:
            wedge_armed = False

    def process_new_lines() -> None:
        nonlocal scan_offset, prev_line, wedge_armed, stalls_in_case, mid_test_recovered, attempts_for_wedge
        if not watch_udid or not log_path.exists():
            return
        try:
            text = log_path.read_text(errors="replace")
        except OSError:
            return
        if len(text) < scan_offset:
            scan_offset = 0
            prev_line = ""
            wedge_armed = False
            stalls_in_case = 0
            mid_test_recovered = False
            attempts_for_wedge = 0
        chunk = text[scan_offset:]
        last_nl = chunk.rfind("\n")
        if last_nl < 0:
            return
        complete = chunk[: last_nl + 1]
        scan_offset += len(complete)
        for line in complete.splitlines():
            if TEST_STARTED.search(line):
                stalls_in_case = 0
                mid_test_recovered = False
            elif ANIM_TIMEOUT in line and CLOCKFACE_IDLE in prev_line:
                wedge_armed = True
                attempts_for_wedge = 0
                stalls_in_case += 1
                if stalls_in_case >= MID_TEST_STALL_THRESHOLD and not mid_test_recovered:
                    mid_test_recovered = True
                    attempt_recovery(line.strip(), "mid_test_3_stalls")
            elif wedge_armed and WATCH_APP_ELEMENT_WAIT.search(line):
                attempt_recovery(line.strip(), "watch_app_foreground")
            elif wedge_armed and SAFE_BOUNDARY.search(line):
                attempt_recovery(line.strip(), "safe_boundary")
            prev_line = line

    while alive(pid):
        try:
            size = log_path.stat().st_size
        except FileNotFoundError:
            size = 0
        now = time.monotonic()
        if size != last_size:
            last_size, last_change = size, now
            process_new_lines()
        elif now - last_change >= quiet and waiting_after_overrun(log_path.read_text(errors="replace")):
            stop(pid)
            receipt.write_text(json.dumps({
                "stopped": True,
                "reason": f"a test overran its time allowance and xcodebuild then logged nothing for {int(quiet)} s",
                "quiet_seconds": int(quiet),
            }, indent=2) + "\n")
            return True
        time.sleep(poll)
    process_new_lines()
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path", type=Path)
    parser.add_argument("pid", type=int)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--watch-udid", default=None)
    parser.add_argument("--clockface-receipt", type=Path, default=None)
    parser.add_argument("--poll-seconds", type=float, default=POLL_SECONDS)
    args = parser.parse_args()
    watch(
        args.log_path,
        args.pid,
        args.receipt,
        poll=args.poll_seconds,
        watch_udid=args.watch_udid,
        clockface_receipt=args.clockface_receipt,
    )


if __name__ == "__main__":
    main()
