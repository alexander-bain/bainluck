#!/usr/bin/env python3
"""Require both actual rendered Watch consent journeys before full UI acceptance."""
import argparse
from pathlib import Path
import re

CASES = {
    "testConsentSettingPersistsAndRevokesAtStandardSize": "WATCH_UI_DIAGNOSTICS_STANDARD=PASS",
    "testConsentSettingPersistsAndRevokesAtAccessibilitySize": "WATCH_UI_DIAGNOSTICS_LARGE=PASS",
}


def validate(log):
    lines = log.splitlines()
    for case, marker in CASES.items():
        prefix = f"Test Case '-[BainLuckWatchUITests.WatchDiagnosticsJourneyTests {case}]'"
        passes = [line for line in lines if re.fullmatch(re.escape(prefix) + r" passed \([0-9.]+ seconds\)\.", line)]
        contradictions = [line for line in lines if line.startswith(prefix) and (" failed " in line or " skipped " in line)]
        if lines.count(marker) != 1 or len(passes) != 1 or contradictions:
            raise ValueError(f"Rendered consent journey incomplete or contradictory: {case}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate(args.log.read_text())
    except ValueError as error:
        raise SystemExit(str(error))
    print("WATCH_DIAGNOSTICS_RECEIPT=PASS")


if __name__ == "__main__":
    main()
