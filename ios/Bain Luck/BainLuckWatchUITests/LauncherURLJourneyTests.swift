#if DEBUG
import XCTest

final class LauncherURLJourneyTests: XCTestCase {
    @MainActor
    func testColdLauncherURLDeliversAndRetainsOfflineSelection() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT": "1"
        ]
        let launcher = try XCTUnwrap(URL(string: "bainluck-watch://selected-game"))
        app.terminate()
        // open launches the terminated app through actual OS URL delivery.
        app.open(launcher)
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20), "Cold URL did not open the picker")
        let receipt = app.staticTexts["watch.launch-receipt"]
        XCTAssertTrue(receipt.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label == %@", "Launcher opens: 1"), evaluatedWith: receipt)
        waitForExpectations(timeout: 15)
        try reveal(first, in: app)
        capture(app, name: "Cold OS launcher URL opened picker")
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertTrue(probability.label.contains("San Francisco Giants"))
        try reveal(probability, in: app)
        capture(app, name: "Cold launcher selected named Giants reading")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.open(launcher)
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(receipt.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label == %@", "Launcher opens: 1"), evaluatedWith: receipt)
        waitForExpectations(timeout: 15)
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertTrue(probability.label.contains("San Francisco Giants"), "Cold URL relaunch lost the selected named game")
        try reveal(state, in: app)
        capture(app, name: "Cold launcher offline saved-reading qualifier")
        try reveal(probability, in: app)
        capture(app, name: "Cold launcher offline retained named Giants reading")
        print("WATCH_UI_LAUNCHER_COLD=PASS")
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
        capture(app, name: "Unreachable launcher reading - \(element.identifier)")
        XCTFail("Cannot bring full reading into view")
        throw NSError(domain: "WatchLauncherJourney", code: 1)
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
