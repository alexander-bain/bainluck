import XCTest

final class SelectedGameJourneyTests: XCTestCase {
    @MainActor
    func testPickerSelectionSurvivesOfflineRelaunchAndCanChange() throws {
        try runJourney(stressLargeText: false)
    }

    @MainActor
    func testAccessibilityLayoutStressKeepsReadingsAndControlsReachable() throws {
        try runJourney(stressLargeText: true)
    }

    @MainActor
    private func runJourney(stressLargeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": stressLargeText ? "1" : "0"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20), "Fixture picker never appeared")
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        try tap(first, in: app)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15), "Selection did not open a game")
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        XCTAssertTrue(probability.label.contains("64%"))
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        let receivedSize = try XCTUnwrap(state.value as? String)
        print("WATCH_UI_\(stressLargeText ? "STRESS" : "STANDARD")_TYPE=\(receivedSize)")
        if stressLargeText { XCTAssertEqual(receivedSize, "accessibility5") }
        let largeText = stressLargeText
        capture(app, name: "Selected game state - \(receivedSize)")
        if largeText {
            let homeScore = app.descendants(matching: .any)["watch.home-score"].firstMatch
            try reveal(homeScore, in: app)
            XCTAssertTrue(homeScore.label.contains("San Francisco Giants"))
            XCTAssertTrue(homeScore.label.contains("score 3"))
            capture(app, name: "Large text named score")
            try reveal(probability, in: app)
        }
        capture(app, name: "Selected named game")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        let offline = NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline")
        expectation(for: offline, evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertEqual(state.value as? String, receivedSize)
        XCTAssertTrue(probability.exists)
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        XCTAssertTrue(probability.label.contains("64%"))
        capture(app, name: "Saved reading after offline relaunch")
        if largeText {
            try reveal(probability, in: app)
            capture(app, name: "Large text saved probability")
        }

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "0"
        app.launch()
        let change = app.buttons["watch.choose-another"]
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        try tap(change, in: app)
        let second = app.buttons["watch.pick.202"]
        XCTAssertTrue(second.waitForExistence(timeout: 15))
        try tap(second, in: app)
        let changed = NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Buffalo Bills", "55%")
        expectation(for: changed, evaluatedWith: probability)
        waitForExpectations(timeout: 15)
        expectation(for: NSPredicate(format: "hittable == true"), evaluatedWith: state)
        waitForExpectations(timeout: 10)
        XCTAssertEqual(state.value as? String, receivedSize)
        capture(app, name: "Changed game identity")
        if largeText { try reveal(probability, in: app) }
        XCTAssertTrue(probability.isHittable, "The new named probability must be reachable after selection")
        XCTAssertTrue(app.frame.contains(probability.frame), "The whole named probability group must fit in the visible screen")
        capture(app, name: "Changed selection")
        app.terminate()
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<24 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            print("WATCH_UI_REVEAL \(element.identifier) reading=\(element.frame) viewport=\(app.frame)")
            let towardEarlierContent = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: towardEarlierContent ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, name: "Unreachable reading - \(element.identifier)")
        XCTFail("Cannot bring full reading into view: \(element.identifier)")
        throw NSError(domain: "WatchJourney", code: 2)
    }

    @MainActor
    private func tap(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<8 {
            if element.isHittable { element.tap(); return }
            app.swipeUp()
        }
        XCTFail("Expected control was not hittable: \(element.identifier)")
        throw NSError(domain: "WatchJourney", code: 1)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
