"""Fail closed unless every Discoveries polish case and standalone marker passed."""
import argparse
from pathlib import Path
import re

CASES = {
    "testTopRefreshRecoversAndSeparatesStoriesAtStandardSize": "WATCH_UI_DISCOVERIES_POLISH_STANDARD=PASS",
    "testTopRefreshRecoversAndSeparatesStoriesAtAccessibilitySize": "WATCH_UI_DISCOVERIES_POLISH_LARGE=PASS",
    "testSelectedGameKeepsSummaryBeforeSeparatedStories": "WATCH_UI_DISCOVERIES_POLISH_SELECTED=PASS",
}


def verify(log: str) -> None:
    lines = log.splitlines()
    for method, marker in CASES.items():
        if lines.count(marker) != 1:
            raise ValueError(f"Expected one standalone {marker}")
        name = f"BainLuckWatchUITests.WatchDiscoverPolishTests {method}"
        passed = rf"^Test Case '-\[{re.escape(name)}\]' passed \([0-9.]+ seconds\)\.$"
        if len(re.findall(passed, log, re.MULTILINE)) != 1:
            raise ValueError(f"Expected one exact passing case: {method}")
        adverse = rf"^Test Case '-\[{re.escape(name)}\]' (?:failed|skipped)[^\n]*$"
        if re.search(adverse, log, re.MULTILINE):
            raise ValueError(f"Case failed or skipped: {method}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    try:
        verify(args.log.read_text(errors="replace"))
    except ValueError as error:
        raise SystemExit(f"Discoveries polish gate unpaid: {error}")
