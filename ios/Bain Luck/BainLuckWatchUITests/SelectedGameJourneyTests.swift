import XCTest

final class SelectedGameJourneyTests: XCTestCase {
    @MainActor
    func testPickerSelectionSurvivesOfflineRelaunchAndCanChange() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1"
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
        capture(app, name: "Selected named game")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        let offline = NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline")
        expectation(for: offline, evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(probability.exists)
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        XCTAssertTrue(probability.label.contains("64%"))
        capture(app, name: "Saved reading after offline relaunch")

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
        capture(app, name: "Changed selection")
        app.terminate()
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
