"""Keep the long combined offline journey from broadening every UI timeout."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


APPROVED_300S_OVERRIDES = sorted(
    [
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingAwayScoreIsExplainedAtAccessibilitySize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingAwayScoreIsExplainedAtStandardSize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingBothScoreIsExplainedAtAccessibilitySize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingBothScoreIsExplainedAtStandardSize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingHomeScoreIsExplainedAtAccessibilitySize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testLiveMissingHomeScoreIsExplainedAtStandardSize",
            300,
        ),
        ("WidgetTapJourneyTests.swift", "testActualCircularLauncherAndTap", 300),
        ("WidgetTapJourneyTests.swift", "testActualComplicationHost", 300),
        ("WidgetTapJourneyTests.swift", "testActualCornerLauncherAndTap", 300),
        (
            "WidgetTapJourneyTests.swift",
            "testColdActualWidgetTapOffersPickerWithoutSelection",
            300,
        ),
        (
            "WidgetTapJourneyTests.swift",
            "testColdActualWidgetTapRetainsOfflineReading",
            300,
        ),
        (
            "WidgetTapJourneyTests.swift",
            "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap",
            300,
        ),
    ]
)


def test_retained_watch_cases_have_no_timeout_override():
    harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
    assert "-test-timeouts-enabled YES" in harness
    assert "-default-test-execution-time-allowance 180" in harness
    assert "-maximum-test-execution-time-allowance 300" in harness
    overrides = []
    for path in (ROOT / "ios/Bain Luck/BainLuckWatchUITests").glob("*.swift"):
        source = path.read_text()
        for match in re.finditer(r"executionTimeAllowance\s*=\s*(\d+)", source):
            methods = re.findall(r"func\s+(\w+)\s*\(", source[: match.start()])
            overrides.append((path.name, methods[-1], int(match[1])))
    # #12513: only the six 6-capture missing-live-score journeys and the six
    # full Carousel face-gallery journeys opt into the existing 300s ceiling;
    # the remaining 89 cases keep the default 180s allowance.
    assert sorted(overrides) == APPROVED_300S_OVERRIDES
