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

import json
import os
import signal
import sys
import time
from pathlib import Path

QUIET_SECONDS = 180
POLL_SECONDS = 10
OVERRUN = "exceeded execution time allowance"
RESTART = "Restarting after unexpected exit, crash, or test timeout"


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


def watch(log_path: Path, pid: int, receipt: Path, quiet: float = QUIET_SECONDS,
          poll: float = POLL_SECONDS) -> bool:
    """Returns True if it stopped xcodebuild."""
    last_size, last_change = -1, time.monotonic()
    while alive(pid):
        try:
            size = log_path.stat().st_size
        except FileNotFoundError:
            size = 0
        now = time.monotonic()
        if size != last_size:
            last_size, last_change = size, now
        elif now - last_change >= quiet and waiting_after_overrun(log_path.read_text(errors="replace")):
            stop(pid)
            receipt.write_text(json.dumps({
                "stopped": True,
                "reason": f"a test overran its time allowance and xcodebuild then logged nothing for {int(quiet)} s",
                "quiet_seconds": int(quiet),
            }, indent=2) + "\n")
            return True
        time.sleep(poll)
    return False


def main() -> None:
    log_path, pid, receipt = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    watch(log_path, pid, receipt)


if __name__ == "__main__":
    main()
