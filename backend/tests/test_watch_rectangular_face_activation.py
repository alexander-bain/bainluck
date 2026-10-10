"""Both Modular mount paths must activate the named face before accepting content."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT / "ios/Bain Luck/BainLuckWatchUITests/RectangularWidgetHostJourneyTests.swift"
)


def function(source, name):
    """Scope checks to one top-level XCTest method/helper, not the whole file."""
    declarations = list(re.finditer(r"^    (?:private )?func (\w+)\(", source, re.M))
    matches = [i for i, match in enumerate(declarations) if match[1] == name]
    assert len(matches) == 1, name
    index = matches[0]
    end = (
        declarations[index + 1].start()
        if index + 1 < len(declarations)
        else len(source)
    )
    return source[declarations[index].start() : end]


def ordered(body, *steps):
    position = 0
    for step in steps:
        location = body.find(step, position)
        assert location >= 0, f"Missing or out-of-order activation/content step: {step}"
        position = location + len(step)


def require_activation_paths(source):
    for name, center in [
        (
            "testActualRectangularWidgetShowsPublishedSavedReading",
            'let center = host.otherElements["center"].firstMatch',
        ),
        (
            "mountScoreFixtureOnModular",
            'let centers = host.otherElements.matching(identifier: "center")',
        ),
    ]:
        body = function(source, name)
        ordered(
            body,
            "installed.tap()",
            "XCUIDevice.shared.press(.home)",
            "try activateConfiguredModularFace(in: host)",
            "XCTAssertTrue(host.wait(for: .runningForeground, timeout: 15))",
            'XCTAssertTrue(host.otherElements["Watch Face"].firstMatch.waitForExistence(timeout: 15))',
            center,
        )
        assert body.count("try activateConfiguredModularFace(in: host)") == 1

    activation = function(source, "activateConfiguredModularFace")
    ordered(
        activation,
        "library.exists || face.exists",
        "XCTAssertEqual(XCTWaiter.wait(for: [arrived], timeout: 15), .completed",
        "if library.exists",
        'let title = host.staticTexts["Switcher Face Title"].firstMatch',
        '"modular, Customizable"',
        'title.label == "Modular"',
        "previews.count == 1",
        "preview.isHittable",
        "preview.tap()",
        "face.exists && !library.exists",
        "XCTAssertEqual(XCTWaiter.wait(for: [activated], timeout: 15), .completed",
        "XCTAssertTrue(face.isHittable)",
    )

    published = function(
        source, "testActualRectangularWidgetShowsPublishedSavedReading"
    )
    ordered(
        published,
        "try activateConfiguredModularFace(in: host)",
        "let center =",
        "let reading =",
        'XCTAssertTrue(reading.label.contains("San Francisco Giants win"))',
        'capture(host, "Actual Modular saved frame evidence before bounds assertion")',
        "try requireReadingWithinWidgetContent(reading, center: center, host: host)",
        'print("WATCH_UI_RECTANGULAR_ACTUAL_TYPED=PASS")',
    )
    assert "CGRect(origin: .zero" not in published
    for assertion in [
        'XCTAssertTrue(reading.label.contains("Saved"))',
        'XCTAssertTrue(reading.label.contains("64% · Live"))',
        'XCTAssertTrue(reading.label.contains("Observed "))',
        "center.isHittable",
        'let observedParts = reading.label.components(separatedBy: "Observed ")',
        "XCTAssertEqual(observedParts.count, 2)",
        "XCTAssertFalse(observedTimestamp.isEmpty",
    ]:
        assert assertion in published

    mount = function(source, "mountScoreFixtureOnModular")
    ordered(
        mount,
        "try activateConfiguredModularFace(in: host)",
        "let center =",
        "XCTAssertEqual(centers.count, 1",
        "XCTAssertTrue(center.isHittable",
        "return center",
    )
    score = function(source, "checkActualScoreColumnsColdTap")
    ordered(
        score,
        "let center = try mountScoreFixtureOnModular(in: host)",
        "let reading =",
        "XCTAssertTrue(reading.waitForExistence(timeout: 20)",
        "XCTAssertEqual(reading.label, expected)",
        "try requireReadingWithinWidgetContent(reading, center: center, host: host)",
        'XCTAssertTrue(host.otherElements["Watch Face"].firstMatch.exists)',
        'XCTAssertFalse(host.otherElements["Face Library View"].firstMatch.exists)',
        "XCTAssertEqual(reading.label, expected)",
        "center.tap()",
        'print("WATCH_SCORE_MODULAR_HOST_ROUTE_CHECKS=PASS scenario=',
    )
    bounds = function(source, "requireReadingWithinWidgetContent")
    ordered(
        bounds,
        "XCTAssertTrue(host.frame.contains(centerFrame))",
        "let remoteRoot = try XCTUnwrap(center.descendants(matching: .any)",
        "$0.frame.origin == .zero && $0.frame.size == centerFrame.size",
        "remoteRoot.descendants(matching: .any).matching(identifier: reading.identifier)",
        "XCTAssertEqual(localReadings.count, 1",
        "XCTAssertEqual(localReadings.firstMatch.frame, readingFrame)",
        "XCTAssertGreaterThan(readingFrame.width, 0)",
        "XCTAssertGreaterThan(readingFrame.height, 0)",
        "let contentFrame = remoteFrame.insetBy(dx: 7.5, dy: 7.5)",
        "XCTAssertTrue(remoteFrame.contains(readingFrame)",
        "XCTAssertTrue(contentFrame.contains(readingFrame)",
    )
    assert "host.frame.contains(reading.frame)" not in source
    assert "center.frame.contains(reading.frame)" not in source
    assert "CGRect(origin: .zero" not in bounds
    reveal = function(source, "reveal")
    ordered(
        reveal,
        "for _ in 0..<32",
        "element.isHittable && app.frame.contains(element.frame) && belowChrome",
        "if belowNavigationChrome && earlier, let priorTop = previousEarlierTop",
        "element.frame.minY == priorTop",
        "if usedRecoveryDrag",
        'XCTFail("Modular Add reveal made zero displacement after recovery:',
        'throw NSError(domain: "WatchRectangularHost", code: 2)',
        "usedRecoveryDrag = true",
        "dy: 0.40",
        "dy: 0.90",
        "continue",
    )
    for suffix, arguments in [
        ("LiveScore", 'scenario: "score", homeScore: 4, awayScore: 2, final: false'),
        ("HomeWinner", 'scenario: "final", homeScore: 4, awayScore: 2, final: true'),
        (
            "AwayWinner",
            'scenario: "away-final", homeScore: 2, awayScore: 4, final: true',
        ),
        ("Tied", 'scenario: "tie", homeScore: 2, awayScore: 2, final: true'),
        ("ZeroScore", 'scenario: "zero", homeScore: 4, awayScore: 0, final: false'),
    ]:
        assert f"try checkActualScoreColumnsColdTap({arguments})" in function(
            source, f"testActualRectangular{suffix}ColumnsColdTap"
        )


def test_rectangular_host_activates_named_face_before_accepting_widget_content():
    require_activation_paths(SOURCE.read_text())


@pytest.mark.parametrize(
    "method,required",
    [
        (
            "testActualRectangularWidgetShowsPublishedSavedReading",
            "try activateConfiguredModularFace(in: host)",
        ),
        ("mountScoreFixtureOnModular", "try activateConfiguredModularFace(in: host)"),
        (
            "checkActualScoreColumnsColdTap",
            "let center = try mountScoreFixtureOnModular(in: host)",
        ),
        ("activateConfiguredModularFace", "preview.tap()"),
        ("activateConfiguredModularFace", "face.exists && !library.exists"),
        ("requireReadingWithinWidgetContent", "let remoteRoot = try XCTUnwrap"),
        ("requireReadingWithinWidgetContent", "XCTAssertTrue(contentFrame.contains(readingFrame)"),
        ("reveal", "if usedRecoveryDrag"),
        ("reveal", "dy: 0.90"),
    ],
)
def test_each_activation_path_is_required_independently(method, required):
    source = SOURCE.read_text()
    body = function(source, method)
    assert body.count(required) == 1
    broken = source.replace(
        body, body.replace(required, "REMOVED_ACTIVATION_STEP", 1), 1
    )
    with pytest.raises(AssertionError):
        require_activation_paths(broken)


@pytest.mark.parametrize(
    "method",
    [
        "testActualRectangularWidgetShowsPublishedSavedReading",
        "mountScoreFixtureOnModular",
    ],
)
def test_content_cannot_be_accepted_before_named_face_activation(method):
    source = SOURCE.read_text()
    body = function(source, method)
    call = "try activateConfiguredModularFace(in: host)"
    # Keeping all tokens is insufficient: moving the call after the content
    # declaration must be rejected separately for both mounting paths.
    broken_body = body.replace(call, "", 1) + "\n" + call
    with pytest.raises(AssertionError):
        require_activation_paths(source.replace(body, broken_body, 1))
