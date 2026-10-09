#if DEBUG
import XCTest

/// Selected-row presentation only; fixtures do not pay physical VoiceOver acceptance.
final class PickerSelectedStateJourneyTests: XCTestCase {
    @MainActor
    func testSelectedGameIsMarkedInPickerAndCanChange() throws {
        try selectedPickerJourney(largeText: false)
        print("WATCH_UI_PICKER_SELECTED_STANDARD=PASS")
    }

    @MainActor
    func testSelectedGameIsMarkedAtAccessibilitySize() throws {
        try selectedPickerJourney(largeText: true)
        print("WATCH_UI_PICKER_SELECTED_LARGE=PASS")
    }

    @MainActor
    private func selectedPickerJourney(largeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0"]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        let second = app.buttons["watch.pick.202"]
        XCTAssertTrue(first.waitForExistence(timeout: 20) && second.exists)
        try assertPicker(first: first, second: second, selected: nil, largeText: largeText, in: app)
        try reveal(first, in: app)
        try captureRow(first, in: app, name: "Unselected picker has no Your game badge - \(largeText ? "accessibility5" : "standard")")
        first.tap()
        try assertGame("San Francisco Giants", in: app)

        try openPicker(in: app)
        try assertPicker(first: first, second: second, selected: 101, largeText: largeText, in: app)
        try reveal(first, in: app)
        try captureRow(first, in: app, name: "Selected Giants row checkmark and Your game - \(largeText ? "accessibility5" : "standard")")
        first.tap()
        try assertGame("San Francisco Giants", in: app)
        XCTAssertFalse(app.buttons["watch.picker-cancel"].firstMatch.exists, "Current selection tap returns to its game")

        try openPicker(in: app)
        try reveal(second, in: app)
        second.tap()
        try assertGame("Buffalo Bills", in: app)
        try openPicker(in: app)
        try assertPicker(first: first, second: second, selected: 202, largeText: largeText, in: app)
        try reveal(second, in: app)
        try captureRow(second, in: app, name: "Selected Bills row owns the badge after changing game - \(largeText ? "accessibility5" : "standard")")
    }

