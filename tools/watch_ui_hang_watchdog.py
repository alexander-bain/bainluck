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
OVERRUN = "exceeded execution time allowance"
RESTART = "Restarting after unexpected exit, crash, or test timeout"
CLOCKFACE_IDLE = "Wait for com.apple.clockface to idle"
ANIM_TIMEOUT = "App animations complete notification not received, will attempt to continue."
SAFE_BOUNDARY = re.compile(
    r"^(?:Test Case '-\[BainLuckWatchUITests\.\w+ test\w+\]' (?:passed|failed) \(|"
    r"Restarting after unexpected exit, crash, or test timeout)"
)


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


def terminate_clockface(watch_udid: str) -> dict[str, object]:
    """Terminate only the wedged watchOS ClockFace daemon so launchd respawns it."""
    try:
        proc = subprocess.run(
            ["xcrun", "simctl", "terminate", watch_udid, "com.apple.clockface"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "returncode": -1,
            "stderr": f"{type(error).__name__}: {error}",
        }


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
    recoveries: list[dict[str, object]] = []

    def process_new_lines() -> None:
        nonlocal scan_offset, prev_line, wedge_armed
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
        chunk = text[scan_offset:]
        last_nl = chunk.rfind("\n")
        if last_nl < 0:
            return
        complete = chunk[: last_nl + 1]
        scan_offset += len(complete)
        for line in complete.splitlines():
            if ANIM_TIMEOUT in line and CLOCKFACE_IDLE in prev_line:
                wedge_armed = True
            elif wedge_armed and SAFE_BOUNDARY.search(line):
                wedge_armed = False
                outcome = clockface_terminator(watch_udid)
                recoveries.append({"boundary": line.strip(), **outcome})
                if clockface_receipt is not None:
                    clockface_receipt.write_text(
                        json.dumps(
                            {"count": len(recoveries), "recoveries": recoveries},
                            indent=2,
                        )
                        + "\n"
                    )
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
