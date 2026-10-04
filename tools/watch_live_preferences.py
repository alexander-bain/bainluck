"""Capture a verified, immutable preferences copy after bounded read-only polling."""
import argparse
import json
from pathlib import Path
import plistlib
import time

from watch_live_receipt import verify


def capture(log: str, source: Path, output: Path, observations: Path,
            timeout: float = 30, clock=time.monotonic, pause=time.sleep) -> None:
    started = clock()
    history = []
    saved_initial = False
    while True:
        accepted = False
        try:
            raw = source.read_bytes()
            if not saved_initial:
                output.with_name("preferences-initial.plist").write_bytes(raw)
                saved_initial = True
            # Validate the same bytes that become the evidence; never re-copy a
            # changing source after it passes. This performs no simulator write.
            output.write_bytes(raw)
            verify(log, 0, plistlib.loads(raw))
            accepted = True
            reason = "PASS"
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
            reason = str(error)
        elapsed = clock() - started
        history.append({"elapsed_seconds": elapsed, "verdict": "PASS" if accepted else "UNPAID", "reason": reason})
        observations.write_text(json.dumps(history, indent=2) + "\n")
        if accepted:
            return
        if elapsed >= timeout:
            raise ValueError(f"Preferences evidence UNPAID after {timeout}s: {reason}")
        pause(min(1, timeout - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    capture(args.log.read_text(), args.source, args.output, args.observations)


if __name__ == "__main__":
    main()
