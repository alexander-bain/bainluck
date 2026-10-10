#if DEBUG
import XCTest

/// Exercise the actual setting with the existing isolated fixture. WCSession
/// activation and event recording remain suppressed by WatchTelemetry in fixtures.
final class WatchDiagnosticsJourneyTests: XCTestCase {
    @MainActor func testConsentSettingPersistsAndRevokesAtStandardSize() throws {
        try journey(large: false)
        print("WATCH_UI_DIAGNOSTICS_STANDARD=PASS")
    }

    @MainActor func testConsentSettingPersistsAndRevokesAtAccessibilitySize() throws {
        try journey(large: true)
        print("WATCH_UI_DIAGNOSTICS_LARGE=PASS")
    }

    @MainActor private func journey(large: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        try openSettings(app)
        let choice = app.switches["watch.diagnostics.choice"].firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 10))
        XCTAssertEqual(choice.value as? String, "0", "No choice must default off")
        let form = app.descendants(matching: .any)["watch.diagnostics.form"].firstMatch
        let size = try XCTUnwrap(form.value as? String)
        if large { XCTAssertEqual(size, "accessibility5") }
        else { XCTAssertFalse(size.hasPrefix("accessibility")) }
        try captureContent(choice, app: app, name: "Watch diagnostics default off - \(size)")
        let disclosure = app.staticTexts["watch.diagnostics.disclosure"].firstMatch
        XCTAssertTrue(disclosure.label.contains("part of your iPhone’s analytics"))
        XCTAssertTrue(disclosure.label.contains("Your iPhone must also allow analytics"))
        try captureContent(disclosure, app: app, name: "Watch diagnostics consent disclosure - \(size)")
        let revocation = app.staticTexts["watch.diagnostics.revocation"].firstMatch
        try reveal(revocation, app: app)
        XCTAssertTrue(revocation.label.contains("clears unsent Watch diagnostics"))
        XCTAssertTrue(revocation.label.contains("Data already sent cannot be recalled here"))
        try captureContent(revocation, app: app, name: "Watch diagnostics revocation disclosure - \(size)")
        try reveal(choice, app: app, earlierWhenMissing: true)
        // watchOS exposes the whole row as a Switch; its center is the label.
        // Tap the visible trailing switch, then assert the actual persisted value.
        choice.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.5)).tap()
        XCTAssertEqual(choice.value as? String, "1")
        capture(app, "Watch diagnostics explicit on - \(size)")
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launch()
        try openSettings(app)
        XCTAssertEqual(choice.value as? String, "1", "Explicit choice must survive relaunch")
        try reveal(choice, app: app, earlierWhenMissing: true)
        // watchOS exposes the whole row as a Switch; its center is the label.
        // Tap the visible trailing switch, then assert the actual persisted value.
        choice.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.5)).tap()
        XCTAssertEqual(choice.value as? String, "0")
        capture(app, "Watch diagnostics revoked - \(size)")
        app.terminate()
        app.launch()
        try openSettings(app)
        XCTAssertEqual(choice.value as? String, "0", "Refusal must survive relaunch")
        capture(app, "Watch diagnostics refusal retained - \(size)")
    }

    @MainActor private func openSettings(_ app: XCUIApplication) throws {
        let link = app.buttons["watch.diagnostics"].firstMatch
        XCTAssertTrue(link.waitForExistence(timeout: 20))
        try reveal(link, app: app, maxScrollFraction: 0.55)
        link.tap()
        XCTAssertTrue(app.switches["watch.diagnostics.choice"].firstMatch.waitForExistence(timeout: 10))
    }

    @MainActor private func bounds(_ app: XCUIApplication) -> CGRect {
        let scroll = app.scrollViews.firstMatch
        let collection = app.collectionViews.firstMatch
        let content = scroll.exists ? scroll.frame : (collection.exists ? collection.frame : app.frame)
        let bar = app.navigationBars.firstMatch
        let top = bar.exists ? max(content.minY, bar.frame.maxY) : content.minY
        return CGRect(x: content.minX, y: top, width: content.width,
                      height: max(1, content.maxY - top)).intersection(app.frame)
    }

    @MainActor private func scroll(_ app: XCUIApplication, earlier: Bool, fraction: CGFloat = 0.20) {
        let box = bounds(app)
        // Longer moves only traverse distant content. Keep both endpoints
        // inside the viewport and retain the small step near the target.
        let startFraction: CGFloat = fraction > 0.20 ? (earlier ? 0.20 : 0.80) : 0.60
        let start = app.coordinate(withNormalizedOffset: .zero).withOffset(
            CGVector(dx: box.midX - app.frame.minX, dy: box.minY + box.height * startFraction - app.frame.minY))
        let end = start.withOffset(CGVector(dx: 0, dy: box.height * (earlier ? fraction : -fraction)))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)
    }

    @MainActor private func reveal(_ element: XCUIElement, app: XCUIApplication, earlierWhenMissing: Bool = false, maxScrollFraction: CGFloat = 0.20) throws {
        for _ in 0..<24 {
            let box = bounds(app)
            // Form lazily mounts offscreen rows; never read a missing row's frame or label.
            if !element.exists { scroll(app, earlier: earlierWhenMissing); continue }
            if element.isHittable && (box.contains(element.frame) ||
                (element.frame.height > box.height && box.intersects(element.frame))) { return }
            let distance = abs(element.frame.midY - box.midY) / box.height
            let fraction = min(maxScrollFraction, max(0.20, distance))
            scroll(app, earlier: element.frame.midY < box.midY, fraction: fraction)
        }
        capture(app, "Unreachable diagnostics element - \(element.identifier)")
        throw NSError(domain: "WatchDiagnostics", code: 1)
    }

    @MainActor private func captureContent(_ element: XCUIElement, app: XCUIApplication, name: String) throws {
        // Cover long accessibility paragraphs in overlapping captures, including
        // both ends; presence in the hierarchy alone is not visible disclosure.
        var covered: CGFloat?
        for _ in 0..<24 {
            let box = bounds(app), frame = element.frame
            if element.isHittable && frame.minY >= box.minY && frame.minY <= box.midY {
                covered = min(frame.height, box.maxY - frame.minY)
                capture(app, name + " - top")
                if box.contains(frame) { return }
                break
            }
            scroll(app, earlier: frame.minY < box.minY)
        }
        guard var end = covered else { throw NSError(domain: "WatchDiagnostics", code: 2) }
        for _ in 0..<24 {
            scroll(app, earlier: false)
            let box = bounds(app), frame = element.frame
            let start = max(0, box.minY - frame.minY), visibleEnd = min(frame.height, box.maxY - frame.minY)
            if element.isHittable && visibleEnd > end {
                XCTAssertLessThanOrEqual(start, end + 1, "Disclosure captures must overlap")
                capture(app, name + " - continuation")
                end = visibleEnd
                if frame.maxY <= box.maxY { return }
            }
        }
        throw NSError(domain: "WatchDiagnostics", code: 3)
    }

    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
#endif
