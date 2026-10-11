#if DEBUG
import XCTest

/// Real selected-store persistence with a single provider 101→111 success.
/// These cases pay neither feed connectivity nor physical VoiceOver acceptance.
final class PickerAliasJourneyTests: XCTestCase {
    @MainActor
    func testResolvedAliasRetainsReadingOfflineAndAfterRestart() throws {
        try aliasJourney(largeText: false)
        print("WATCH_UI_PICKER_ALIAS_STANDARD=PASS")
    }

    @MainActor
    func testResolvedAliasRetainsReadingAtAccessibilitySize() throws {
        try aliasJourney(largeText: true)
        print("WATCH_UI_PICKER_ALIAS_LARGE=PASS")
    }

    /// Focused completion of the control not reached by the retained standard run.
    @MainActor
    func testUnprovenSameNameChoiceDoesNotReuseSavedReading() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        try restoreAliasOffline(in: app, largeText: false)
        try openPicker(in: app)
        let first = app.buttons["watch.pick.101"]
        let second = app.buttons["watch.pick.202"]
        try assertSelectedRows(first: first, second: second, largeText: false, in: app)
        try assertUnprovenChoice(second, in: app)
        print("WATCH_UI_PICKER_ALIAS_UNPROVEN_CONTROL=PASS")
    }

    /// Only the missing saved-banner pixels; paid named-reading captures stay retained.
    @MainActor
    func testRestoredSavedBannerIsReadableAtAccessibilitySize() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        try restoreAliasOffline(in: app, largeText: true)
        try openPicker(in: app)
        let first = app.buttons["watch.pick.101"]
        try assertSelectedRows(first: first, second: app.buttons["watch.pick.202"], largeText: true, in: app)
        try reveal(first, in: app)
        first.tap()
        try assertState(saved: true, in: app)
        try captureSavedBanner(in: app, name: "Complete saved offline banner after alias reselect - accessibility5")
        print("WATCH_UI_PICKER_ALIAS_SAVED_BANNER_LARGE=PASS")
    }

    @MainActor
    private func restoreAliasOffline(in app: XCUIApplication, largeText: Bool) throws {
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_PICKER_ALIAS": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0"]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        _ = try assertReading(in: app) // Establish the real production snapshot once.
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        try assertState(saved: true, in: app)
        _ = try assertReading(in: app)
    }

    @MainActor
    private func assertUnprovenChoice(_ second: XCUIElement, in app: XCUIApplication) throws {
        XCTAssertFalse(second.isSelected)
        try reveal(second, in: app)
        second.tap()
        let unavailable = app.staticTexts["Your selection is retained. Refresh to try again."]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 15))
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-score"].firstMatch.exists,
            "Unproven 202 must not display 111's reading even when names match")
        try captureElement(unavailable, in: app, name: "Unproven same-name202 clears old reading offline")
    }

    @MainActor
    private func aliasJourney(largeText: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        let size = largeText ? "accessibility5" : "standard"
        let suite = UUID().uuidString
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": suite, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_PICKER_ALIAS": "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": largeText ? "1" : "0"]
        app.launch()
        let first = app.buttons["watch.pick.101"]
        let second = app.buttons["watch.pick.202"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        XCTAssertFalse(first.isSelected)
        try reveal(first, in: app)
        first.tap()
        let originalLabels = try assertReading(in: app)
        // This fixture can only produce these contents through its 101→111 success.
        // All subsequent detail calls fail; no second success can hide lost state.
        let refresh = app.buttons["Refresh"].firstMatch
        XCTAssertTrue(refresh.waitForExistence(timeout: 15))
        try reveal(refresh, in: app)
        refresh.tap()
        try assertState(saved: false, in: app)
        try openPicker(in: app)
        try assertSelectedRows(first: first, second: second, largeText: largeText, in: app)
        try captureElement(first, in: app, name: "Resolved101 row selected before offline reselect - \(size)")
        first.tap()
        XCTAssertEqual(try assertReading(in: app), originalLabels,
            "Offline alias tap retains named scores, probability and original independent ages")
        XCTAssertFalse(app.buttons["watch.picker-cancel"].firstMatch.exists)
        try assertState(saved: false, in: app)

        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch() // Same suite; no fixture snapshot writes or default reset.
        try assertState(saved: true, in: app)
        XCTAssertEqual(try assertReading(in: app), originalLabels,
            "Offline restart must restore the real production snapshot")
        try openPicker(in: app)
        try assertSelectedRows(first: first, second: second, largeText: largeText, in: app)
        try captureElement(first, in: app, name: "Restored alias selected badge with full names - \(size)")
        first.tap()
        try assertState(saved: true, in: app)
        XCTAssertEqual(try assertReading(in: app), originalLabels)
        for (element, name) in readingElements(in: app) {
            try captureElement(element, in: app, name: "Restored offline alias retains \(name) - \(size)")
        }
        try captureSavedBanner(in: app, name: "Complete saved offline banner after alias reselect - \(size)")

        // One standard-only negative control; identical names must not confer identity.
        if !largeText {
            try openPicker(in: app)
            try assertUnprovenChoice(second, in: app)
        }
        let receipt = XCTAttachment(string: "suite=\(suite)\nsize=\(size)\nfixture_request=101\nfixture_canonical=111\nrestart_reset=0\nrestart_offline=1\nreading_labels=\(originalLabels)")
        receipt.name = "Alias journey fixture and observed-label receipt"
        receipt.lifetime = .keepAlways
        add(receipt)
    }

    @MainActor
    private func readingElements(in app: XCUIApplication) -> [(XCUIElement, String)] {
        [
            (app.descendants(matching: .any)["watch.away-score"].firstMatch, "Dodgers score2"),
            (app.descendants(matching: .any)["watch.home-score"].firstMatch, "Giants score3"),
            (app.descendants(matching: .any)["watch.home-probability"].firstMatch, "Giants64percent"),
            (app.staticTexts["Score observed 1 hour ago"].firstMatch, "original score age1hour"),
            (app.staticTexts["Probability observed 3 hours ago"].firstMatch, "original probability age3hours")
        ]
    }

    @MainActor
    private func assertReading(in app: XCUIApplication) throws -> [String] {
        let elements = readingElements(in: app)
        let expected = ["Los Angeles Dodgers, score 2", "San Francisco Giants, score 3",
            "San Francisco Giants win probability, 64%", "Score observed 1 hour ago",
            "Probability observed 3 hours ago"]
        for ((element, _), label) in zip(elements, expected) {
            XCTAssertTrue(element.waitForExistence(timeout: 15))
            XCTAssertEqual(element.label, label)
        }
        return elements.map { $0.0.label }
    }

    @MainActor
    private func assertState(saved: Bool, in app: XCUIApplication) throws {
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let offline = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label CONTAINS %@", "Offline."), object: state)
        XCTAssertEqual(XCTWaiter.wait(for: [offline], timeout: 15), .completed)
        XCTAssertEqual(state.label.contains("Saved reading. Refresh to confirm."), saved)
        XCTAssertTrue(state.label.contains("Live"))
    }

    @MainActor
    private func assertSelectedRows(first: XCUIElement, second: XCUIElement, largeText: Bool, in app: XCUIApplication) throws {
        let heading = app.staticTexts["watch.picker-heading"]
        XCTAssertTrue(heading.waitForExistence(timeout: 15))
        let textSize = try XCTUnwrap(heading.value as? String)
        XCTAssertFalse(textSize.isEmpty)
        if largeText { XCTAssertEqual(textSize, "accessibility5") }
        else { XCTAssertFalse(textSize.hasPrefix("accessibility")) }
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "watch.pick.")).allElementsBoundByIndex
        XCTAssertEqual(rows.map { $0.identifier }, ["watch.pick.101", "watch.pick.202"])
        XCTAssertTrue(first.isSelected, "The provider-proven original request owns the selected trait")
        XCTAssertFalse(second.isSelected, "Same names are not identity proof")
        XCTAssertEqual(first.label, "Los Angeles Dodgers at San Francisco Giants. Live. Your game")
        XCTAssertEqual(second.label, "Los Angeles Dodgers at San Francisco Giants. Scheduled")
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
            throw NSError(domain: "WatchPickerAliasJourney", code: 4)
        }
        return visible[0]
    }

    @MainActor
    private func viewport(_ scroll: XCUIElement, appFrame: CGRect) throws -> CGRect {
        let bounds = scroll.frame.intersection(appFrame)
        guard !bounds.isNull && !bounds.isEmpty && bounds.minX.isFinite && bounds.minY.isFinite && bounds.maxX.isFinite && bounds.maxY.isFinite else {
            XCTFail("Expected a finite nonempty scroll viewport")
            throw NSError(domain: "WatchPickerAliasJourney", code: 5)
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
        throw NSError(domain: "WatchPickerAliasJourney", code: 1)
    }

    @MainActor
    private func captureSavedBanner(in app: XCUIApplication, name: String) throws {
        try assertState(saved: true, in: app)
        let container = try scrollViewport(in: app)
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let identity = app.descendants(matching: .any)["watch.home-identity"].firstMatch
        let savedNote = app.descendants(matching: .any)["watch.saved-update"].firstMatch
        let recovery = app.descendants(matching: .any)["watch.update-explanation"].firstMatch
        XCTAssertTrue(identity.exists && savedNote.exists && recovery.exists)
        XCTAssertEqual(identity.label, "San Francisco Giants")
        XCTAssertEqual(savedNote.label, "Last saved update")
        XCTAssertTrue(state.label.contains("Saved reading. Refresh to confirm."))
        XCTAssertTrue(state.label.contains("Offline."))
        XCTAssertTrue(recovery.label.hasPrefix("Offline."))
        // The accepted page begins with the home identity. Saved context is
        // below the scores and receives its own complete captures after top proof.
        var previousIdentityY: CGFloat?
        var stableTopSamples = 0
        var samples: [String] = []
        for attempt in 0..<24 {
            let appFrame = app.frame
            var bounds = try viewport(container, appFrame: appFrame)
            let bars = app.navigationBars.allElementsBoundByIndex.filter { $0.exists && $0.frame.intersects(bounds) }
            if let chromeBottom = bars.map({ $0.frame.maxY }).max() {
                let top = max(bounds.minY, chromeBottom + 3)
                bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
            }
            guard !bounds.isNull, !bounds.isEmpty, bounds.height > 30,
                  bounds.minX.isFinite, bounds.maxX.isFinite,
                  bounds.minY.isFinite, bounds.maxY.isFinite else {
                XCTFail("Invalid unobscured saved-reading viewport")
                throw NSError(domain: "WatchPickerAliasJourney", code: 5)
            }
            let identityFrame = identity.frame
            let identityY = identityFrame.minY
            let beginning = CGRect(x: identityFrame.minX, y: identityFrame.minY,
                                   width: identityFrame.width, height: min(30, identityFrame.height))
            let finiteIdentity = !identityFrame.isNull && !identityFrame.isEmpty
                && identityFrame.minX.isFinite && identityFrame.minY.isFinite
                && identityFrame.maxX.isFinite && identityFrame.maxY.isFinite
            samples.append("attempt=\(attempt) identity=\(identityFrame) viewport=\(bounds)")
            if let previousIdentityY, abs(identityY - previousIdentityY) < 1,
               finiteIdentity, bounds.contains(beginning), identity.isHittable {
                stableTopSamples += 1
            } else {
                stableTopSamples = 0
            }
            if stableTopSamples == 2 {
                if !(state.value as? String ?? "").hasPrefix("accessibility") {
                    XCTAssertTrue(bounds.contains(identityFrame), "The full standard-size first identity must fit at natural top")
                }
                capture(app, name + " - first reading at stable natural top")
                let geometry = XCTAttachment(string: samples.joined(separator: "\n") + "\n" + app.debugDescription)
                geometry.name = name + " - top-boundary geometry and hierarchy"
                geometry.lifetime = .keepAlways
                add(geometry)
                try captureElement(identity, in: app, name: name + " - complete first identity")
                try captureElement(state, in: app, name: name + " - complete saved state")
                try captureElement(savedNote, in: app, name: name + " - complete saved note")
                try captureElement(recovery, in: app, name: name + " - complete offline recovery")
                return
            }
            previousIdentityY = identityY
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                dx: bounds.midX - appFrame.minX, dy: bounds.minY + bounds.height * 0.20 - appFrame.minY))
            let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * 0.55))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        capture(app, name + " - failed natural-top normalization")
        let failure = XCTAttachment(string: samples.joined(separator: "\n") + "\n" + app.debugDescription)
        failure.name = name + " - failed geometry and hierarchy"
        failure.lifetime = .keepAlways
        add(failure)
        XCTFail("Cannot establish the stable natural top for complete saved-banner capture")
        throw NSError(domain: "WatchPickerAliasJourney", code: 6)
    }

    @MainActor
    private func captureElement(_ row: XCUIElement, in app: XCUIApplication, name: String) throws {
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
            XCTFail("Cannot show the beginning of the complete named element")
            throw NSError(domain: "WatchPickerAliasJourney", code: 2)
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
                capture(app, name + (atBottom ? " - bottom" : " - overlapping continuation"))
                coveredEnd = visibleEnd
                if atBottom { return }
            }
            scroll(bounds: bounds, appFrame: appFrame, towardTop: false, in: app)
        }
        XCTFail("Cannot show the end of the complete element")
        throw NSError(domain: "WatchPickerAliasJourney", code: 3)
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
