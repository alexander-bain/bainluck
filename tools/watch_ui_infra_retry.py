"""#12513: decide whether a Watch UI run died on the simulator, not on a test.

Run 43867918866 (corner shard): 92 s into its first test, xcodebuild timed out
reaching the companion iPhone simulator's
"com.apple.instruments.deviceservice.lockdown" service, the runner died, and the
restarted runner executed nothing. No check failed. The harness waits for both
simulators' services and retries such a run ONCE. It never retries a run in which
any test failed a check, so a real failure can't be retried away.

Run 44094233390 (widgets shard): a test's launch request for the Watch app was
never accepted by the simulator. The log shows "Launch com.bainluck..." as the
test's last step, with no quiescence wait, automation session or idle wait after
it. The test then overran its 5 minutes and the simulator later answered
"RequestDenied, launch-failed". None of our code had run. An overrun counts as a
simulator failure only in exactly that shape. Every other overrun, including one in
a test's own steps or while our app was starting, is never retried.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Signatures of a simulator or test-runner connection that dropped.
CONNECTION_LOST = (
    re.compile(r'unable to connect to "com\.apple\.instruments\.deviceservice[^"]*"'),
    re.compile(r"encountered an error \(Test crashed with signal \w+ before establishing connection\.\)"),
    re.compile(r"encountered an error \(Lost connection to (the )?test manager service"),
)
# Any of these means a test itself failed; never retry over them.
REAL_FAILURE = (
    re.compile(r": error: -\[BainLuckWatchUITests\."),
    re.compile(r"^WATCH_UI_\w+=FAIL", re.MULTILINE),
)
OVERRUN = re.compile(
    r"^Test Case '-\[BainLuckWatchUITests\.(\w+) (test\w+)\]' exceeded execution time allowance", re.MULTILINE
)
STEP = re.compile(r"^\s+t =\s+[0-9.]+s\s+(\S.*?)\s*$")
APP_LAUNCH = "Launch com.bainluck.Bain-Luck.watchkitapp"
# System-side step XCTest may log before it sends the request; our app has not started.
BEFORE_REQUEST = "Waiting for system app quiescence"


def overran_in_launch_request(log: str, suite: str, case: str) -> bool:
    """True when the overrun test's last step was the Watch app's launch request
    and nothing after it shows the app process starting."""
    name = f"Test Case '-[BainLuckWatchUITests.{suite} {case}]'"
    end = log.find(f"{name} exceeded execution time allowance")
    start = log.rfind(f"{name} started.", 0, end)
    if start < 0 or end < 0:
        return False
    steps = [m.group(1) for m in map(STEP.match, log[start:end].splitlines()) if m]
    if steps and steps[-1] == BEFORE_REQUEST:
        steps.pop()
    return bool(steps) and steps[-1] == APP_LAUNCH


def infra_abort(log: str) -> str | None:
    """The simulator signature that ended this run, or None if a retry is not allowed."""
    if any(pattern.search(log) for pattern in REAL_FAILURE):
        return None
    overruns = OVERRUN.findall(log)
    if overruns:
        if all(overran_in_launch_request(log, suite, case) for suite, case in overruns):
            suite, case = overruns[0]
            return f"the simulator never accepted the Watch app's launch in {suite}/{case}"
        return None
    for pattern in CONNECTION_LOST:
        match = pattern.search(log)
        if match:
            return match.group(0)
    return None


def main() -> None:
    log_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    reason = infra_abort(log_path.read_text(errors="replace"))
    out_path.write_text(json.dumps({"retry": reason is not None, "reason": reason}, indent=2) + "\n")
    raise SystemExit(0 if reason else 1)


if __name__ == "__main__":
    main()
