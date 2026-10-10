#if DEBUG
import XCTest

// BEGIN WATCH_HEADER_LABEL_TOPOLOGY
// XCUI retains a same-frame Text child under the explicitly labelled .ignore row.
// Count one semantic root; refuse a second root, extra descendants or shifted copies.
enum WatchHeaderLabelTopology {
    struct Child {
        let frame: CGRect
        let isStaticText: Bool
        let identifier: String
        let descendantCount: Int
    }

    static func isUnique(rootCount: Int, rootIsStaticText: Bool, labelCount: Int, rootFrame: CGRect,
                         children: [Child]) -> Bool {
        guard rootCount == 1, rootIsStaticText, children.count <= 1,
              labelCount == 1 + children.count,
              !rootFrame.isEmpty, !rootFrame.isNull,
              rootFrame.minX.isFinite, rootFrame.minY.isFinite,
              rootFrame.maxX.isFinite, rootFrame.maxY.isFinite else { return false }
        return children.allSatisfy {
            $0.isStaticText && $0.identifier.isEmpty && $0.descendantCount == 0 &&
            $0.frame == rootFrame
        }
    }
}
// END WATCH_HEADER_LABEL_TOPOLOGY

/// Local design journeys: actual store responses and mounted native controls.
/// They do not substitute for the eventual complete release or device gates.
final class PickerCurrentGameJourneyTests: XCTestCase {
    @MainActor
    func testPopulatedPickerShowsChoicesBeforeRefreshAtStandardSize() throws {
        try checkPopulatedPickerChoicesBeforeRefresh(large: false)
    }

    @MainActor
    func testPopulatedPickerShowsChoicesBeforeRefreshAtAccessibilitySize() throws {
        try checkPopulatedPickerChoicesBeforeRefresh(large: true)
    }

    @MainActor
    private func checkPopulatedPickerChoicesBeforeRefresh(large: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let first = app.buttons["watch.pick.101"]
        let second = app.buttons["watch.pick.202"]
        XCTAssertTrue(first.waitForExistence(timeout: 20) && second.exists)
        let refresh = app.buttons["watch.picker-refresh"]
        XCTAssertEqual(app.buttons.matching(identifier: "watch.picker-refresh").count, 1)
        let ordered = app.buttons.allElementsBoundByIndex.map { $0.identifier }.filter {
            ["watch.pick.101", "watch.pick.202", "watch.picker-refresh"].contains($0)
        }
        XCTAssertEqual(ordered, ["watch.pick.101", "watch.pick.202", "watch.picker-refresh"],
                       "Existing provider choices precede the single manual refresh action")
        XCTAssertEqual(first.label, "Los Angeles Dodgers at San Francisco Giants. Live")
        XCTAssertEqual(second.label, "Kansas City Chiefs at Buffalo Bills. Scheduled")
        let size = large ? "accessibility5" : "standard"
        capture(app, "Populated picker natural opening before refresh chrome - " + size)
        try captureComplete(first, in: app, name: "Complete first alternative before refresh - " + size)
        try captureComplete(second, in: app, name: "Complete second alternative before refresh - " + size)
        try reveal(refresh, in: app)
        XCTAssertTrue(refresh.isHittable)
        try captureComplete(refresh, in: app, name: "Manual refresh remains reachable after choices - " + size)
    }

    @MainActor
    func testCurrentCardReturnAffordanceAtStandardSize() throws {
        try checkCurrentCardReturnAffordance(large: false)
    }

    @MainActor
    func testCurrentCardReturnAffordanceAtAccessibilitySize() throws {
        try checkCurrentCardReturnAffordance(large: true)
    }

    @MainActor
    private func checkCurrentCardReturnAffordance(large: Bool) throws {
        let app = try launchCurrentGame(large: large)
        defer { app.terminate() }
        try openPicker(app)
        let current = try assertCurrent(app, id: 111)
        let size = large ? "accessibility5" : "standard"
        try captureComplete(current, in: app, name: "Current card with explicit Return - " + size)
        try reveal(current, in: app)
        let safeContent = try viewport(in: app)
        let visibleCard = current.frame.intersection(safeContent)
        XCTAssertTrue(current.isHittable && !visibleCard.isEmpty)
        let target = CGPoint(x: visibleCard.midX, y: visibleCard.midY)
        XCTAssertTrue(safeContent.contains(target) && current.frame.contains(target))
        let geometry = XCTAttachment(string: "Current card: \(current.frame); safe content: \(safeContent); tap: \(target)\n" + app.debugDescription)
        geometry.name = "Verified current-card return target - " + size
        geometry.lifetime = .keepAlways
        add(geometry)
        app.coordinate(withNormalizedOffset: .zero).withOffset(
            CGVector(dx: target.x - app.frame.minX, dy: target.y - app.frame.minY)).tap()
        XCTAssertFalse(app.buttons["watch.picker-cancel"].exists)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        try captureComplete(probability, in: app, name: "Return preserves named64 - " + size)
        print("WATCH_UI_CURRENT_RETURN_\(size.uppercased())=PASS")
    }

    @MainActor
    func testHandoffHelpExplainsPhoneGestureAtStandardSize() throws {
        try checkHandoffHelp(large: false)
    }

    @MainActor
    func testHandoffHelpExplainsPhoneGestureAtAccessibilitySize() throws {
        try checkHandoffHelp(large: true)
    }