    @MainActor
    private func assertPicker(first: XCUIElement, second: XCUIElement, selected: Int?, largeText: Bool, in app: XCUIApplication) throws {
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertTrue(heading.waitForExistence(timeout: 15))
        let textSize = try XCTUnwrap(heading.value as? String)
        XCTAssertFalse(textSize.isEmpty)
        if largeText {
            XCTAssertEqual(textSize, "accessibility5", "The presented picker must receive the injected text size")
        } else {
            XCTAssertFalse(textSize.hasPrefix("accessibility"), "Standard journey must retain a standard text size")
        }
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "watch.pick.")).allElementsBoundByIndex
        XCTAssertEqual(rows.map { $0.identifier }, ["watch.pick.101", "watch.pick.202"], "Selected decoration must preserve server order")
        for (row, id, name, state) in [
            (first, 101, "Los Angeles Dodgers at San Francisco Giants", "Live"),
            (second, 202, "Kansas City Chiefs at Buffalo Bills", "Scheduled")
        ] {
            let current = selected == id
            XCTAssertEqual(row.isSelected, current, "Selected accessibility trait follows canonical event ID")
            XCTAssertEqual(row.label, "\(name). \(state)" + (current ? ". Your game" : ""), "Full names and the current label are spoken once")
        }
    }

    @MainActor
    private func assertGame(_ team: String, in app: XCUIApplication) throws {
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let named = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label CONTAINS %@", team), object: probability)
        XCTAssertEqual(XCTWaiter.wait(for: [named], timeout: 15), .completed)
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
    private func scrollViewport(in app: XCUIApplication) throws -> XCUIElement {
        let appFrame = app.frame
        let visible = app.scrollViews.allElementsBoundByIndex.filter { scroll in
            let bounds = scroll.frame.intersection(appFrame)
            return !bounds.isNull && !bounds.isEmpty && bounds.minX.isFinite && bounds.minY.isFinite && bounds.maxX.isFinite && bounds.maxY.isFinite && scroll.isHittable
        }
        guard visible.count == 1 else {
            capture(app, "Missing or ambiguous selected picker viewport")
            XCTFail("Expected one visible scroll viewport")
            throw NSError(domain: "WatchPickerSelectedStateJourney", code: 4)
        }
        return visible[0]
    }

    @MainActor
    private func viewport(_ scroll: XCUIElement, appFrame: CGRect) throws -> CGRect {
        let bounds = scroll.frame.intersection(appFrame)
        guard !bounds.isNull && !bounds.isEmpty && bounds.minX.isFinite && bounds.minY.isFinite && bounds.maxX.isFinite && bounds.maxY.isFinite else {
            XCTFail("Expected a finite nonempty scroll viewport")
            throw NSError(domain: "WatchPickerSelectedStateJourney", code: 5)
        }
        return bounds
    }

    @MainActor
    private func scroll(bounds: CGRect, appFrame: CGRect, towardTop: Bool, in app: XCUIApplication) {
        let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: bounds.midX - appFrame.minX, dy: bounds.minY + bounds.height * 0.60 - appFrame.minY))
        let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (towardTop ? 0.20 : -0.20)))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        let container = try scrollViewport(in: app)
        for _ in 0..<24 {
            let appFrame = app.frame
            let bounds = try viewport(container, appFrame: appFrame)
            let frame = element.frame
            if element.isHittable && bounds.intersects(frame) { return }
            let earlier = frame.minY < bounds.minY
            let hiddenDistance = earlier ? bounds.minY - frame.minY : max(0, frame.maxY - bounds.maxY)
            let distance = min(0.55, max(0.15, (hiddenDistance + 8) / bounds.height))
            let startY: CGFloat = earlier ? 0.20 : 0.80
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: bounds.midX - appFrame.minX, dy: bounds.minY + bounds.height * startY - appFrame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? distance : -distance)))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, "Unreachable selected picker control - \(element.identifier)")
        XCTFail("Cannot bring the picker control into tappable view")
        throw NSError(domain: "WatchPickerSelectedStateJourney", code: 1)
    }

    @MainActor
    private func captureRow(_ row: XCUIElement, in app: XCUIApplication, name: String) throws {
        // Oversized accessibility rows can remain complete through scrolling;
        // capture overlapping views through the bottom instead of demanding one-frame fit.
        let container = try scrollViewport(in: app)
        var topCoverage: CGFloat?
        for _ in 0..<24 {
            let appFrame = app.frame
            let bounds = try viewport(container, appFrame: appFrame)
            let frame = row.frame
            if row.isHittable && frame.minY >= bounds.minY && frame.minY <= bounds.midY {
                topCoverage = min(frame.height, bounds.maxY - frame.minY)
                capture(app, name + " - top")
                if bounds.contains(frame) { return }
                break
            }
            scroll(bounds: bounds, appFrame: appFrame, towardTop: frame.minY < bounds.minY, in: app)
        }
        guard var coveredEnd = topCoverage else {
            XCTFail("Cannot show the beginning of the complete named picker row")
            throw NSError(domain: "WatchPickerSelectedStateJourney", code: 2)
        }
        for _ in 0..<24 {
            let appFrame = app.frame
            let bounds = try viewport(container, appFrame: appFrame)
            let frame = row.frame
            let visibleStart = max(0, bounds.minY - frame.minY)
            let visibleEnd = min(frame.height, bounds.maxY - frame.minY)
            if row.isHittable && bounds.intersects(frame) && visibleEnd > coveredEnd {
                XCTAssertLessThanOrEqual(visibleStart, coveredEnd + 1, "Retained views must overlap to cover the entire row")
                let atBottom = frame.maxY <= bounds.maxY
                capture(app, name + (atBottom ? " - bottom including state and selected badge" : " - overlapping continuation"))
                coveredEnd = visibleEnd
                if atBottom { return }
            }
            scroll(bounds: bounds, appFrame: appFrame, towardTop: false, in: app)
        }
        XCTFail("Cannot show the end of the complete picker row")
        throw NSError(domain: "WatchPickerSelectedStateJourney", code: 3)
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
