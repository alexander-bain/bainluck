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
        try expandPickerDetails(in: app)
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15), "Offline picker must explain its retry recovery")
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
        try reveal(heading, in: app)
        try reveal(error, in: app)
        expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: refresh)
        waitForExpectations(timeout: 15)
        _ = try revealRefresh(refresh, in: app)
    }

    @MainActor
    private func expandPickerDetails(in app: XCUIApplication) throws {
        let details = app.buttons["watch.picker-info"]
        XCTAssertTrue(details.waitForExistence(timeout: 15))
        XCTAssertEqual(details.label, "About this list")
        try reveal(details, in: app)
        if details.value as? String != "Expanded" {
            XCTAssertEqual(details.value as? String, "Collapsed")
            details.tap()
        }
        XCTAssertEqual(details.value as? String, "Expanded")
    }

    @MainActor
    private func refreshViewport(in app: XCUIApplication) throws -> CGRect {
        let visible = app.scrollViews.allElementsBoundByIndex.filter {
            let bounds = $0.frame.intersection(app.frame)
            return $0.isHittable && !bounds.isNull && !bounds.isEmpty
                && bounds.minX.isFinite && bounds.maxX.isFinite
                && bounds.minY.isFinite && bounds.maxY.isFinite
        }
        guard visible.count == 1 else {
            XCTFail("Expected one visible refresh scroll viewport")
            throw NSError(domain: "WatchPickerRefreshViewport", code: 1)
        }
        var bounds = visible[0].frame.intersection(app.frame)
        let bars = app.navigationBars.allElementsBoundByIndex.filter {
            $0.exists && $0.frame.intersects(bounds)
        }
        if let chromeBottom = bars.map({ $0.frame.maxY }).max() {
            let top = max(bounds.minY, chromeBottom + 3)
            bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        }
        guard !bounds.isEmpty, !bounds.isNull, bounds.height > 30,
              bounds.minX.isFinite, bounds.maxX.isFinite,
              bounds.minY.isFinite, bounds.maxY.isFinite else {
            XCTFail("Invalid unobscured refresh viewport")
            throw NSError(domain: "WatchPickerRefreshViewport", code: 2)
        }
        return bounds.insetBy(dx: 2, dy: 3)
    }

    @MainActor
    private func revealRefresh(_ refresh: XCUIElement, in app: XCUIApplication) throws -> CGRect {
        for _ in 0..<24 {
            let bounds = try refreshViewport(in: app)
            let frame = refresh.frame
            if refresh.isHittable && bounds.contains(frame) { return bounds }
            let earlier = frame.minY < bounds.minY
            let distance = earlier ? bounds.minY - frame.minY : frame.maxY - bounds.maxY
            let fraction = min(0.50, max(0.15, distance / bounds.height))
            let origin = app.coordinate(withNormalizedOffset: .zero)
            let start = origin.withOffset(CGVector(dx: bounds.midX - app.frame.minX,
                dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - app.frame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? fraction : -fraction)))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)
        }
        XCTFail("Cannot bring full refresh control below navigation chrome")
        throw NSError(domain: "WatchPickerRefreshViewport", code: 3)
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
