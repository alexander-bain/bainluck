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
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
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
    func testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        for (scenario, message) in [
            ("offline", "Offline. Connect to the internet, then refresh games."),
            ("interrupted", "Connection interrupted. Refresh games to try again."),
            ("timeout", "Connection timed out. Refresh games to try again.")
        ] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
                "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
                "BAINLUCK_WATCH_UI_PICKER_NETWORK": scenario]
            app.launch()
            let first = app.buttons["watch.pick.101"]
            XCTAssertTrue(first.waitForExistence(timeout: 20))
            try reveal(first, in: app)
            first.tap()
            let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
            XCTAssertTrue(probability.waitForExistence(timeout: 15) && probability.label.contains("San Francisco Giants"))
            try openPicker(in: app)
            let error = app.staticTexts["watch.picker-error"]
            XCTAssertTrue(error.waitForExistence(timeout: 15))
            XCTAssertEqual(error.label, message)
            try reveal(error, in: app)
            capture(app, "Picker \(scenario) complete recovery guidance")
            let retained = app.buttons["watch.pick.202"]
            XCTAssertTrue(retained.exists && retained.label.contains("Kansas City Chiefs") && retained.label.contains("Buffalo Bills"))
            XCTAssertTrue(app.staticTexts["Showing the previously received list."].exists)
            try reveal(retained, in: app)
            capture(app, "Picker \(scenario) retains named previously received option")
            let refresh = app.buttons["Refresh games"]
            try reveal(refresh, in: app)
            XCTAssertTrue(refresh.isEnabled)
            refresh.tap()
            expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: error)
            waitForExpectations(timeout: 15)
            XCTAssertFalse(app.staticTexts["Showing the previously received list."].exists)
            XCTAssertTrue(retained.waitForExistence(timeout: 15))
            try reveal(retained, in: app)
            retained.tap()
            XCTAssertTrue(probability.waitForExistence(timeout: 15))
            expectation(for: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "Buffalo Bills", "55%"), evaluatedWith: probability)
            waitForExpectations(timeout: 15)
            try reveal(probability, in: app)
            capture(app, "Picker \(scenario) successful refresh selects named Bills reading")
            print("WATCH_UI_PICKER_NETWORK_\(scenario.uppercased())=PASS")
            app.terminate()
        }
    }

    @MainActor
    private func openPicker(in app: XCUIApplication) throws {
        let change = app.buttons["watch.choose-another"]
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        try reveal(change, in: app)
        change.tap()
        XCTAssertTrue(app.buttons["watch.picker-cancel"].firstMatch.waitForExistence(timeout: 15))
    }

    @MainActor
    private func returnToGame(in app: XCUIApplication) throws {
        let cancel = app.buttons["watch.picker-cancel"].firstMatch
        try reveal(cancel, in: app)
        capture(app, "Reachable explicit return to selected game")
        cancel.tap()
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: cancel)
        waitForExpectations(timeout: 15)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        let initialAppFrame = app.frame
        let initialFrame = element.frame
        if element.isHittable && initialAppFrame.contains(initialFrame) { return }
        let visible = app.scrollViews.allElementsBoundByIndex.filter { scroll in
            let bounds = scroll.frame.intersection(initialAppFrame)
            return !bounds.isNull && !bounds.isEmpty && bounds.minX.isFinite && bounds.minY.isFinite && bounds.maxX.isFinite && bounds.maxY.isFinite && scroll.isHittable
        }
        guard visible.count == 1 else {
            capture(app, "Missing or ambiguous picker return viewport")
            XCTFail("Expected one visible scroll viewport")
            throw NSError(domain: "WatchPickerReturnJourney", code: 2)
        }
        let container = visible[0]
        for _ in 0..<24 {
            let appFrame = app.frame
            let bounds = container.frame.intersection(appFrame)
            guard !bounds.isNull && !bounds.isEmpty && bounds.minX.isFinite && bounds.minY.isFinite && bounds.maxX.isFinite && bounds.maxY.isFinite else {
                XCTFail("Expected a finite nonempty scroll viewport")
                throw NSError(domain: "WatchPickerReturnJourney", code: 3)
            }
            let frame = element.frame
            // Toolbar return controls lie outside the content scroll viewport.
            // Retain complete app-frame visibility plus actual hittability.
            if element.isHittable && appFrame.contains(frame) { return }
            let earlier = frame.minY < bounds.minY
            let hiddenDistance = earlier ? bounds.minY - frame.minY : max(0, frame.maxY - bounds.maxY)
            let distance = min(0.55, max(0.15, (hiddenDistance + 8) / bounds.height))
            let startY: CGFloat = earlier ? 0.20 : 0.80
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: bounds.midX - appFrame.minX, dy: bounds.minY + bounds.height * startY - appFrame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? distance : -distance)))
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
