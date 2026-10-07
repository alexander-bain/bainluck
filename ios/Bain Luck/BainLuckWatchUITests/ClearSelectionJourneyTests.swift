#if DEBUG
import XCTest

final class ClearSelectionJourneyTests: XCTestCase {
    @MainActor
    func testClearSavedOfflineSelectionSurvivesRelaunch() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(probability.exists && probability.label.contains("San Francisco Giants"))
        capture(app, name: "Saved offline game before clearing selection")
        let clear = app.buttons["watch.clear-selection"]
        XCTAssertTrue(clear.waitForExistence(timeout: 15))
        try reveal(clear, in: app)
        capture(app, name: "Reachable clear selected game recovery")
        clear.tap()
        try assertPickerRecovery(in: app, probability: probability, state: state)
        capture(app, name: "Cleared selection returns to picker recovery")

        app.terminate()
        app.launch()
        try assertPickerRecovery(in: app, probability: probability, state: state)
        capture(app, name: "Offline relaunch retains cleared selection and picker recovery")
        print("WATCH_UI_CLEAR_SELECTION=PASS")
    }

    @MainActor
    private func assertPickerRecovery(in app: XCUIApplication, probability: XCUIElement, state: XCUIElement) throws {
        let refresh = app.buttons["Refresh games"]
        XCTAssertTrue(refresh.waitForExistence(timeout: 20), "Clearing must leave picker refresh recovery")
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: probability)
        waitForExpectations(timeout: 15)
        XCTAssertFalse(state.exists, "A cleared saved game must not remain on screen")
        XCTAssertFalse(app.buttons["watch.clear-selection"].exists)
        XCTAssertFalse(app.buttons["watch.choose-another"].exists)
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertTrue(heading.exists)
        XCTAssertEqual(heading.label, "Choose your game")
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15), "Offline picker must explain its retry recovery")
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
        try reveal(heading, in: app)
        try reveal(error, in: app)
        expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: refresh)
        waitForExpectations(timeout: 15)
        try reveal(refresh, in: app)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<24 {
            if element.isHittable && app.frame.contains(element.frame) { return }
            let earlier = element.frame.minY < app.frame.minY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.60))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? 0.75 : 0.45))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, name: "Unreachable clear recovery - \(element.identifier)")
        XCTFail("Cannot bring full control into view")
        throw NSError(domain: "WatchClearSelectionJourney", code: 1)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
#endif
