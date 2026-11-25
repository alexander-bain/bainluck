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
    re.compile(r"encountered an error \(Early unexpected exit, operation never finished bootstrapping"),
    re.compile(r"encountered an error \(Failed to establish communication with the test runner"),
    re.compile(r"The test runner failed to initialize for UI testing"),
    re.compile(r"(CoreSimulatorService|SimLaunchHostService)[^\n]*Connection interrupted"),
    re.compile(r"Simulator device failed to launch com\.bainluck\.Bain-Luck\.watchkitapp[^\n]*RequestDenied"),
)
# Any of these means a test itself failed; never retry over them.
TEST_CASE_ERROR = re.compile(r": error: -\[BainLuckWatchUITests\.")
WATCH_FAIL_MARKER = re.compile(r"^WATCH_UI_\w+=FAIL", re.MULTILINE)
APP_LAUNCH_REFUSED_ERROR = re.compile(
    r"^<unknown>:0: error: -\[BainLuckWatchUITests\.(\w+) (test\w+)\] : "
    r"(?:Application 'com\.bainluck\.Bain-Luck\.watchkitapp' does not have a process ID|"
    r"Failed to get background assertion for target app with pid \d+:.*)$"
)
SESSION_STARTED_MARKERS = (
    "Setting up automation session",
    "Wait for com.bainluck.Bain-Luck.watchkitapp to idle",
)
OVERRUN = re.compile(
    r"^Test Case '-\[BainLuckWatchUITests\.(\w+) (test\w+)\]' exceeded execution time allowance", re.MULTILINE
)
STEP = re.compile(r"^\s+t =\s+[0-9.]+s\s+(\S.*?)\s*$")
APP_LAUNCH = "Launch com.bainluck.Bain-Luck.watchkitapp"
# System-side step XCTest may log before it sends the request; our app has not started.
BEFORE_REQUEST = "Waiting for system app quiescence"
CLOCKFACE_IDLE = "Wait for com.apple.clockface to idle"
CLOCKFACE_ANIM_TIMEOUT = "App animations complete notification not received, will attempt to continue."
CLOCKFACE_STALL_THRESHOLD = 4


def error_is_pre_session_launch_refusal(log: str, line: str, *, pos: int | None = None) -> bool:
    """True only when XCTest failed to establish a simulator launch before any app session started."""
    match = APP_LAUNCH_REFUSED_ERROR.match(line.strip())
    if not match:
        return False
    suite, case = match.groups()
    name = f"Test Case '-[BainLuckWatchUITests.{suite} {case}]'"
    cursor = log.find(line) if pos is None else pos
    if cursor < 0:
        return False
    start = log.rfind(f"{name} started.", 0, cursor)
    end = log.find(f"{name} failed (", cursor)
    if start < 0 or end < 0:
        return False
    block = log[start:end]
    if APP_LAUNCH not in block:
        return False
    return not any(marker in block for marker in SESSION_STARTED_MARKERS)


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


def overran_in_clockface_idle_hang(log: str, suite: str, case: str) -> bool:
    """True when the overrun test lost at least 4 x 60 s waiting for com.apple.clockface idle."""
    name = f"Test Case '-[BainLuckWatchUITests.{suite} {case}]'"
    end = log.find(f"{name} exceeded execution time allowance")
    start = log.rfind(f"{name} started.", 0, end)
    if start < 0 or end < 0:
        return False
    lines = log[start:end].splitlines()
    stalls = sum(
        1
        for i in range(len(lines) - 1)
        if CLOCKFACE_IDLE in lines[i] and CLOCKFACE_ANIM_TIMEOUT in lines[i + 1]
    )
    return stalls >= CLOCKFACE_STALL_THRESHOLD


def infra_abort(log: str) -> str | None:
    """The simulator signature that ended this run, or None if a retry is not allowed."""
    if WATCH_FAIL_MARKER.search(log):
        return None
    launch_refused_cases: list[str] = []
    for line_match in re.finditer(r"^.*$", log, re.MULTILINE):
        line = line_match.group(0)
        if not TEST_CASE_ERROR.search(line):
            continue
        if not error_is_pre_session_launch_refusal(log, line, pos=line_match.start()):
            return None
        m = APP_LAUNCH_REFUSED_ERROR.match(line.strip())
        if m:
            launch_refused_cases.append(f"{m.group(1)}/{m.group(2)}")
    overruns = OVERRUN.findall(log)
    if overruns:
        if all(overran_in_launch_request(log, suite, case) for suite, case in overruns):
            suite, case = overruns[0]
            return f"the simulator never accepted the Watch app's launch in {suite}/{case}"
        if all(
            overran_in_launch_request(log, suite, case)
            or overran_in_clockface_idle_hang(log, suite, case)
            for suite, case in overruns
        ):
            clockface_cases = [
                f"{suite}/{case}"
                for suite, case in overruns
                if overran_in_clockface_idle_hang(log, suite, case)
            ]
            return (
                "com.apple.clockface stopped reporting animation idle "
                f"({len(clockface_cases)} overrun case(s): {', '.join(clockface_cases)})"
            )
        return None
    if launch_refused_cases:
        return (
            "the simulator refused Watch app launch before automation session start "
            f"({len(launch_refused_cases)} case(s): {', '.join(launch_refused_cases)})"
        )
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
