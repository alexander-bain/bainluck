#if DEBUG
import XCTest

/// Exercise recovery controls using injected accessibility5 on the smallest Watch.
/// This is layout stress, not an OS Settings or physical-device Dynamic Type test.
/// Fixture transport fails offline without changing any host network settings.
final class LargeTextRecoveryJourneyTests: XCTestCase {
    @MainActor
    func testOfflinePickerReturnRetainsNamedReadingAtLargestTextSize() throws {
        let app = try selectedOfflineGame()
        defer { app.terminate() }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let reading = probability.label
        let help = app.buttons["watch.continue-on-phone"]
        try reveal(help, in: app)
        capture(app, "Largest text reachable Continue on iPhone control")
        help.tap()
        let dismissHelp = app.buttons["OK"]
        XCTAssertTrue(dismissHelp.waitForExistence(timeout: 15))
        capture(app, "Continue on iPhone explanation without delivery claim")
        dismissHelp.tap()
        let change = app.buttons["watch.choose-another"]
        try reveal(change, in: app)
        capture(app, "Largest text reachable change control")
        change.tap()
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertEqual(heading.value as? String, "accessibility5", "The sheet itself must receive the layout-stress size")
        try reveal(heading, in: app)
        capture(app, "Verified largest text sheet heading")
        try reveal(error, in: app)
        XCTAssertEqual(error.label, "Couldn't refresh available games. Try again.")
        capture(app, "Largest text offline picker recovery")
        let cancel = app.buttons["watch.picker-cancel"].firstMatch
        try reveal(cancel, in: app)
        capture(app, "Largest text reachable return control")
        cancel.tap()
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: cancel)
        waitForExpectations(timeout: 15)
        let state = try assertSavedOfflineState(in: app)
        try reveal(state, in: app)
        capture(app, "Largest text returned saved offline qualifier")
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, reading)
        try reveal(probability, in: app)
        capture(app, "Largest text returned complete named probability")
    }

    @MainActor
    func testOfflineClearSurvivesRelaunchAtLargestTextSize() throws {
        let app = try selectedOfflineGame()
        defer { app.terminate() }
        let clear = app.buttons["watch.clear-selection"]
        try reveal(clear, in: app)
        capture(app, "Largest text reachable clear control")
        clear.tap()
        try assertClearedPicker(in: app)
        capture(app, "Largest text cleared offline recovery")
        app.terminate()
        app.launch()
        try assertClearedPicker(in: app)
        capture(app, "Largest text cold relaunch stays cleared")
    }

    @MainActor
    private func selectedOfflineGame() throws -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": "1"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["watch.picker-heading"].value as? String, "accessibility5")
        try reveal(first, in: app)
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        XCTAssertTrue(probability.label.contains("64%"))
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = try assertSavedOfflineState(in: app)
        try reveal(state, in: app)
        capture(app, "Largest text saved offline qualifier")
        try reveal(probability, in: app)
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        XCTAssertTrue(probability.label.contains("64%"))
        capture(app, "Largest text saved complete named probability")
        return app
    }

    @MainActor
    private func assertSavedOfflineState(in app: XCUIApplication) throws -> XCUIElement {
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertEqual(state.value as? String, "accessibility5")
        return state
    }

    @MainActor
    private func assertClearedPicker(in app: XCUIApplication) throws {
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertTrue(heading.waitForExistence(timeout: 15))
        XCTAssertEqual(heading.value as? String, "accessibility5")
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.game-state"].firstMatch.exists)
        XCTAssertFalse(app.buttons["watch.clear-selection"].exists)
        XCTAssertFalse(app.buttons["watch.choose-another"].exists)
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(error.label, "Couldn't refresh available games. Try again.")
        try reveal(heading, in: app)
        try reveal(error, in: app)
        let refresh = app.buttons["Refresh games"]
        expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: refresh)
        waitForExpectations(timeout: 15)
        try reveal(refresh, in: app)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        for _ in 0..<32 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            let earlier = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, "Unreachable largest text control - \(element.identifier)")
        XCTFail("Cannot bring complete element into view: \(element.identifier), \(element.frame), viewport \(app.frame)")
        throw NSError(domain: "WatchLargeTextRecovery", code: 1)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
#endif
