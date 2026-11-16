"""Keep the long combined offline journey from broadening every UI timeout."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


APPROVED_TIMEOUT_OVERRIDES = sorted(
    [
        (
            "PickerCurrentGameJourneyTests.swift",
            "testHandoffHelpExplainsPhoneGestureAtAccessibilitySize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testHandoffHelpExplainsPhoneGestureAtStandardSize",
            300,
        ),
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
        (
            "PickerCurrentGameJourneyTests.swift",
            "testScheduledPickerShowsSuppliedTimeAtAccessibilitySize",
            300,
        ),
        (
            "PickerCurrentGameJourneyTests.swift",
            "testScheduledPickerShowsSuppliedTimeAtStandardSize",
            300,
        ),
        (
            "PickerSelectedStateJourneyTests.swift",
            "testSelectedGameIsMarkedAtAccessibilitySize",
            300,
        ),
        (
            "PickerSelectedStateJourneyTests.swift",
            "testSelectedGameIsMarkedInPickerAndCanChange",
            300,
        ),
        ("WidgetTapJourneyTests.swift", "testActualCircularLauncherAndTap", 540),
        ("WidgetTapJourneyTests.swift", "testActualComplicationHost", 540),
        ("WidgetTapJourneyTests.swift", "testActualCornerLauncherAndTap", 540),
        (
            "WidgetTapJourneyTests.swift",
            "testColdActualWidgetTapOffersPickerWithoutSelection",
            540,
        ),
        (
            "WidgetTapJourneyTests.swift",
            "testColdActualWidgetTapRetainsOfflineReading",
            540,
        ),
        (
            "WidgetTapJourneyTests.swift",
            "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap",
            540,
        ),
    ]
)


def test_retained_watch_cases_have_no_timeout_override():
    harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
    assert "-test-timeouts-enabled YES" in harness
    assert "-default-test-execution-time-allowance 180" in harness
    assert "-maximum-test-execution-time-allowance 540" in harness
    overrides = []
    for path in (ROOT / "ios/Bain Luck/BainLuckWatchUITests").glob("*.swift"):
        source = path.read_text()
        for match in re.finditer(r"executionTimeAllowance\s*=\s*(\d+)", source):
            methods = re.findall(r"func\s+(\w+)\s*\(", source[: match.start()])
            overrides.append((path.name, methods[-1], int(match[1])))
    # #12513: only the twelve slow hosted picker journeys (300s) and the six
    # Carousel face-gallery / clockface-idle journeys (540s) override 180s.
    assert sorted(overrides) == APPROVED_TIMEOUT_OVERRIDES