    @MainActor
    private func checkHandoffHelp(large: Bool) throws {
        let app = try launchCurrentGame(large: large, nativeCategory: large
            ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL")
        defer { app.terminate() }
        let more = app.buttons["watch.more-actions"]
        try reveal(more, in: app)
        XCTAssertEqual(more.value as? String, "Collapsed")
        more.tap()
        XCTAssertEqual(more.value as? String, "Expanded")
        let help = app.buttons["watch.continue-on-phone"]
        try reveal(help, in: app)
        help.tap()
        let expected = "On your iPhone, swipe up from the bottom and pause midway. If it has a Home button, double-click Home.\n\nLook along the bottom for Bain Luck’s Handoff banner. Tap it if shown.\n\nBoth devices need Handoff on and the same Apple Account. The iPhone app must support Watch Handoff.\n\nIf no banner appears, your game stays selected here."
        let message = app.staticTexts.matching(NSPredicate(format: "label == %@", expected)).firstMatch
        XCTAssertTrue(message.waitForExistence(timeout: 15))
        XCTAssertEqual(message.label, expected)
        let nativeGeometry = XCTAttachment(string: "Message frame: \(message.frame); launch arguments: \(app.launchArguments)\n" + app.debugDescription)
        nativeGeometry.name = "Native Handoff text-size geometry - \(large ? "accessibility5" : "standard")"
        nativeGeometry.lifetime = .keepAlways
        add(nativeGeometry)
        let size = large ? "accessibility5" : "standard"
        capture(app, "Plain language Handoff help natural top - " + size)
        try captureComplete(message, in: app, name: "Complete Handoff gesture and requirements - " + size, handoffTable: true)
        let dismiss = app.buttons["OK"]
        try reveal(dismiss, in: app, handoffTable: true)
        capture(app, "Handoff help dismissal - " + size)
        dismiss.tap()
        XCTAssertFalse(message.exists)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        try captureComplete(probability, in: app, name: "Handoff dismissal retains current game - " + size)
        print("WATCH_UI_HANDOFF_HELP_\(size.uppercased())=PASS")
    }

    @MainActor
    func testFlatProbabilityFullLongNameAtStandardSize() throws {
        try checkFlatLongProbability(large: false)
    }

    @MainActor
    func testFlatProbabilityFullLongNameAtAccessibilitySize() throws {
        try checkFlatLongProbability(large: true)
    }

    @MainActor
    private func checkFlatLongProbability(large: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": "long-live",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, "Association Sportive de Saint-Étienne Full Canonical Name win probability, 64%")
        let size = large ? "accessibility5" : "standard"
        capture(app, "Shared full home identity and both scores natural top - " + size)
        try assertGameValueHierarchy(in: app, large: large,
            expectedHome: "Association Sportive de Saint-Étienne Full Canonical Name")
        let identity = app.descendants(matching: .any)["watch.home-identity"].firstMatch
        try captureComplete(identity, in: app, name: "Complete shared home identity - " + size)
        try captureComplete(probability, in: app, name: "Full untruncated long named probability - " + size)
        for (id, expected) in [("watch.away-score", "Club de Football Long Complete Opponent Name, score 12"),
                              ("watch.home-score", "Association Sportive de Saint-Étienne Full Canonical Name, score 0")] {
            let row = app.descendants(matching: .any)[id].firstMatch
            XCTAssertEqual(row.label, expected)
            try captureComplete(row, in: app, name: "Long forecast score association - " + id + " - " + size)
        }
        for label in ["Probability observed 3 hours ago", "Score observed 1 hour ago"] {
            try captureComplete(app.staticTexts[label], in: app, name: "Long forecast original clock - " + label + " - " + size)
        }
        print("WATCH_UI_FLAT_LONG_PROBABILITY=\(size),PASS")
    }

    @MainActor
    func testProbabilityArcZeroStaysZero() throws {
        try checkProbabilityArcEndpoint(scenario: "probability-zero", value: "0%")
    }

    @MainActor
    func testProbabilityArcHundredStaysHundred() throws {
        try checkProbabilityArcEndpoint(scenario: "probability-hundred", value: "100%")
    }

    @MainActor
    func testProbabilityArcZeroUsesNativeAccessibilityFallback() throws {
        try checkProbabilityArcEndpoint(scenario: "probability-zero", value: "0%", large: true)
    }

    @MainActor
    func testProbabilityArcHundredUsesNativeAccessibilityFallback() throws {
        try checkProbabilityArcEndpoint(scenario: "probability-hundred", value: "100%", large: true)
    }

    @MainActor
    private func checkProbabilityArcEndpoint(scenario: String, value: String, large: Bool = false) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, "Buffalo Bills win probability, " + value)
        try assertGameValueHierarchy(in: app, large: large, expectedHome: "Buffalo Bills")
        XCTAssertEqual(app.descendants(matching: .any).matching(NSPredicate(format:
            "identifier == %@", "watch.home-probability")).count, 1, "Decorative scale never adds another spoken probability")
        capture(app, "Static probability arc natural opening - " + value)
        try captureComplete(probability, in: app, name: "Static named scale numeric endpoint - " + value)
        try captureComplete(app.staticTexts["Probability observed 3 hours ago"], in: app,
                            name: "Original endpoint observation - " + value)
        XCTAssertEqual(app.descendants(matching: .any)["watch.home-score"].firstMatch.label,
                       "Buffalo Bills, score 0")
        print("WATCH_UI_PROBABILITY_ARC_ENDPOINT=\(value),PASS")
    }

    @MainActor
    func testProbabilityPosterAtStandardSize() throws {
        try checkProbabilityPoster(large: false)
    }

    @MainActor
    func testProbabilityPosterAtAccessibilitySize() throws {
        try checkProbabilityPoster(large: true)
    }

    @MainActor
    func testCompactStateLongClockUsesFullWidthFallbackAtStandardSize() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": "long-clock"]
        app.launch()
        defer { app.terminate() }
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        XCTAssertEqual(state.label, "Live Q4 12:34")
        try assertGameValueHierarchy(in: app, large: false, expectedClock: "Q4 12:34", expectedHome: "Buffalo Bills")
        capture(app, "Full score and live clock before update details - standard")
        try captureComplete(state, in: app, name: "Complete native live period and clock")
        let probabilityAge = app.staticTexts["Probability observed 3 hours ago"]
        XCTAssertEqual(probabilityAge.value as? String, "May be out of date")
        try captureComplete(probabilityAge, in: app, name: "Original probability age below full clock")
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "Buffalo Bills win probability, 64%")
        try captureComplete(probability, in: app, name: "Long clock retains full named probability")
        print("WATCH_UI_COMPACT_STATE_CLOCK_FALLBACK=PASS")
    }

    @MainActor
    private func assertGameValueHierarchy(in app: XCUIApplication, large: Bool, expectedSavedContext: Bool = false, expectedClock: String? = nil, expectedHome: String = "San Francisco Giants") throws {
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
        let scoreAge = app.staticTexts["Score observed 1 hour ago"]
        let probabilityAge = app.staticTexts["Probability observed 3 hours ago"]
        XCTAssertTrue(state.exists && probability.exists && away.exists && home.exists)
        XCTAssertFalse(app.staticTexts["watch.home-probability-unavailable"].exists)
        XCTAssertTrue(scoreAge.exists && probabilityAge.exists)
        XCTAssertTrue(state.label.hasSuffix(expectedClock.map { "Live " + $0 } ?? "Live"))
        // These callers explicitly use live fixtures with known probability and both scores.
        // Shared visible identity is a separate element and must be included in the fit gate.
        let identity = app.descendants(matching: .any)["watch.home-identity"].firstMatch
        XCTAssertTrue(identity.exists)
        XCTAssertEqual(identity.label, expectedHome)
        XCTAssertTrue(probability.label.hasPrefix(expectedHome + " win probability, "))
        XCTAssertTrue(home.label.hasPrefix(expectedHome + ", score "))
        XCTAssertGreaterThan(identity.frame.height, 0)
        XCTAssertLessThanOrEqual(identity.frame.maxY, min(probability.frame.minY, home.frame.minY))
        let homeReadingBottom = max(probability.frame.maxY, home.frame.maxY)
        let scoreBottom = max(away.frame.maxY, home.frame.maxY)
        XCTAssertLessThanOrEqual(homeReadingBottom, away.frame.minY)
        if large {
            XCTAssertLessThanOrEqual(probability.frame.maxY, home.frame.minY)
        } else {
            XCTAssertLessThanOrEqual(probability.frame.maxX, home.frame.minX)
        }
        if expectedSavedContext {
            XCTAssertTrue(state.label.contains("At last update: Live"))
            XCTAssertGreaterThanOrEqual(state.frame.minY, scoreBottom)
        } else {
            XCTAssertFalse(state.label.contains("At last update:"))
            XCTAssertLessThanOrEqual(homeReadingBottom, state.frame.minY)
            XCTAssertLessThanOrEqual(state.frame.maxY, away.frame.minY)
        }
        XCTAssertGreaterThanOrEqual(scoreAge.frame.minY, scoreBottom)
        XCTAssertGreaterThanOrEqual(probabilityAge.frame.minY, scoreBottom)
        if !large {
            XCTAssertTrue(try viewport(in: app).contains(identity.frame), "The complete visible home name must fit without scrolling")
            XCTAssertTrue(try viewport(in: app).contains(probability.frame))
            XCTAssertTrue(try viewport(in: app).contains(away.frame))
            XCTAssertTrue(try viewport(in: app).contains(home.frame))
            if !expectedSavedContext {
                XCTAssertTrue(try viewport(in: app).contains(state.frame))
            }
        }
        // Accessibility text uses its complete native size and may need scrolling.
        // Keep all independent-clock assertions below; banners no longer lead the page.
        XCTAssertEqual(scoreAge.value as? String, "May be out of date")
        XCTAssertEqual(probabilityAge.value as? String, "May be out of date")
    }

    @MainActor
    private func checkProbabilityPoster(large: Bool) throws {
        let app = try launchCurrentGame(large: large)
        defer { app.terminate() }
        let size = large ? "accessibility5" : "standard"
        try assertGameValueHierarchy(in: app, large: large)
        capture(app, "Named probability and useful score context natural opening - " + size)
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", "Probability observed 3 hours ago")).count, 1)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let score = app.descendants(matching: .any)["watch.away-score"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertLessThanOrEqual(probability.frame.maxY, score.frame.minY)
        XCTAssertLessThanOrEqual(probability.frame.width, app.frame.width)
        try captureComplete(probability, in: app, name: "Complete named probability poster - " + size)
        try captureComplete(app.staticTexts["Probability observed 3 hours ago"], in: app,
                            name: "Poster original probability age - " + size)
        for (id, expected) in [("watch.away-score", "Los Angeles Dodgers, score 2"),
                                ("watch.home-score", "San Francisco Giants, score 3")] {
            let row = app.descendants(matching: .any)[id].firstMatch
            XCTAssertEqual(row.label, expected)
            try captureComplete(row, in: app, name: "Reported score remains reachable - " + id + " - " + size)
        }
        try captureComplete(app.staticTexts["Score observed 1 hour ago"], in: app,
                            name: "Poster separate original score age - " + size)
        print("WATCH_UI_PROBABILITY_POSTER=\(size),PASS")
    }

    @MainActor
    func testProbabilityPosterSavedReadingKeepsOriginalClocks() throws {
        try checkSavedArc(large: true)
    }

    @MainActor
    func testProbabilityArcSavedAtStandardSize() throws {
        try checkSavedArc(large: false)
    }

    @MainActor
    private func checkSavedArc(large: Bool) throws {
        let app = try launchCurrentGame(large: large)
        defer { app.terminate() }
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let saved = XCTNSPredicateExpectation(predicate: NSPredicate(format:
            "exists == true AND label CONTAINS %@ AND label CONTAINS %@",
            "Saved reading. Refresh to confirm.", "Offline."), object: state)
        XCTAssertEqual(XCTWaiter.wait(for: [saved], timeout: 15), .completed)
        let size = large ? "accessibility5" : "standard"
        try assertGameValueHierarchy(in: app, large: large, expectedSavedContext: true)
        capture(app, "Saved game content first natural opening - " + size)
        let savedExplanation = app.staticTexts["watch.saved-update"]
        let connectionExplanation = app.staticTexts["watch.update-explanation"]
        XCTAssertEqual(savedExplanation.label, "Last saved update")
        XCTAssertTrue(connectionExplanation.label.hasPrefix("Offline."))
        XCTAssertGreaterThanOrEqual(savedExplanation.frame.minY, app.descendants(matching: .any)["watch.home-score"].firstMatch.frame.maxY)
        XCTAssertGreaterThanOrEqual(app.staticTexts["Probability observed 3 hours ago"].frame.minY, savedExplanation.frame.maxY)
        // Saved/connection truth is reachable below the game, not removed.
        XCTAssertTrue(state.label.contains("Saved reading. Refresh to confirm."))
        XCTAssertTrue(state.label.contains("Offline."))
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        try captureComplete(probability, in: app, name: "Saved poster named64 remains original")
        try captureComplete(savedExplanation, in: app, name: "Quiet last saved update below scores")
        try captureComplete(connectionExplanation, in: app, name: "Quiet connection action below scores")
        for label in ["Probability observed 3 hours ago", "Score observed 1 hour ago"] {
            XCTAssertEqual(app.staticTexts[label].value as? String, "May be out of date")
            try captureComplete(app.staticTexts[label], in: app, name: "Saved poster distinct clock - " + label)
        }
        print("WATCH_UI_PROBABILITY_POSTER_SAVED=PASS")
    }

    @MainActor
    func testScheduledMissingScoresShowMatchupAtStandardSize() throws {
        try checkScheduledMissingScores(large: false)
    }

    @MainActor
    func testScheduledMissingScoresShowMatchupAtAccessibilitySize() throws {
        try checkScheduledMissingScores(large: true)
    }

    @MainActor
    private func checkScheduledMissingScores(large: Bool) throws {
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": "scheduled-no-score",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let matchup = app.staticTexts["watch.scheduled-matchup"]
        XCTAssertTrue(matchup.waitForExistence(timeout: 15))
        XCTAssertEqual(matchup.label, "Kansas City Chiefs at Buffalo Bills")
        XCTAssertFalse(app.descendants(matching: .any)["watch.away-score"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-score"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["watch.score-heading"].exists)
        let start = app.staticTexts["watch.scheduled-start"]
        let suppliedStart = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-09T02:00:00Z"))
        XCTAssertEqual(start.label, "Scheduled " + suppliedStart.formatted(.dateTime.month().day().hour().minute()))
        XCTAssertFalse(app.descendants(matching: .any)["watch.game-state"].firstMatch.exists)
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", "Scheduled " + suppliedStart.formatted(.dateTime.month().day().hour().minute()))).count, 1)
        XCTAssertLessThanOrEqual(app.descendants(matching: .any)["watch.home-probability"].firstMatch.frame.maxY, start.frame.minY)
        XCTAssertLessThanOrEqual(start.frame.maxY, matchup.frame.minY)
        XCTAssertEqual(app.descendants(matching: .any)["watch.home-probability"].firstMatch.label,
                       "Buffalo Bills win probability, 64%")
        capture(app, "Scheduled missing score natural opening - \(large ? "AX" : "standard")")
        try captureComplete(matchup, in: app, name: "Full scheduled matchup without manufactured score")
        print("WATCH_UI_SCHEDULED_MISSING_SCORE=\(large ? "AX" : "standard"),PASS")
    }

    @MainActor
    func testScheduledStartBoundariesAtStandardSize() throws {
        try checkScheduledStartBoundaries(large: false)
    }

    @MainActor
    func testScheduledStartBoundariesAtAccessibilitySize() throws {
        try checkScheduledStartBoundaries(large: true)
    }

    @MainActor
    private func checkScheduledStartBoundaries(large: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        defer { app.terminate() }
        let suppliedStart = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-09T02:00:00Z"))
        let starts = "Scheduled " + suppliedStart.formatted(.dateTime.month().day().hour().minute())
        for (scenario, expectedHeader, expectedState, hasScores) in [
            ("scheduled-no-time", "Scheduled · time unavailable", "", false),
            ("scheduled-with-score", starts, "", true),
            ("unknown-status-with-start", "", "Mystery", true),
            ("missing-status-with-start", "", "Game state unavailable", true)
        ] {
            app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
                "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
                "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
            app.launch()
            let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
            XCTAssertTrue(probability.waitForExistence(timeout: 15))
            XCTAssertEqual(probability.label, "Buffalo Bills win probability, 64%")
            let header = app.staticTexts["watch.scheduled-start"]
            let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
            if expectedHeader.isEmpty {
                XCTAssertFalse(header.exists, "A timestamp cannot manufacture scheduled status")
                XCTAssertEqual(state.label, expectedState)
            } else {
                XCTAssertEqual(header.label, expectedHeader)
                XCTAssertFalse(state.exists)
                XCTAssertLessThanOrEqual(probability.frame.maxY, header.frame.minY)
                XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", expectedHeader)).count, 1)
            }
            let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
            let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
            if hasScores {
                XCTAssertEqual(away.label, "Kansas City Chiefs, score 12")
                XCTAssertEqual(home.label, "Buffalo Bills, score 0")
                if !expectedHeader.isEmpty { XCTAssertLessThanOrEqual(header.frame.maxY, away.frame.minY) }
                if !large {
                    for element in [probability, away, home] { XCTAssertTrue(try viewport(in: app).contains(element.frame)) }
                }
                XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
                for row in [away, home] { try captureComplete(row, in: app, name: "Scheduled boundary complete actual score - " + scenario) }
            } else {
                XCTAssertFalse(away.exists || home.exists)
                XCTAssertEqual(app.staticTexts["watch.scheduled-matchup"].label, "Kansas City Chiefs at Buffalo Bills")
            }
            XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
            if !expectedHeader.isEmpty { try captureComplete(header, in: app, name: "Complete supplied scheduled header - " + scenario) }
            capture(app, "Scheduled context boundary - " + scenario + (large ? " - AX" : " - standard"))
            app.terminate()
        }
    }

    @MainActor
    func testSavedScheduledStartKeepsQualificationAndOriginalAge() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": "scheduled-no-score"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.staticTexts["watch.scheduled-start"].waitForExistence(timeout: 15))
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let error = app.staticTexts["watch.update-explanation"]
        let offline = XCTNSPredicateExpectation(predicate: NSPredicate(format:
            "exists == true AND label BEGINSWITH %@", "Offline."), object: error)
        XCTAssertEqual(XCTWaiter.wait(for: [offline], timeout: 15), .completed)
        let suppliedStart = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-09T02:00:00Z"))
        let header = app.staticTexts["watch.scheduled-start"]
        XCTAssertEqual(header.label, "Scheduled " + suppliedStart.formatted(.dateTime.month().day().hour().minute()))
        let matchup = app.staticTexts["watch.scheduled-matchup"]
        XCTAssertEqual(matchup.label, "Kansas City Chiefs at Buffalo Bills")
        XCTAssertEqual(app.descendants(matching: .any)["watch.home-probability"].firstMatch.label,
                       "Buffalo Bills win probability, 64%")
        let saved = app.staticTexts["watch.saved-update"]
        XCTAssertEqual(saved.label, "Last saved update")
        XCTAssertTrue(app.descendants(matching: .any)["watch.game-state"].firstMatch.label.contains("Saved reading. Refresh to confirm."))
        for detail in [saved, error] {
            XCTAssertGreaterThanOrEqual(detail.frame.minY, matchup.frame.maxY)
            try captureComplete(detail, in: app, name: "Scheduled saved qualification stays below game")
        }
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.away-score"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-score"].firstMatch.exists)
        try captureComplete(header, in: app, name: "Saved supplied start without clock reset")
    }

    @MainActor
    func testAdaptiveScoreShortLiveAtStandardSize() throws {
        try checkAdaptiveScores(scenario: "short-live", large: false)
    }

    @MainActor
    func testAdaptiveScoreShortLiveAtAccessibilitySize() throws {
        try checkAdaptiveScores(scenario: "short-live", large: true)
    }

    @MainActor
    func testAdaptiveScoreLongFinalAtStandardSize() throws {
        try checkAdaptiveScores(scenario: "long-final", large: false)
    }

    @MainActor
    func testAdaptiveScoreLongFinalAtAccessibilitySize() throws {
        try checkAdaptiveScores(scenario: "long-final", large: true)
    }

    @MainActor
    func testAdaptiveScoreMissingFinalAtStandardSize() throws {
        try checkAdaptiveScores(scenario: "missing-final", large: false)
    }

    @MainActor
    func testAdaptiveScoreMissingFinalAtAccessibilitySize() throws {
        try checkAdaptiveScores(scenario: "missing-final", large: true)
    }

    @MainActor
    func testCompactScoreNamesUseFullWidthRowsAtStandardSize() throws {
        try checkAdaptiveScores(scenario: "compact-final", large: false)
    }

    @MainActor
    private func checkAdaptiveScores(scenario: String, large: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        XCTAssertTrue(state.label.contains(scenario == "short-live" ? "Live" : "Final"))
        let home = scenario == "long-final" ? "Association Sportive de Saint-Étienne Full Canonical Name" : (scenario == "compact-final" ? "Chelsea" : "Buffalo Bills")
        let away = scenario == "long-final" ? "Club de Football Long Complete Opponent Name" : (scenario == "compact-final" ? "Arsenal" : "Kansas City Chiefs")
        let size = large ? "accessibility5" : "standard"
        XCTAssertFalse(app.staticTexts["watch.live-score-explanation"].exists)
        let awayRow = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let homeRow = app.descendants(matching: .any)["watch.home-score"].firstMatch
        if scenario == "short-live" {
            // The declared live fixture uses the shared home identity; final fixtures do not.
            XCTAssertLessThanOrEqual(homeRow.frame.maxY, awayRow.frame.minY)
            try assertGameValueHierarchy(in: app, large: large, expectedHome: home)
        } else {
            XCTAssertFalse(app.descendants(matching: .any)["watch.home-identity"].firstMatch.exists)
            XCTAssertGreaterThanOrEqual(homeRow.frame.minY, awayRow.frame.maxY,
                                        "Final boundaries retain the complete away-then-home rows")
        }
        capture(app, "Natural-fit scoreboard natural top - \(scenario) - \(size)")
        for (identifier, label) in [("watch.away-score", "\(away), score 12"),
                                     ("watch.home-score", "\(home), \(scenario == "missing-final" ? "score unavailable" : "score 0")")] {
            let row = app.descendants(matching: .any)[identifier].firstMatch
            XCTAssertEqual(row.label, label)
            XCTAssertGreaterThan(row.frame.height, 0)
            XCTAssertLessThanOrEqual(row.frame.width, app.frame.width)
            try captureComplete(row, in: app, name: "Full unscaled score row \(identifier) - \(scenario) - \(size)")
        }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        if scenario == "short-live" {
            XCTAssertEqual(probability.label, "Buffalo Bills win probability, 64%")
            XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        } else {
            XCTAssertFalse(probability.exists)
        }
        if scenario == "missing-final" {
            try captureComplete(app.staticTexts["Final score unavailable"], in: app,
                                name: "Missing final score remains unavailable - " + size)
        }
        try captureComplete(app.staticTexts["Score observed 1 hour ago"], in: app,
                            name: "Original score clock preserved - \(scenario) - \(size)")
        print("WATCH_UI_ADAPTIVE_SCORE=\(scenario),\(size),PASS")
    }

    @MainActor
    func testConfirmedFinalOutcomeAtStandardSize() throws {
        try checkConfirmedFinalOutcomes(large: false)
    }

    @MainActor
    func testConfirmedFinalOutcomeAtAccessibilitySize() throws {
        try checkConfirmedFinalOutcomes(large: true)
    }

    @MainActor
    private func checkConfirmedFinalOutcomes(large: Bool) throws {
        for (scenario, expectedHeader, awayScore, homeScore) in [
            ("final-home-win", "Final · Buffalo Bills won", "0", "12"),
            ("final-away-win", "Final · Kansas City Chiefs won", "12", "0"),
            ("final-score-tie", "Final · scores tied", "2", "2")
        ] {
            try checkFinalOutcome(scenario: scenario, expectedHeader: expectedHeader,
                                  awayScore: awayScore, homeScore: homeScore, large: large)
        }
    }

    @MainActor
    func testLongFinalOutcomeKeepsWholeHeaderAndBothRowsAtStandardSize() throws {
        try checkLongFinalOutcome(large: false)
    }

    @MainActor
    func testLongFinalOutcomeKeepsWholeHeaderAndBothRowsAtAccessibilitySize() throws {
        try checkLongFinalOutcome(large: true)
    }

    @MainActor
    private func checkLongFinalOutcome(large: Bool) throws {
        try checkFinalOutcome(scenario: "long-final",
                              expectedHeader: "Final · Club de Football Long Complete Opponent Name won",
                              awayScore: "12", homeScore: "0", large: large,
                              awayName: "Club de Football Long Complete Opponent Name",
                              homeName: "Association Sportive de Saint-Étienne Full Canonical Name")
    }

    @MainActor
    func testCompletedStatusUsesSameFinalScoreInterpretation() throws {
        try checkFinalOutcome(scenario: "completed-home-win", expectedHeader: "Final · Buffalo Bills won",
                              awayScore: "0", homeScore: "12", large: false)
    }

    @MainActor
    func testMissingOrNegativeFinalScoreDoesNotNameOutcome() throws {
        try checkFinalOutcome(scenario: "missing-final", expectedHeader: "Final",
                              awayScore: "12", homeScore: nil, large: false)
        try checkFinalOutcome(scenario: "final-negative-score", expectedHeader: "Final",
                              awayScore: "12", homeScore: "-1", large: false)
    }

    @MainActor
    func testSavedFinalOutcomeKeepsQuietQualificationAndOriginalAge() throws {
        try checkFinalOutcome(scenario: "final-home-win", expectedHeader: "Final · Buffalo Bills won",
                              awayScore: "0", homeScore: "12", large: false, saved: true)
    }

    @MainActor
    private func checkFinalOutcome(scenario: String, expectedHeader: String,
                                   awayScore: String?, homeScore: String?, large: Bool,
                                   saved: Bool = false,
                                   awayName: String = "Kansas City Chiefs",
                                   homeName: String = "Buffalo Bills") throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        if saved {
            app.terminate()
            app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
            app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
            app.launch()
            let error = app.staticTexts["watch.update-explanation"]
            let offline = XCTNSPredicateExpectation(predicate: NSPredicate(format:
                "exists == true AND label BEGINSWITH %@", "Offline."), object: error)
            XCTAssertEqual(XCTWaiter.wait(for: [offline], timeout: 15), .completed)
        }
        XCTAssertEqual(state.label, expectedHeader)
        XCTAssertFalse(app.staticTexts["watch.home-probability-unavailable"].exists)
        try assertSingleResultQualification(in: app, label: expectedHeader)
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["watch.scheduled-start"].exists)
        XCTAssertFalse(app.staticTexts["watch.score-heading"].exists)
        let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
        XCTAssertEqual(away.label, awayName + ", " + (awayScore.map { "score " + $0 } ?? "score unavailable"))
        XCTAssertEqual(home.label, homeName + ", " + (homeScore.map { "score " + $0 } ?? "score unavailable"))
        XCTAssertLessThanOrEqual(state.frame.maxY, away.frame.minY)
        XCTAssertGreaterThanOrEqual(home.frame.minY, away.frame.maxY)
        if !large {
            for element in [state, away, home] { XCTAssertTrue(try viewport(in: app).contains(element.frame)) }
        }
        capture(app, "Final outcome natural opening - " + scenario + (large ? " - AX" : " - standard"))
        for element in [state, away, home] { try captureComplete(element, in: app, name: "Complete final outcome and score - " + scenario) }
        let age = app.staticTexts["Score observed 1 hour ago"]
        XCTAssertTrue(age.exists)
        XCTAssertGreaterThanOrEqual(age.frame.minY, home.frame.maxY)
        XCTAssertFalse(app.staticTexts["Probability observed 3 hours ago"].exists)
        if homeScore == nil { XCTAssertTrue(app.staticTexts["Final score unavailable"].exists) }
        if saved {
            let savedNote = app.staticTexts["watch.saved-update"]
            let error = app.staticTexts["watch.update-explanation"]
            XCTAssertEqual(savedNote.label, "Last saved update")
            XCTAssertTrue(error.label.hasPrefix("Offline."))
            for detail in [savedNote, error] {
                XCTAssertGreaterThanOrEqual(detail.frame.minY, home.frame.maxY)
                try captureComplete(detail, in: app, name: "Quiet saved final qualification")
            }
            XCTAssertEqual(state.label, expectedHeader, "The outcome is not repeated inside the lower saved qualifier")
        }
    }

    @MainActor
    func testSelectedClosedRetainsScoresWithoutForecastAtStandardSize() throws {
        try checkSelectedReadingBoundary(closed: true, large: false)
    }

    @MainActor
    func testSelectedClosedRetainsScoresWithoutForecastAtAccessibilitySize() throws {
        try checkSelectedReadingBoundary(closed: true, large: true)
    }

    @MainActor
    func testSelectedUnknownChanceRetainsScoresAtStandardSize() throws {
        try checkSelectedReadingBoundary(closed: false, large: false)
    }

    @MainActor
    func testSelectedUnknownChanceRetainsScoresAtAccessibilitySize() throws {
        try checkSelectedReadingBoundary(closed: false, large: true)
    }

    @MainActor
    func testLongNamedUnavailableChanceRetainsScoresAtStandardSize() throws {
        try checkSelectedReadingBoundary(closed: false, large: false, longName: true)
    }

    @MainActor
    func testLongNamedUnavailableChanceRetainsScoresAtAccessibilitySize() throws {
        try checkSelectedReadingBoundary(closed: false, large: true, longName: true)
    }

    @MainActor
    func testSavedClosedResultQualificationStaysAboveScoresAtStandardSize() throws {
        try checkSelectedReadingBoundary(closed: true, large: false, saved: true)
    }

    @MainActor
    func testSavedClosedResultQualificationStaysAboveScoresAtAccessibilitySize() throws {
        try checkSelectedReadingBoundary(closed: true, large: true, saved: true)
    }

    @MainActor
    private func checkSelectedReadingBoundary(closed: Bool, large: Bool, saved: Bool = false, longName: Bool = false) throws {
        continueAfterFailure = false
        XCTAssertFalse(longName && (closed || saved), "Long-name specimen is the declared fresh missing-chance case")
        let scenario = closed ? "selected-closed" : (longName ? "long-unknown-probability" : "selected-unknown-probability")
        let expectedHome = longName ? "Association Sportive de Saint-Étienne Full Canonical Name" : "Buffalo Bills"
        let expectedAway = longName ? "Club de Football Long Complete Opponent Name" : "Kansas City Chiefs"
        let size = large ? "accessibility5" : "standard"
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        if saved {
            XCTAssertTrue(closed)
            app.terminate()
            app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
            app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
            app.launch()
            let error = app.staticTexts["watch.update-explanation"]
            let offline = XCTNSPredicateExpectation(predicate: NSPredicate(format:
                "exists == true AND label BEGINSWITH %@", "Offline."), object: error)
            XCTAssertEqual(XCTWaiter.wait(for: [offline], timeout: 15), .completed)
        }
        XCTAssertEqual(state.label, closed ? "Result not confirmed" : "Live")
        XCTAssertTrue(app.buttons["watch.choose-another"].exists)
        XCTAssertFalse(app.staticTexts["watch.live-score-explanation"].exists)
        XCTAssertFalse(app.staticTexts["watch.picker-heading"].exists, "These receipts must show the selected page, not the picker")
        let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
        XCTAssertEqual(away.label, expectedAway + ", score 12")
        XCTAssertEqual(home.label, expectedHome + ", score 0", "Actual zero is preserved; it is not a missing value")
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-identity"].firstMatch.exists,
                       "Missing chance must not create an empty shared probability hero")
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertFalse(probability.exists, "A suppressed or missing chance must never become0% or the supplied64%")
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "%")).count, 0)
        capture(app, "Selected boundary natural opening - " + scenario + " - " + size)
        if !large {
            let bounds = try viewport(in: app)
            for row in [away, home] {
                XCTAssertTrue(bounds.contains(row.frame), "Both complete actual score rows must fit the standard opening")
            }
        }
        for (row, name) in [(away, "away"), (home, "home")] {
            XCTAssertGreaterThan(row.frame.height, 0)
            XCTAssertLessThanOrEqual(row.frame.width, app.frame.width)
            try captureComplete(row, in: app, name: "Selected full name and actual score - " + name + " - " + scenario + " - " + size)
        }
        if closed {
            XCTAssertFalse(app.staticTexts["watch.home-probability-unavailable"].exists)
            XCTAssertFalse(app.staticTexts["Win probability unavailable"].exists,
                           "Closed events require result qualification, not a missing-forecast invitation")
            try assertSingleResultQualification(in: app, label: "Result not confirmed")
            XCTAssertFalse(app.staticTexts["Closed · result unverified"].exists)
            XCTAssertFalse(app.staticTexts["Last reported score · final result unverified"].exists)
            XCTAssertFalse(app.staticTexts["Final score"].exists)
            XCTAssertFalse(app.staticTexts["watch.score-heading"].exists,
                           "Saved/error context must not replace qualification with generic Score")
            XCTAssertLessThanOrEqual(state.frame.maxY, min(away.frame.minY, home.frame.minY),
                                     "Result qualification must precede both complete named score rows")
            try captureComplete(state, in: app, name: "Single plain result qualification above scores - " + size + (saved ? " - saved offline" : ""))
        } else {
            let unavailable = app.staticTexts["watch.home-probability-unavailable"]
            XCTAssertTrue(unavailable.exists)
            XCTAssertEqual(unavailable.label, expectedHome + " win chance unavailable")
            XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", expectedHome + " win chance unavailable")).count, 1)
            XCTAssertGreaterThanOrEqual(unavailable.frame.minY, max(away.frame.maxY, home.frame.maxY),
                                        "Quiet unavailable reading stays below both useful scores")
            XCTAssertGreaterThanOrEqual(unavailable.frame.minY, state.frame.maxY)
            XCTAssertGreaterThanOrEqual(app.staticTexts["Score observed 1 hour ago"].frame.minY, unavailable.frame.maxY)
            try captureComplete(unavailable, in: app, name: "Complete named missing chance without fabricated percent - " + scenario + " - " + size)
        }
        let scoreAge = app.staticTexts["Score observed 1 hour ago"]
        XCTAssertTrue(scoreAge.exists)
        XCTAssertGreaterThanOrEqual(scoreAge.frame.minY, max(away.frame.maxY, home.frame.maxY))
        try captureComplete(scoreAge, in: app, name: "Original independent score clock below game - " + scenario + " - " + size)
        XCTAssertFalse(app.staticTexts["Probability observed 3 hours ago"].exists,
                       "A timestamp alone must not imply a current visible chance")
        if saved {
            let savedNote = app.staticTexts["watch.saved-update"]
            let error = app.staticTexts["watch.update-explanation"]
            XCTAssertEqual(savedNote.label, "Last saved update")
            XCTAssertTrue(error.label.hasPrefix("Offline."))
            for detail in [savedNote, error] {
                XCTAssertGreaterThanOrEqual(detail.frame.minY, max(away.frame.maxY, home.frame.maxY))
                try captureComplete(detail, in: app, name: "Saved closed explanation remains below game - " + detail.identifier + " - " + size)
            }
            XCTAssertEqual(state.label, "Result not confirmed", "Header never prepends saved/error jargon")
        } else {
            XCTAssertFalse(app.staticTexts["watch.saved-update"].exists)
            XCTAssertFalse(app.staticTexts["watch.update-explanation"].exists)
        }
        print("WATCH_UI_SELECTED_BOUNDARY=\(scenario),\(size),saved=\(saved),PASS")
    }

    @MainActor
    func testLiveMissingBothScoreIsExplainedAtStandardSize() throws {
        try checkMissingLiveScore(scenario: "live-missing-both", large: false)
    }

    @MainActor
    func testLiveMissingBothScoreIsExplainedAtAccessibilitySize() throws {
        try checkMissingLiveScore(scenario: "live-missing-both", large: true)
    }

    @MainActor
    func testLiveMissingAwayScoreIsExplainedAtStandardSize() throws {
        try checkMissingLiveScore(scenario: "live-missing-away", large: false)
    }

    @MainActor
    func testLiveMissingAwayScoreIsExplainedAtAccessibilitySize() throws {
        try checkMissingLiveScore(scenario: "live-missing-away", large: true)
    }

    @MainActor
    func testLiveMissingHomeScoreIsExplainedAtStandardSize() throws {
        try checkMissingLiveScore(scenario: "live-missing-home", large: false)
    }

    @MainActor
    func testLiveMissingHomeScoreIsExplainedAtAccessibilitySize() throws {
        try checkMissingLiveScore(scenario: "live-missing-home", large: true)
    }

    @MainActor
    private func checkMissingLiveScore(scenario: String, large: Bool) throws {
        continueAfterFailure = false
        let missingAway = scenario != "live-missing-home"
        let missingHome = scenario != "live-missing-away"
        let expected = missingAway && missingHome ? "Score unavailable" : "One score unavailable"
        let size = large ? "accessibility5" : "standard"
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_SCORE_LAYOUT": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        defer { app.terminate() }
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 15))
        XCTAssertEqual(state.label, "Live")
        XCTAssertFalse(app.staticTexts["watch.picker-heading"].exists)
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "Buffalo Bills win probability, 64%")
        let away = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let home = app.descendants(matching: .any)["watch.home-score"].firstMatch
        XCTAssertEqual(away.label, "Kansas City Chiefs, " + (missingAway ? "score unavailable" : "score 12"))
        XCTAssertEqual(home.label, "Buffalo Bills, " + (missingHome ? "score unavailable" : "score 0"))
        let explanation = app.staticTexts["watch.live-score-explanation"]
        XCTAssertEqual(explanation.label, expected, "Exactly one missing side must not imply both scores are unavailable")
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "identifier == %@", "watch.live-score-explanation")).count, 1)
        XCTAssertLessThanOrEqual(probability.frame.maxY, min(away.frame.minY, home.frame.minY), "Known named chance stays first")
        XCTAssertGreaterThanOrEqual(explanation.frame.minY, max(away.frame.maxY, home.frame.maxY))
        capture(app, "Missing live scores natural opening - " + scenario + " - " + size)
        if !large {
            let bounds = try viewport(in: app)
            for reading in [probability, away, home] {
                XCTAssertTrue(bounds.contains(reading.frame), "Explanation cannot displace the full standard primary reading or score rows")
            }
        }
        for (reading, label) in [(probability, "named chance"), (away, "away score"), (home, "home score"), (explanation, "unavailable explanation")] {
            XCTAssertGreaterThan(reading.frame.height, 0)
            XCTAssertLessThanOrEqual(reading.frame.width, app.frame.width)
            try captureComplete(reading, in: app, name: "Complete native " + label + " - " + scenario + " - " + size)
        }
        for label in ["Score observed 1 hour ago", "Probability observed 3 hours ago"] {
            let age = app.staticTexts[label]
            XCTAssertTrue(age.exists)
            XCTAssertGreaterThanOrEqual(age.frame.minY, explanation.frame.maxY)
            try captureComplete(age, in: app, name: "Independent original clock - " + label + " - " + scenario + " - " + size)
        }
        XCTAssertFalse(app.staticTexts["Final score unavailable"].exists)
        XCTAssertFalse(app.staticTexts["watch.saved-update"].exists)
        XCTAssertFalse(app.staticTexts["watch.update-explanation"].exists)
        print("WATCH_UI_LIVE_MISSING_SCORE=\(scenario),\(size),PASS")
    }

    @MainActor
    func testFirstOpenRetainsContextUntilDetailArrivesAtStandardSize() throws {
        try checkFirstOpenContext(large: false)
    }

    @MainActor
    func testFirstOpenRetainsContextUntilDetailArrivesAtAccessibilitySize() throws {
        try checkFirstOpenContext(large: true)
    }

    @MainActor
    private func launchFirstOpen(large: Bool, missing: Bool = false) throws -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1", "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString,
            "BAINLUCK_WATCH_UI_RESET": "1", "BAINLUCK_WATCH_UI_FIRST_OPEN": missing ? "missing" : "1",
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        app.launch()
        if !missing {
            let first = app.buttons["watch.pick.101"]
            XCTAssertTrue(first.waitForExistence(timeout: 15))
            try reveal(first, in: app)
            first.tap()
        }
        XCTAssertTrue(app.descendants(matching: .any)["watch.loading-selected-game"].firstMatch.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["watch.selection-loading-explanation"].label,
                       "Your selection is retained while details load.")
        return app
    }

    @MainActor
    private func assertNoDetailReading(_ app: XCUIApplication) {
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-probability"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["99%"].exists, "Picker odds must not become a fetched detail reading")
        XCTAssertFalse(app.descendants(matching: .any)["watch.home-score"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["watch.away-score"].firstMatch.exists)
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Score observed ")).count, 0)
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Probability observed ")).count, 0)
        XCTAssertFalse(app.staticTexts["Selected game unavailable"].exists)
    }

    @MainActor
    private func checkFirstOpenContext(large: Bool) throws {
        let app = try launchFirstOpen(large: large)
        defer { app.terminate() }
        let context = app.descendants(matching: .any)["watch.selection-context"].firstMatch
        XCTAssertTrue(context.exists)
        XCTAssertTrue(context.label.contains("Los Angeles Dodgers") && context.label.contains("San Francisco Giants"))
        let start = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-09T02:00:00Z"))
        XCTAssertTrue(context.label.contains(start.formatted(.dateTime.month().day().hour().minute())))
        assertNoDetailReading(app)
        let size = large ? "accessibility5" : "standard"
        try captureComplete(context, in: app, name: "Known matchup and supplied start while detail suspended - " + size)
        let deliver = app.buttons["watch.fixture-deliver-detail"]
        try reveal(deliver, in: app)
        deliver.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertTrue(probability.waitForExistence(timeout: 15))
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertFalse(context.exists)
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        try captureComplete(probability, in: app, name: "Same released request supplies named64 and original clocks - " + size)
        print("WATCH_UI_FIRST_OPEN_\(size.uppercased())=PASS")
    }

    @MainActor
    func testFirstOpenSwitchAndFailureKeepOnlyNewUndatedContext() throws {
        let app = try launchFirstOpen(large: true)
        defer { app.terminate() }
        try openPicker(app)
        let other = app.buttons["watch.pick.202"]
        try reveal(other, in: app)
        other.tap()
        let context = app.descendants(matching: .any)["watch.selection-context"].firstMatch
        let newIdentity = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label CONTAINS %@", "Buffalo Bills"), object: context)
        XCTAssertEqual(XCTWaiter.wait(for: [newIdentity], timeout: 15), .completed)
        XCTAssertTrue(context.label.contains("Kansas City Chiefs"))
        XCTAssertFalse(context.label.contains("Giants") || context.label.contains("Oct"))
        assertNoDetailReading(app)
        try captureComplete(context, in: app, name: "Switched pending request keeps only new undated Bills context")
        let fail = app.buttons["watch.fixture-fail-detail"]
        try reveal(fail, in: app)
        fail.tap()
        let error = app.staticTexts["Offline. Try again."]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["watch.selection-state-heading"].label, "Reading unavailable")
        let retained = app.staticTexts["watch.selection-retry-explanation"]
        XCTAssertEqual(retained.label, "Your selection is retained. Refresh to try again.")
        // Exercise a pending retry explicitly, instead of relying on the time
        // spent capturing large text to cross the automatic retry deadline.
        // If that deadline already elapsed, the same identified control is
        // disabled and the already-pending retry must meet the same assertions.
        let retry = app.buttons["watch.refresh-selected-game"]
        try reveal(retry, in: app)
        if retry.isEnabled { retry.tap() }
        XCTAssertTrue(app.descendants(matching: .any)["watch.loading-selected-game"].firstMatch.waitForExistence(timeout: 15))
        XCTAssertTrue(error.exists)
        XCTAssertEqual(app.staticTexts["watch.selection-state-heading"].label, "Reading unavailable")
        XCTAssertEqual(retained.label, "Your selection is retained. Refresh to try again.")
        try captureComplete(retained, in: app, name: "Unavailable detail retains selection and names retry")
        XCTAssertTrue(context.exists && context.label.contains("Buffalo Bills"))
        assertNoDetailReading(app)
        try captureComplete(context, in: app, name: "Real failed request retains known Bills context")
        try captureComplete(error, in: app, name: "Real failed request preserves retry explanation")
        let clear = app.buttons["watch.clear-selection"]
        try reveal(clear, in: app)
        clear.tap()
        XCTAssertTrue(app.staticTexts["watch.picker-heading"].waitForExistence(timeout: 15))
        XCTAssertFalse(context.exists)
        print("WATCH_UI_FIRST_OPEN_SWITCH_FAILURE=PASS")
    }

    @MainActor
    func testFirstOpenMissingPickerMetadataDoesNotInventContext() throws {
        let app = try launchFirstOpen(large: false, missing: true)
        defer { app.terminate() }
        let context = app.descendants(matching: .any)["watch.selection-context"].firstMatch
        XCTAssertFalse(context.exists)
        assertNoDetailReading(app)
        capture(app, "No matching picker metadata stays honest while suspended")
        let fail = app.buttons["watch.fixture-fail-detail"]
        try reveal(fail, in: app)
        fail.tap()
        let error = app.staticTexts["Offline. Try again."]
        XCTAssertTrue(error.waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["watch.selection-state-heading"].label, "Reading unavailable")
        let retained = app.staticTexts["watch.selection-retry-explanation"]
        XCTAssertEqual(retained.label, "Your selection is retained. Refresh to try again.")
        try captureComplete(retained, in: app, name: "Unavailable detail retains selection and names retry")
        XCTAssertFalse(context.exists)
        try captureComplete(error, in: app, name: "Missing metadata failure remains recoverable")
        print("WATCH_UI_FIRST_OPEN_MISSING=PASS")
    }

    @MainActor
    func testTeamColorNamesAndMissingFallbackAtStandardSize() throws {
        try checkTeamColorNames(large: false)
    }

    @MainActor
    func testTeamColorNamesAndMissingFallbackAtAccessibilitySize() throws {
        try checkTeamColorNames(large: true)
    }

    @MainActor
    private func checkTeamColorNames(large: Bool) throws {
        let app = try launchCurrentGame(large: large, scenario: "team-color")
        defer { app.terminate() }
        let size = large ? "accessibility5" : "standard"
        try captureMainScoreNames(in: app, away: "Los Angeles Dodgers", home: "San Francisco Giants", awayScore: 2, homeScore: 3, specimen: "missing-metadata-" + size)
        try openPicker(app)
        let missing = try assertCurrent(app, id: 111)
        try captureComplete(missing, in: app, name: "Missing team metadata retains full current matchup - " + size)
        let other = app.buttons["watch.pick.202"]
        XCTAssertEqual(other.label, "Kansas City Chiefs at Buffalo Bills. Scheduled")
        try captureComplete(other, in: app, name: "Restrained team colors and full alternative names - " + size)
        try reveal(other, in: app)
        other.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let bills = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@",
            "Buffalo Bills win probability, 55%"), object: probability)
        XCTAssertEqual(XCTWaiter.wait(for: [bills], timeout: 15), .completed)
        try captureMainScoreNames(in: app, away: "Kansas City Chiefs", home: "Buffalo Bills", awayScore: 0, homeScore: 0, specimen: "exact202-valid-colors-" + size)
        try openPicker(app)
        let current = app.buttons["watch.pick.202"]
        XCTAssertTrue(current.isSelected)
        XCTAssertEqual(current.label, "Kansas City Chiefs at Buffalo Bills. Scheduled. Your game")
        XCTAssertTrue(try XCTUnwrap(current.value as? String).contains("Buffalo Bills win probability, 55%"))
        try captureComplete(current, in: app, name: "Current team colors preserve named55 and Return - " + size)
        print("WATCH_UI_TEAM_COLOR_\(size.uppercased())=PASS")
    }

    @MainActor
    func testMainScoreAliasColorsStayTextOnlyAtStandardSize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-alias", large: false)
    }

    @MainActor
    func testMainScoreAliasColorsStayTextOnlyAtAccessibilitySize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-alias", large: true)
    }

    @MainActor
    func testMainScoreInvalidColorsStayTextOnlyAtStandardSize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-invalid", large: false)
    }

    @MainActor
    func testMainScoreInvalidColorsStayTextOnlyAtAccessibilitySize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-invalid", large: true)
    }

    @MainActor
    func testMainScoreColorsKeepLongNamesAtStandardSize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-long", large: false)
    }

    @MainActor
    func testMainScoreColorsKeepLongNamesAtAccessibilitySize() throws {
        try checkMainScoreColorFallback(scenario: "team-color-long", large: true)
    }

    @MainActor
    private func checkMainScoreColorFallback(scenario: String, large: Bool) throws {
        let app = try launchCurrentGame(large: large, scenario: scenario)
        defer { app.terminate() }
        let size = large ? "accessibility5" : "standard"
        if scenario == "team-color-alias" {
            // The first loaded feed colors101; accepted detail resolves it to111.
            // Exact event metadata must not be borrowed from that alias.
            try captureMainScoreNames(in: app, away: "Los Angeles Dodgers", home: "San Francisco Giants",
                                      awayScore: 2, homeScore: 3, specimen: "colored101-does-not-color111-" + size)
        } else {
            try openPicker(app)
            let row = app.buttons["watch.pick.202"]
            try reveal(row, in: app)
            row.tap()
            let long = scenario == "team-color-long"
            let away = long ? "Club de Football Long Complete Opponent Name" : "Kansas City Chiefs"
            let home = long ? "Association Sportive de Saint-Étienne Full Canonical Name" : "Buffalo Bills"
            let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
            let selected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@",
                home + " win probability, 55%"), object: probability)
            XCTAssertEqual(XCTWaiter.wait(for: [selected], timeout: 15), .completed)
            try captureMainScoreNames(in: app, away: away, home: home, awayScore: 0, homeScore: 0,
                                      specimen: scenario + "-" + size)
        }
        print("WATCH_UI_MAIN_SCORE_COLOR=\(scenario),\(size),PASS")
    }

    @MainActor
    private func captureMainScoreNames(in app: XCUIApplication, away: String, home: String,
                                       awayScore: Int, homeScore: Int, specimen: String) throws {
        capture(app, "Main score marker natural opening - " + specimen)
        for (identifier, expected) in [("watch.away-score", "\(away), score \(awayScore)"),
                                       ("watch.home-score", "\(home), score \(homeScore)")] {
            let row = app.descendants(matching: .any)[identifier].firstMatch
            XCTAssertEqual(row.label, expected, "Decorative dots must not add speech or replace full names")
            XCTAssertGreaterThan(row.frame.height, 0)
            XCTAssertLessThanOrEqual(row.frame.width, app.frame.width)
            try captureComplete(row, in: app, name: "Full native main score row - " + identifier + " - " + specimen)
        }
        // Exact colored/missing/malformed/mismatched appearance is reviewed in
        // originals; hidden decorative dots are deliberately not accessibility controls.
    }

    @MainActor
    func testProbabilityBarAndEnabledClearAtStandardSize() throws {
        try checkProbabilityBarAndClear(large: false)
    }

    @MainActor
    func testProbabilityBarAndEnabledClearAtAccessibilitySize() throws {
        try checkProbabilityBarAndClear(large: true)
    }

    @MainActor
    private func checkProbabilityBarAndClear(large: Bool) throws {
        let app = try launchCurrentGame(large: large)
        defer { app.terminate() }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        let size = large ? "accessibility5" : "standard"
        try captureComplete(probability, in: app, name: "Named64 with compact scalar bar - " + size)
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        let clear = app.buttons["watch.clear-selection"]
        try reveal(clear, in: app)
        XCTAssertTrue(clear.isEnabled)
        XCTAssertGreaterThanOrEqual(clear.frame.height, 44)
        try captureComplete(clear, in: app, name: "Enabled outlined Clear - " + size)
        clear.tap()
        XCTAssertTrue(app.staticTexts["watch.picker-heading"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["watch.picker-heading"].label, "Choose your game")
        XCTAssertFalse(probability.exists)
        XCTAssertFalse(clear.exists)
        capture(app, "Enabled Clear returns to picker - " + size)
        print("WATCH_UI_BAR_CLEAR_\(size.uppercased())=PASS")
    }

    @MainActor
    func testScheduledPickerShowsSuppliedTimeAtStandardSize() throws {
        try checkScheduledTime(large: false)
    }

    @MainActor
    func testScheduledPickerShowsSuppliedTimeAtAccessibilitySize() throws {
        try checkScheduledTime(large: true)
    }

    @MainActor
    private func checkScheduledTime(large: Bool) throws {
        let app = try launchCurrentGame(large: large, scenario: "scheduled-time")
        defer { app.terminate() }
        try openPicker(app)
        let other = app.buttons["watch.pick.202"]
        XCTAssertTrue(other.waitForExistence(timeout: 15))
        let start = app.staticTexts["watch.pick-start.202"]
        XCTAssertTrue(start.exists)
        let suppliedDate = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-09T02:00:00Z"))
        XCTAssertEqual(start.label, suppliedDate.formatted(.dateTime.month().day().hour().minute()))
        XCTAssertEqual(other.value as? String, "Scheduled start " + start.label)
        XCTAssertTrue(other.frame.insetBy(dx: -1, dy: -1).contains(start.frame), "Start time remains inside the card")
        XCTAssertEqual(other.label, "Kansas City Chiefs at Buffalo Bills. Scheduled")
        let size = large ? "accessibility5" : "standard"
        try captureComplete(other, in: app, name: "Scheduled alternate with supplied time - " + size)
        try reveal(other, in: app)
        other.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let bills = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@",
            "Buffalo Bills win probability, 55%"), object: probability)
        XCTAssertEqual(XCTWaiter.wait(for: [bills], timeout: 15), .completed)
        try openPicker(app)
        let current = app.buttons["watch.pick.202"]
        XCTAssertTrue(current.isSelected)
        XCTAssertTrue(start.exists)
        XCTAssertEqual(start.label, suppliedDate.formatted(.dateTime.month().day().hour().minute()))
        XCTAssertTrue(try XCTUnwrap(current.value as? String).contains("Scheduled start " + start.label))
        XCTAssertTrue(current.frame.insetBy(dx: -1, dy: -1).contains(start.frame), "Current start time remains inside the card")
        try captureComplete(current, in: app, name: "Scheduled current with supplied time and Return - " + size)
        print("WATCH_UI_SCHEDULED_PICKER_TIME_\(size.uppercased())=PASS")
    }

    @MainActor
    func testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize() throws {
        let app = try launchCurrentGame(large: true)
        defer { app.terminate() }
        try openPicker(app)
        let other = app.buttons["watch.pick.202"]
        XCTAssertTrue(other.waitForExistence(timeout: 15))
        XCTAssertFalse(other.isSelected)
        XCTAssertEqual(other.label, "Kansas City Chiefs at Buffalo Bills. Scheduled")
        XCTAssertGreaterThanOrEqual(other.frame.height, 44)
        try captureComplete(other, in: app, name: "Alternative full matchup and Scheduled - accessibility5")
        try reveal(other, in: app)
        other.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let bills = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@",
            "Buffalo Bills win probability, 55%"), object: probability)
        XCTAssertEqual(XCTWaiter.wait(for: [bills], timeout: 15), .completed)
        capture(app, "Selected scheduled game at natural top - accessibility5")
        try captureComplete(probability, in: app, name: "Alternative selected Bills55 - accessibility5")
        try openPicker(app)
        let current = app.buttons["watch.pick.202"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        XCTAssertTrue(current.isSelected)
        XCTAssertEqual(current.label, "Kansas City Chiefs at Buffalo Bills. Scheduled. Your game")
        XCTAssertTrue(try XCTUnwrap(current.value as? String).contains("55%"))
        try captureComplete(current, in: app, name: "Bills becomes current with Return - accessibility5")
        try reveal(current, in: app)
        let bounds = try viewport(in: app)
        let visible = current.frame.intersection(bounds)
        XCTAssertTrue(current.isHittable && !visible.isEmpty)
        let target = CGPoint(x: visible.midX, y: visible.midY)
        XCTAssertTrue(bounds.contains(target) && current.frame.contains(target))
        let geometry = XCTAttachment(string: "Card: \(current.frame); viewport: \(bounds); target: \(target)\n" + app.debugDescription)
        geometry.name = "Verified Bills current-card return target"
        geometry.lifetime = .keepAlways
        add(geometry)
        app.coordinate(withNormalizedOffset: .zero).withOffset(
            CGVector(dx: target.x - app.frame.minX, dy: target.y - app.frame.minY)).tap()
        XCTAssertFalse(app.buttons["watch.picker-cancel"].exists)
        XCTAssertEqual(probability.label, "Buffalo Bills win probability, 55%")
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        capture(app, "Returned scheduled game at natural top - accessibility5")
        try captureComplete(probability, in: app, name: "Returning keeps Bills55 - accessibility5")
        let awayScore = app.descendants(matching: .any)["watch.away-score"].firstMatch
        let homeScore = app.descendants(matching: .any)["watch.home-score"].firstMatch
        XCTAssertEqual(awayScore.label, "Kansas City Chiefs, score 0")
        XCTAssertEqual(homeScore.label, "Buffalo Bills, score 0")
        try captureComplete(awayScore, in: app, name: "Scheduled reported away score retained - accessibility5")
        try captureComplete(homeScore, in: app, name: "Scheduled reported home score retained - accessibility5")
        try captureComplete(app.staticTexts["Score observed 1 hour ago"], in: app,
                            name: "Scheduled independent score age1h - accessibility5")
        try captureComplete(app.staticTexts["Probability observed 3 hours ago"], in: app,
                            name: "Scheduled independent probability age3h - accessibility5")
        print("WATCH_UI_ALTERNATIVE_CURRENT_RETURN_ACCESSIBILITY5=PASS")
    }

    @MainActor
    func testCurrentGameSurvivesPartialOfflineAndEmptyLists() throws {
        let app = try launchCurrentGame(large: false)
        defer { app.terminate() }
        try openPicker(app)
        let current = try assertCurrent(app, id: 111)
        try captureComplete(current, in: app, name: "Partial list retains current Giants - standard")
        try assertStatus("Some games unavailable", in: app)
        try refresh(app, expected: "Offline · Previous list")
        _ = try assertCurrent(app, id: 111)
        try captureComplete(app.staticTexts["watch.picker-status"], in: app, name: "Compact offline status - standard")
        try refresh(app, expected: "No games in Discover right now")
        let retained = try assertCurrent(app, id: 111)
        XCTAssertFalse(app.buttons["watch.pick.202"].exists)
        try captureComplete(app.staticTexts["watch.picker-status"], in: app, name: "True empty list with retained choice - standard")
        try reveal(retained, in: app)
        retained.tap()
        XCTAssertTrue(app.descendants(matching: .any)["watch.home-probability"].firstMatch.waitForExistence(timeout: 15))
        XCTAssertEqual(app.descendants(matching: .any)["watch.home-probability"].firstMatch.label,
                       "San Francisco Giants win probability, 64%")
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        try openPicker(app) // Fifth list response recovers the proven101 alias.
        _ = try assertCurrent(app, id: 101)
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "watch.pick.")).allElementsBoundByIndex
        XCTAssertEqual(rows.map(\.identifier), ["watch.pick.101", "watch.pick.202"])
        let other = app.buttons["watch.pick.202"]
        XCTAssertFalse(other.isSelected)
        try reveal(other, in: app)
        other.tap()
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@",
            "Buffalo Bills win probability, 55%"), object: probability)
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 15), .completed)
        try captureComplete(probability, in: app, name: "Other choice loads its own Bills55 reading")
        print("WATCH_UI_CURRENT_GAME_STANDARD=PASS")
    }

    @MainActor
    func testCurrentGameAndOfflineDetailsAtAccessibilitySize() throws {
        let app = try launchCurrentGame(large: true)
        defer { app.terminate() }
        try openPicker(app)
        XCTAssertEqual(app.staticTexts["watch.picker-heading"].value as? String, "accessibility5")
        let current = try assertCurrent(app, id: 111)
        try captureComplete(current, in: app, name: "Complete current Giants card - accessibility5")
        try captureComplete(app.staticTexts["watch.picker-other-heading"], in: app, name: "Other games separation - accessibility5")
        let other = app.buttons["watch.pick.202"]
        XCTAssertFalse(other.isSelected)
        try captureComplete(other, in: app, name: "Complete Chiefs at Bills choice - accessibility5")
        try refresh(app, expected: "Offline · Previous list")
        try captureComplete(app.staticTexts["watch.picker-status"], in: app, name: "Compact offline status - accessibility5")
        let details = app.descendants(matching: .any)["watch.picker-info"].firstMatch
        try reveal(details, in: app)
        details.tap()
        let error = app.staticTexts["watch.picker-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 10))
        XCTAssertEqual(error.label, "Offline. Connect to the internet, then refresh games.")
        for (element, name) in [
            (error, "Full offline instruction"),
            (app.staticTexts["Games from Discover · not the full schedule"], "Discover scope"),
            (app.staticTexts["Some games have unavailable details."], "Omission explanation"),
            (app.staticTexts["Your current game stays selected even when it is not in this list."], "Retained selection explanation")
        ] {
            try captureComplete(element, in: app, name: name + " - accessibility5")
        }
        _ = try assertCurrent(app, id: 111)
        print("WATCH_UI_CURRENT_GAME_LARGE=PASS")
    }

    @MainActor
    func testFinalCurrentGameShowsScoreInsteadOfForecast() throws {
        let app = try launchCurrentGame(large: false, scenario: "final")
        defer { app.terminate() }
        try openPicker(app)
        let current = app.buttons["watch.pick.111"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        let value = try XCTUnwrap(current.value as? String)
        XCTAssertTrue(value.contains("Final score · 2–3"))
        XCTAssertTrue(value.contains("Score observed 1 hour ago"))
        XCTAssertFalse(value.contains("64%"))
        XCTAssertFalse(value.contains("win probability"))
        try captureComplete(current, in: app, name: "Final current game uses original score clock")
        print("WATCH_UI_CURRENT_GAME_FINAL=PASS")
    }

    @MainActor
    func testUnknownCurrentGameDoesNotInventProbabilityOrAge() throws {
        let app = try launchCurrentGame(large: false, scenario: "unknown")
        defer { app.terminate() }
        try openPicker(app)
        let current = app.buttons["watch.pick.111"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        let value = try XCTUnwrap(current.value as? String)
        XCTAssertTrue(value.contains("Win probability unavailable"))
        XCTAssertTrue(value.contains("Probability observation time unavailable"))
        XCTAssertFalse(value.contains("64%"))
        XCTAssertFalse(value.contains("ago"))
        try captureComplete(current, in: app, name: "Unknown current game preserves unavailable reading and clock")
        print("WATCH_UI_CURRENT_GAME_UNKNOWN=PASS")
    }

    @MainActor
    func testFinalCurrentGameShowsScoreInsteadOfForecastAtAccessibilitySize() throws {
        let app = try launchCurrentGame(large: true, scenario: "final")
        defer { app.terminate() }
        try openPicker(app)
        let current = app.buttons["watch.pick.111"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        let value = try XCTUnwrap(current.value as? String)
        XCTAssertTrue(value.contains("Final score · 2–3"))
        XCTAssertTrue(value.contains("Score observed 1 hour ago"))
        XCTAssertFalse(value.contains("64%"))
        XCTAssertFalse(value.contains("win probability"))
        try captureComplete(current, in: app, name: "Final current game uses original score clock - accessibility5")
        print("WATCH_UI_CURRENT_GAME_FINAL_ACCESSIBILITY5=PASS")
    }

    @MainActor
    func testUnknownCurrentGameDoesNotInventProbabilityOrAgeAtAccessibilitySize() throws {
        let app = try launchCurrentGame(large: true, scenario: "unknown")
        defer { app.terminate() }
        try openPicker(app)
        let current = app.buttons["watch.pick.111"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        let value = try XCTUnwrap(current.value as? String)
        XCTAssertTrue(value.contains("Win probability unavailable"))
        XCTAssertTrue(value.contains("Probability observation time unavailable"))
        XCTAssertFalse(value.contains("64%"))
        XCTAssertFalse(value.contains("ago"))
        try captureComplete(current, in: app, name: "Unknown current game preserves unavailable reading and clock - accessibility5")
        print("WATCH_UI_CURRENT_GAME_UNKNOWN_ACCESSIBILITY5=PASS")
    }

    @MainActor
    func testIndependentStaleClocksAreCompactAndExplicitAtStandardSize() throws {
        let app = try launchCurrentGame(large: false)
        defer { app.terminate() }
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        XCTAssertEqual(app.descendants(matching: .any)["watch.away-score"].firstMatch.label,
                       "Los Angeles Dodgers, score 2")
        XCTAssertEqual(app.descendants(matching: .any)["watch.home-score"].firstMatch.label,
                       "San Francisco Giants, score 3")
        try captureComplete(probability, in: app, name: "Named probability before independent stale clocks - standard")
        for label in ["Score observed 1 hour ago", "Probability observed 3 hours ago"] {
            let text = app.staticTexts[label]
            XCTAssertTrue(text.waitForExistence(timeout: 15))
            XCTAssertEqual(text.label, label, "Full original clock remains available to accessibility")
            XCTAssertEqual(text.value as? String, "May be out of date")
            try captureComplete(text, in: app, name: "Compact clock - standard - " + label)
        }
        print("WATCH_UI_MAIN_STALE_STANDARD=PASS")
    }

    @MainActor
    func testSavedCurrentCardAndReturnPreserveIndependentClocksAtAccessibilitySize() throws {
        let app = try launchCurrentGame(large: true)
        defer { app.terminate() }
        // First launch writes the real selected-store snapshot through its101→111 response.
        XCTAssertTrue(app.staticTexts["Score observed 1 hour ago"].exists)
        XCTAssertTrue(app.staticTexts["Probability observed 3 hours ago"].exists)
        app.terminate()
        app.launchEnvironment["BAINLUCK_WATCH_UI_RESET"] = "0"
        app.launchEnvironment["BAINLUCK_WATCH_UI_OFFLINE"] = "1"
        app.launch()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let saved = XCTNSPredicateExpectation(predicate: NSPredicate(format:
            "exists == true AND label CONTAINS %@ AND label CONTAINS %@",
            "Saved reading. Refresh to confirm.", "Offline."), object: state)
        XCTAssertEqual(XCTWaiter.wait(for: [saved], timeout: 15), .completed)
        try openPicker(app)
        // Feed rows remain fixture-provided; detail is offline. This checks persistence,
        // not list connectivity. Store's previously proven101 alias remains selected.
        let current = try assertCurrent(app, id: 101)
        XCTAssertTrue((current.value as? String)?.contains("Saved reading. Refresh to confirm.") == true)
        XCTAssertEqual(app.staticTexts["watch.picker-heading"].value as? String, "accessibility5")
        try captureComplete(current, in: app, name: "Saved current card after real offline restart - accessibility5")
        try reveal(current, in: app)
        current.tap()
        XCTAssertFalse(app.buttons["watch.picker-cancel"].exists)
        XCTAssertTrue(state.label.contains("Saved reading. Refresh to confirm."))
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        XCTAssertEqual(probability.label, "San Francisco Giants win probability, 64%")
        let scoreAge = app.staticTexts["Score observed 1 hour ago"]
        let probabilityAge = app.staticTexts["Probability observed 3 hours ago"]
        XCTAssertTrue(scoreAge.exists)
        XCTAssertTrue(probabilityAge.exists)
        XCTAssertEqual(scoreAge.value as? String, "May be out of date")
        XCTAssertEqual(probabilityAge.value as? String, "May be out of date")
        try captureSavedReturnTop(in: app)
        try captureComplete(probability, in: app, name: "Returned saved named64 - accessibility5")
        try captureComplete(scoreAge, in: app, name: "Returned original score age1hour - accessibility5")
        try captureComplete(probabilityAge, in: app, name: "Returned original probability age3hours - accessibility5")
        print("WATCH_UI_CURRENT_GAME_SAVED_LARGE=PASS")
    }

    @MainActor
    private func captureSavedReturnTop(in app: XCUIApplication) throws {
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        let firstScore = app.descendants(matching: .any)["watch.away-score"].firstMatch
        var previousY: CGFloat?
        var stable = 0
        for _ in 0..<24 {
            let bounds = try viewport(in: app)
            let y = firstScore.frame.minY
            if let previousY, abs(y - previousY) < 1,
               bounds.contains(state.frame), state.isHittable, firstScore.isHittable {
                stable += 1
            } else { stable = 0 }
            if stable == 2 {
                capture(app, "Returned saved banner at stable natural top - accessibility5")
                return
            }
            previousY = y
            move(in: app, bounds: bounds, earlier: true, fraction: 0.50)
        }
        throw failure("Cannot establish saved return natural top", in: app)
    }

    @MainActor
    private func launchCurrentGame(large: Bool, scenario: String = "live", nativeCategory: String? = nil) throws -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["BAINLUCK_WATCH_UI_TEST": "1",
            "BAINLUCK_WATCH_UI_SUITE": UUID().uuidString, "BAINLUCK_WATCH_UI_RESET": "1",
            "BAINLUCK_WATCH_UI_CURRENT_GAME": scenario,
            "BAINLUCK_WATCH_UI_LARGE_TEXT": large ? "1" : "0"]
        if let nativeCategory {
            app.launchArguments = ["-UIPreferredContentSizeCategoryName", nativeCategory]
        }
        app.launch()
        let first = app.buttons["watch.pick.101"]
        XCTAssertTrue(first.waitForExistence(timeout: 20))
        try reveal(first, in: app)
        first.tap()
        XCTAssertTrue(app.descendants(matching: .any)["watch.game-state"].firstMatch.waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["watch.choose-another"].exists)
        return app
    }

    @MainActor
    private func openPicker(_ app: XCUIApplication) throws {
        let change = app.buttons["watch.choose-another"]
        try reveal(change, in: app)
        change.tap()
        XCTAssertTrue(app.buttons["watch.picker-cancel"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["watch.picker-heading"].waitForExistence(timeout: 15))
    }

    @MainActor
    private func assertCurrent(_ app: XCUIApplication, id: Int) throws -> XCUIElement {
        let current = app.buttons["watch.pick.\(id)"]
        XCTAssertTrue(current.waitForExistence(timeout: 15))
        XCTAssertTrue(current.isSelected)
        XCTAssertEqual(current.label, "Los Angeles Dodgers at San Francisco Giants. Live. Your game")
        let value = try XCTUnwrap(current.value as? String)
        XCTAssertTrue(value.contains("San Francisco Giants win probability, 64%"))
        XCTAssertTrue(value.contains("Probability observed 3 hours ago"))
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "watch.pick.")).allElementsBoundByIndex
        XCTAssertEqual(rows.first?.identifier, current.identifier)
        XCTAssertEqual(rows.filter(\.isSelected).count, 1)
        return current
    }

    @MainActor
    private func assertStatus(_ expected: String, in app: XCUIApplication) throws {
        let status = app.staticTexts["watch.picker-status"]
        let settled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND label == %@", expected), object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [settled], timeout: 15), .completed)
    }

    @MainActor
    private func refresh(_ app: XCUIApplication, expected: String) throws {
        let refresh = app.buttons["watch.picker-refresh"]
        try reveal(refresh, in: app)
        XCTAssertTrue(refresh.isEnabled)
        refresh.tap()
        try assertStatus(expected, in: app)
    }

    @MainActor
    private func assertSingleResultQualification(in app: XCUIApplication, label: String) throws {
        let roots = app.descendants(matching: .any).matching(identifier: "watch.game-state")
        guard roots.count == 1 else {
            throw failure("Expected exactly one identified result qualification", in: app)
        }
        let root = roots.element(boundBy: 0)
        XCTAssertEqual(root.label, label)
        let matchingLabel = NSPredicate(format: "label == %@", label)
        let children = root.children(matching: .any).matching(matchingLabel).allElementsBoundByIndex
        let topology = children.map {
            WatchHeaderLabelTopology.Child(frame: $0.frame, isStaticText: $0.elementType == .staticText,
                identifier: $0.identifier, descendantCount: $0.descendants(matching: .any).count)
        }
        guard WatchHeaderLabelTopology.isUnique(rootCount: roots.count, rootIsStaticText: root.elementType == .staticText,
            labelCount: app.descendants(matching: .any).matching(matchingLabel).count,
            rootFrame: root.frame, children: topology) else {
            throw failure("Result qualification has a separate copy or unexpected label topology", in: app)
        }
    }

    @MainActor
    private func viewport(in app: XCUIApplication) throws -> CGRect {
        let visible = app.scrollViews.allElementsBoundByIndex.filter {
            $0.isHittable && !$0.frame.intersection(app.frame).isEmpty
        }
        guard visible.count == 1 else { throw failure("Expected one visible scroll viewport", in: app) }
        var bounds = visible[0].frame.intersection(app.frame)
        let bars = app.navigationBars.allElementsBoundByIndex.filter { $0.exists && $0.frame.intersects(bounds) }
        if let chromeBottom = bars.map({ $0.frame.maxY }).max() {
            let top = max(bounds.minY, chromeBottom + 3)
            bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        }
        guard !bounds.isEmpty, !bounds.isNull, bounds.height > 30,
              bounds.minY.isFinite, bounds.maxY.isFinite else {
            throw failure("Invalid unobscured viewport", in: app)
        }
        return bounds.insetBy(dx: 2, dy: 3)
    }

    @MainActor
    private func handoffViewport(in app: XCUIApplication) throws -> CGRect {
        // Retained watchOS alert hierarchy uses a Table, not the game's ScrollView.
        let tables = app.tables.allElementsBoundByIndex.filter {
            $0.exists && $0.buttons["OK"].exists && $0.frame.intersects(app.frame)
        }
        guard tables.count == 1 else { throw failure("Expected one native Handoff alert table", in: app) }
        var bounds = tables[0].frame.intersection(app.frame)
        let bars = app.navigationBars.allElementsBoundByIndex.filter { $0.exists && $0.frame.intersects(bounds) }
        if let chromeBottom = bars.map({ $0.frame.maxY }).max() {
            let top = max(bounds.minY, chromeBottom + 3)
            bounds = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        }
        guard !bounds.isEmpty, !bounds.isNull, bounds.height > 30,
              bounds.minY.isFinite, bounds.maxY.isFinite else {
            throw failure("Invalid native Handoff viewport", in: app)
        }
        return bounds.insetBy(dx: 2, dy: 3)
    }

    @MainActor
    private func move(in app: XCUIApplication, bounds: CGRect, earlier: Bool, fraction: CGFloat) {
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: bounds.midX - app.frame.minX,
            dy: bounds.minY + bounds.height * (earlier ? 0.25 : 0.75) - app.frame.minY))
        let end = start.withOffset(CGVector(dx: 0, dy: bounds.height * (earlier ? fraction : -fraction)))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.3)
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, handoffTable: Bool = false) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        for _ in 0..<20 {
            let bounds = try handoffTable ? handoffViewport(in: app) : viewport(in: app)
            let frame = element.frame
            let visible = frame.intersection(bounds)
            if element.isHittable && !visible.isEmpty && visible.height >= min(30, frame.height) { return }
            let earlier = frame.minY < bounds.minY
            let distance = earlier ? bounds.minY - frame.minY : frame.maxY - bounds.maxY
            move(in: app, bounds: bounds, earlier: earlier, fraction: min(0.50, max(0.15, distance / bounds.height)))
        }
        throw failure("Unreachable \(element.identifier)", in: app)
    }

    @MainActor
    private func captureComplete(_ element: XCUIElement, in app: XCUIApplication, name: String, handoffTable: Bool = false) throws {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        var covered: CGFloat?
        for _ in 0..<24 {
            let bounds = try handoffTable ? handoffViewport(in: app) : viewport(in: app)
            let frame = element.frame
            // Native multiline alert text has an offscreen midpoint; geometry proves readable coverage.
            let readable = element.isHittable || (handoffTable && element.elementType == .staticText)
            // A contained footer can be fully readable without scrolling above mid-screen.
            // Keep the same hittability rule and the chrome-excluded, inset viewport.
            if readable && !frame.isEmpty && !frame.isNull &&
                frame.minX.isFinite && frame.minY.isFinite &&
                frame.maxX.isFinite && frame.maxY.isFinite && bounds.contains(frame) {
                capture(app, name + " - complete")
                return
            }
            if readable && frame.minY >= bounds.minY && frame.minY < bounds.midY {
                capture(app, name + " - top")
                covered = min(frame.height, bounds.maxY - frame.minY)
                if frame.maxY <= bounds.maxY { return }
                break
            }
            move(in: app, bounds: bounds, earlier: frame.minY < bounds.minY, fraction: 0.20)
        }
        guard var coveredEnd = covered else { throw failure("Missing readable top: \(name)", in: app) }
        for _ in 0..<24 {
            let bounds = try handoffTable ? handoffViewport(in: app) : viewport(in: app)
            let frame = element.frame
            let start = max(0, bounds.minY - frame.minY)
            let end = min(frame.height, bounds.maxY - frame.minY)
            if end > coveredEnd && (element.isHittable || (handoffTable && element.elementType == .staticText)) {
                XCTAssertLessThanOrEqual(start, coveredEnd + 1, "Captures must overlap below native chrome")
                capture(app, name + " - continuation")
                coveredEnd = end
                if frame.maxY <= bounds.maxY { return }
            }
            move(in: app, bounds: bounds, earlier: false, fraction: 0.25)
        }
        throw failure("Missing readable end: \(name)", in: app)
    }

    @MainActor
    private func capture(_ app: XCUIApplication, _ name: String) {
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = name
        screenshot.lifetime = .keepAlways
        add(screenshot)
        let geometry = XCTAttachment(string: app.debugDescription)
        geometry.name = name + " - hierarchy"
        geometry.lifetime = .keepAlways
        add(geometry)
    }

    @MainActor
    private func failure(_ message: String, in app: XCUIApplication) -> NSError {
        capture(app, message)
        XCTFail(message)
        return NSError(domain: "WatchCurrentGameJourney", code: 1,
                       userInfo: [NSLocalizedDescriptionKey: message])
    }
}
#endif
