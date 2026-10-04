#if DEBUG
import XCTest

final class ProbabilityRoundingJourneyTests: XCTestCase {
    @MainActor
    func testPairedRoundingPersistsOfflineAndDrawSportKeepsScalarRounding() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = [
            "BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_ROUNDING": "1"
        ]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        try assertProbability(probability, team: "Tampa Bay Rays", percent: "45%", in: app)
        capture(app, name: "Paired baseball home reading 45 percent")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Saved reading", "Offline"), evaluatedWith: state)
        waitForExpectations(timeout: 15)
        try assertProbability(probability, team: "Tampa Bay Rays", percent: "45%", in: app)
        capture(app, name: "Saved offline paired baseball reading remains 45 percent")
        print("WATCH_UI_ROUNDING_PAIR=45")

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "0"
        app.launch()
        let change = app.buttons["watch.choose-another"]
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        try reveal(change, in: app)
        change.tap()
        let second = app.buttons["watch.pick.202"]
        XCTAssertTrue(second.waitForExistence(timeout: 15))
        try reveal(second, in: app)
        second.tap()
        expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Chelsea", "46%"), evaluatedWith: probability)
        waitForExpectations(timeout: 15)
        try assertProbability(probability, team: "Chelsea", percent: "46%", in: app)
        capture(app, name: "Draw-priced soccer home reading remains scalar 46 percent")
        print("WATCH_UI_ROUNDING_DRAW=46")
    }

    @MainActor
    private func assertProbability(_ probability: XCUIElement, team: String, percent: String, in app: XCUIApplication) throws {
        XCTAssertEqual(probability.label.replacingOccurrences(of: " ", with: ""), "\(team) win probability, \(percent)".replacingOccurrences(of: " ", with: ""))
        try reveal(probability, in: app)
        // The app groups this reading with accessibility children ignored.
        // Its visible text is therefore verified from the retained screenshot,
        // while the complete grouped spoken reading is asserted here.
        XCTAssertTrue(probability.isHittable && app.frame.contains(probability.frame))
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
        capture(app, name: "Unreachable rounding reading - \(element.identifier)")
        XCTFail("Cannot bring full reading into view")
        throw NSError(domain: "WatchRoundingJourney", code: 1)
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
