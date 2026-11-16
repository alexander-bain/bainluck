"""#12513: decide whether a Watch UI run died on the simulator, not on a test.

Run 43867918866 (corner shard): 92 s into its first test, xcodebuild timed out
reaching the companion iPhone simulator's
"com.apple.instruments.deviceservice.lockdown" service, the runner died, and the
restarted runner executed nothing. No check failed. The harness waits for both
simulators' services and retries such a run ONCE. It never retries a run in which
any test failed a check or ran past its time limit, so a real failure can't be
retried away.
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
    re.compile(r"exceeded execution time allowance"),
    re.compile(r"^WATCH_UI_\w+=FAIL", re.MULTILINE),
)


def infra_abort(log: str) -> str | None:
    """The connection signature that ended this run, or None if a retry is not allowed."""
    if any(pattern.search(log) for pattern in REAL_FAILURE):
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
