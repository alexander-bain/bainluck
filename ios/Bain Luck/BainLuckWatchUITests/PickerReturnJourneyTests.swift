#if DEBUG
import XCTest

final class PickerReturnJourneyTests: XCTestCase {
    @MainActor
    func testReturnFromPickerPreservesSelectedGameAndSavedOfflineReading() throws {
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
        let reading = probability.label
        try openPicker(in: app)
        XCTAssertTrue(app.buttons["watch.pick.202"].waitForExistence(timeout: 15))
        try returnToGame(in: app)
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, reading, "Returning must preserve the selected named game")
        try reveal(probability, in: app)
        capture(app, "Picker return preserves named Giants reading")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(probability.exists && probability.label.contains("San Francisco Giants"))
        try openPicker(in: app)
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(error.label, "Couldn't refresh available games. Try again.")
        try reveal(error, in: app)
        capture(app, "Offline picker failure retains explicit return")
        try returnToGame(in: app)
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, reading, "Offline picker return must retain the saved named reading")
        try reveal(state, in: app)
        capture(app, "Offline return preserves saved reading qualifier")
        try reveal(probability, in: app)
        capture(app, "Offline return preserves named Giants reading")
        print("WATCH_UI_PICKER_RETURN=PASS")
    }

    @MainActor
    private func openPicker(in app: XCUIApplication) throws {
        let change = app.buttons["watch.choose-another"]
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        try reveal(change, in: app)
        change.tap()
        XCTAssertTrue(app.buttons["watch.picker-cancel"].waitForExistence(timeout: 15))
    }

    @MainActor
    private func returnToGame(in app: XCUIApplication) throws {
        let cancel = app.buttons["watch.picker-cancel"]
        try reveal(cancel, in: app)
        capture(app, "Reachable explicit return to selected game")
        cancel.tap()
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: cancel)
        waitForExpectations(timeout: 15)
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
        capture(app, "Unreachable picker return - \(element.identifier)")
        XCTFail("Cannot bring full control into view")
        throw NSError(domain: "WatchPickerReturnJourney", code: 1)
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
