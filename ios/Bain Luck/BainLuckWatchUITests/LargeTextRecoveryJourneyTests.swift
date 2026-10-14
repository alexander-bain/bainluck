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
        let more = app.buttons["watch.more-actions"]
        try reveal(more, in: app)
        XCTAssertEqual(more.value as? String, "Collapsed")
        more.tap()
        XCTAssertEqual(more.value as? String, "Expanded")
        let help = app.buttons["watch.continue-on-phone"]
        try reveal(help, in: app)
        capture(app, "Largest text reachable Continue on iPhone control")
        help.tap()
        let dismissHelp = app.buttons["OK"]
        XCTAssertTrue(dismissHelp.waitForExistence(timeout: 15))
        capture(app, "Continue on iPhone explanation without delivery claim")
        dismissHelp.tap()
        let change = app.buttons["watch.choose-another"]
        _ = try revealChange(change, in: app)
        capture(app, "Largest text reachable change control")
        change.tap()
        try expandPickerDetails(in: app)
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertEqual(heading.value as? String, "accessibility5", "The sheet itself must receive the layout-stress size")
        try reveal(heading, in: app)
        capture(app, "Verified largest text sheet heading")
        try reveal(error, in: app)
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
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
        try expandPickerDetails(in: app)
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
        try reveal(heading, in: app)
        try reveal(error, in: app)
        let refresh = app.buttons["Refresh games"]
        expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: refresh)
        waitForExpectations(timeout: 15)
        try reveal(refresh, in: app)
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
    private func changeViewport(in app: XCUIApplication, appFrame: CGRect) throws -> CGRect {
        let visible = app.scrollViews.allElementsBoundByIndex.compactMap { scroll -> CGRect? in
            let bounds = scroll.frame.intersection(appFrame)
            guard scroll.isHittable && !bounds.isNull && !bounds.isEmpty
                && bounds.minX.isFinite && bounds.maxX.isFinite
                && bounds.minY.isFinite && bounds.maxY.isFinite else { return nil }
            return bounds
        }
        guard visible.count == 1 else {
            XCTFail("Expected one visible change scroll viewport")
            throw NSError(domain: "WatchLargeTextChangeViewport", code: 1)
        }
        var bounds = visible[0]
        let chromeBottom = app.navigationBars.allElementsBoundByIndex.compactMap { bar -> CGFloat? in
            guard bar.exists else { return nil }
            let frame = bar.frame
            return frame.intersects(bounds) ? frame.maxY : nil
        }.max()
        if let chromeBottom = chromeBottom {
            let top = max(bounds.minY, chromeBottom + 3)
            bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        }
        guard !bounds.isEmpty, !bounds.isNull, bounds.height > 30,
              bounds.minX.isFinite, bounds.maxX.isFinite,
              bounds.minY.isFinite, bounds.maxY.isFinite else {
            XCTFail("Invalid unobscured change viewport")
            throw NSError(domain: "WatchLargeTextChangeViewport", code: 2)
        }
        return bounds.insetBy(dx: 2, dy: 3)
    }

    @MainActor
    private func revealChange(_ change: XCUIElement, in app: XCUIApplication) throws -> CGRect {
        XCTAssertTrue(change.waitForExistence(timeout: 15))
        for _ in 0..<32 {
            let appFrame = app.frame
            let bounds = try changeViewport(in: app, appFrame: appFrame)
            let frame = change.frame
            if change.isHittable && bounds.contains(frame) { return bounds }
            let earlier = frame.minY < bounds.minY
            let distance = earlier ? bounds.minY - frame.minY : frame.maxY - bounds.maxY
            let fraction = min(0.50, max(0.15, distance / bounds.height))
            let origin = app.coordinate(withNormalizedOffset: .zero)
            let start = origin.withOffset(CGVector(dx: bounds.midX - appFrame.minX,
                dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - appFrame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? fraction : -fraction)))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, "Unreachable largest text control - \(change.identifier)")
        XCTFail("Cannot bring full change control below navigation chrome")
        throw NSError(domain: "WatchLargeTextChangeViewport", code: 3)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        for _ in 0..<32 {
            let appFrame = app.frame
            let frame = element.frame
            if element.isHittable && appFrame.contains(frame) { return }
            // Contained but not hittable in the upper half means under the navigation bar (the
            // Watch app has no bottom chrome); dragging it up again oscillated until the cap.
            let earlier = frame.minY < appFrame.minY || (appFrame.contains(frame) && frame.midY < appFrame.midY)
            // Size each drag to the remaining offset, as revealChange does; a fixed 15% step
            // spent most of the 3-minute allowance on drags at accessibility5.
            let distance = earlier ? appFrame.minY - frame.minY : frame.maxY - appFrame.maxY
            let fraction = min(0.50, max(0.15, distance / appFrame.height))
            let from: CGFloat = earlier ? 0.35 : 0.75
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: from))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: earlier ? from + fraction : from - fraction))
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
