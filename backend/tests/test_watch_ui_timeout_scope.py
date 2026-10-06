"""Keep the long combined offline journey from broadening every UI timeout."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def test_watch_ui_timeout_override_is_scoped_to_combined_offline_case():
    harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
    assert "-test-timeouts-enabled YES" in harness
    assert "-default-test-execution-time-allowance 180" in harness
    assert "-maximum-test-execution-time-allowance 300" in harness
    overrides = []
    for path in (ROOT / "ios/Bain Luck/BainLuckWatchUITests").glob("*.swift"):
        source = path.read_text()
        for match in re.finditer(r"executionTimeAllowance\s*=\s*(\d+)", source):
            methods = re.findall(r"func\s+(\w+)\s*\(", source[:match.start()])
            overrides.append((path.name, methods[-1], int(match[1])))
    assert overrides == [("WatchDiscoverJourneyTests.swift",
                          "testSelectedGameStaysFirstAndDiscoveriesSurviveOfflineRelaunch", 300)]
