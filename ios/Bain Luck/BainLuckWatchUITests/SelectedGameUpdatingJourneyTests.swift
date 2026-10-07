#if DEBUG
import XCTest

final class SelectedGameUpdatingJourneyTests: XCTestCase {
    @MainActor func testUpdatingIsVisibleUntilRequestFinishes() throws {
        try journey(largeText: false)
        print("WATCH_UI_GAME_UPDATING_STANDARD=PASS")
    }

    @MainActor func testUpdatingIsVisibleAtAccessibilitySize() throws {
        try journey(largeText: true)
        print("WATCH_UI_GAME_UPDATING_LARGE=PASS")
    }

    @MainActor private func journey(largeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_UPDATING": "1", "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0"]
        app.launch()
        let choice = app.buttons["watch.pick.101"]
        XCTAssertTrue(choice.waitForExistence(timeout: 20))
        try reveal(choice, in: app)
        choice.tap()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        let clocks = try XCTUnwrap(state.value as? String)
        let metadata = clocks.split(separator: "|")
        XCTAssertEqual(metadata.count, 4)
        XCTAssertEqual(metadata[1], "101")
        XCTAssertNotNil(Double(metadata[2]))
        XCTAssertNotNil(Double(metadata[3]))
        if largeText { XCTAssertEqual(metadata[0], "accessibility5") }
        else { XCTAssertFalse(metadata[0].hasPrefix("accessibility")) }
        let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
        let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
        XCTAssertEqual(home.label, "San Francisco Giants, score 3")
        XCTAssertEqual(away.label, "Los Angeles Dodgers, score 2")
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        let originalState = state.label
        let updating = app.staticTexts["watch.game-updating"]
        XCTAssertFalse(updating.exists)
        let refresh = app.buttons["Refresh"].firstMatch
        try reveal(refresh, in: app)
        refresh.tap()
        XCTAssertTrue(updating.waitForExistence(timeout: 10))
        try reveal(updating, in: app)
        XCTAssertEqual(updating.label, "Updating…")
        capture(app, "Updating near selected game state - \(metadata[0])")
        XCTAssertEqual(state.value as? String, clocks, "In-flight fetch cannot advance producer clocks")
        XCTAssertEqual(state.label, originalState)
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertEqual(home.label, "San Francisco Giants, score 3")
        XCTAssertEqual(away.label, "Los Angeles Dodgers, score 2")
        try reveal(away, in: app)
        try captureRow(away, in: app, name: "Updating retained named away score - \(metadata[0])")
        try reveal(home, in: app)
        try captureRow(home, in: app, name: "Updating retained named home score - \(metadata[0])")
        XCTAssertTrue(updating.exists, "Captures must show an actual in-flight request")
        let completed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: updating)
        XCTAssertEqual(XCTWaiter.wait(for: [completed], timeout: 90), .completed)
        XCTAssertEqual(state.value as? String, clocks, "Same producer payload must retain raw clocks after completion")
        XCTAssertEqual(state.label, originalState)
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertEqual(home.label, "San Francisco Giants, score 3")
        XCTAssertEqual(away.label, "Los Angeles Dodgers, score 2")
        try reveal(state, in: app)
        capture(app, "Request finished same selected state and clocks - \(metadata[0])")
        try reveal(home, in: app)
        try captureRow(home, in: app, name: "Request finished same named score - \(metadata[0])")
        // This is within the store's unchanged 30-second post-completion wait.
        // Poll the actual view state; do not infer completion from the delay fixture.
        let premature = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true"), object: updating)
        XCTAssertEqual(XCTWaiter.wait(for: [premature], timeout: 2), .timedOut)
        XCTAssertEqual(state.value as? String, clocks)
    }

    @MainActor
    private func viewport(for element: XCUIElement, in app: XCUIApplication) -> CGRect {
        let scroll = app.scrollViews.firstMatch
        return scroll.exists ? scroll.frame.intersection(app.frame) : app.frame
    }

    @MainActor
    private func scroll(_ element: XCUIElement, towardTop: Bool, in app: XCUIApplication) {
        let bounds = viewport(for: element, in: app)
        let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: bounds.midX - app.frame.minX, dy: bounds.minY + bounds.height * 0.60 - app.frame.minY))
        let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (towardTop ? 0.20 : -0.20)))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
    }

    @MainActor
    private func captureRow(_ row: XCUIElement, in app: XCUIApplication, name: String) throws {
        // Oversized accessibility rows can remain complete through scrolling;
        // capture overlapping views through the bottom instead of demanding one-frame fit.
        var topCoverage: CGFloat?
        for _ in 0..<24 {
            let bounds = viewport(for: row, in: app)
            let frame = row.frame
            if row.isHittable && frame.minY >= bounds.minY && frame.minY <= bounds.midY {
                topCoverage = min(frame.height, bounds.maxY - frame.minY)
                capture(app, name + " - top")
                if bounds.contains(frame) { return }
                break
            }
            scroll(row, towardTop: frame.minY < bounds.minY, in: app)
        }
        guard var coveredEnd = topCoverage else {
            XCTFail("Cannot show the beginning of the complete named score row")
            throw NSError(domain: "WatchUpdatingJourney", code: 2)
        }
        for _ in 0..<24 {
            let bounds = viewport(for: row, in: app)
            let frame = row.frame
            let visibleStart = max(0, bounds.minY - frame.minY)
            let visibleEnd = min(frame.height, bounds.maxY - frame.minY)
            if row.isHittable && bounds.intersects(frame) && visibleEnd > coveredEnd {
                XCTAssertLessThanOrEqual(visibleStart, coveredEnd + 1, "Retained views must overlap to cover the entire row")
                let atBottom = frame.maxY <= bounds.maxY
                capture(app, name + (atBottom ? " - bottom including full name and score" : " - overlapping continuation"))
                coveredEnd = visibleEnd
                if atBottom { return }
            }
            scroll(row, towardTop: false, in: app)
        }
        XCTFail("Cannot show the end of the complete score row")
        throw NSError(domain: "WatchUpdatingJourney", code: 3)
    }

    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) throws {
        for _ in 0..<24 {
            let bounds = app.scrollViews.firstMatch.exists
                ? app.scrollViews.firstMatch.frame.intersection(app.frame) : app.frame
            if element.isHittable && bounds.intersects(element.frame) { return }
            // A label under the navigation overlay can still lie inside the
            // scroll frame. Move it toward the viewport center; comparing only
            // minY to the screen edge oscillates around the obscured top edge.
            let upward = element.frame.midY < bounds.midY
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(
                CGVector(dx: bounds.midX - app.frame.minX, dy: bounds.minY + bounds.height * 0.60 - app.frame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (upward ? 0.20 : -0.20)))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)
        }
        capture(app, "Unreachable updating journey control - \(element.identifier)")
        XCTFail("Cannot reveal \(element.identifier) in bounded viewport")
        throw NSError(domain: "WatchUpdatingJourney", code: 1)
    }

    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
#endif
