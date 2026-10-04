#if !DEBUG
import Foundation
import XCTest

/// Opt-in hosted acceptance only. Release excludes the fixture transport.
final class LiveSelectedGameJourneyTests: XCTestCase {
    @MainActor
    func testProductionPickerSelectionSurvivesRelaunchAndRefreshes() async throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [:]
        app.launchArguments = []
        defer { app.terminate() }
        app.launch()
        let picker = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "watch.pick.")).firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 30), "UNPAID: production picker empty, unavailable, or did not load")
        XCTAssertFalse(app.buttons["watch.choose-another"].exists, "UNPAID: journey requires a fresh installation, not seeded selection")
        let pickerID = try XCTUnwrap(Int(picker.identifier.replacingOccurrences(of: "watch.pick.", with: "")))
        XCTAssertGreaterThan(pickerID, 0)
        let pickerLabel = picker.label
        let clock = ISO8601DateFormatter()
        clock.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let requestedAt = clock.string(from: Date())
        var request = URLRequest(url: try XCTUnwrap(URL(string: "https://api.bainluck.com/api/events/\(pickerID)")))
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        let (data, response) = try await session.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, "UNPAID: production detail request failed")
        let detail = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let canonicalID = try XCTUnwrap((detail["id"] as? NSNumber)?.intValue)
        let home = try XCTUnwrap(detail["home_team"] as? String)
        let away = try XCTUnwrap(detail["away_team"] as? String)
        XCTAssertGreaterThan(canonicalID, 0)
        XCTAssertFalse(home.isEmpty); XCTAssertFalse(away.isEmpty)
        XCTAssertTrue(pickerLabel.contains(home) && pickerLabel.contains(away), "UNPAID: picker and canonical production detail identity disagree")
        let apiAttachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        apiAttachment.name = "Production detail for tapped picker \(pickerID), canonical \(canonicalID)"
        apiAttachment.lifetime = .keepAlways
        add(apiAttachment)
        capture(app, "Production picker before tap")
        try reveal(picker, in: app)
        picker.tap()
        let state = app.descendants(matching: .any)["watch.game-state"].firstMatch
        XCTAssertTrue(state.waitForExistence(timeout: 30), "UNPAID: tapped selection did not render")
        try await waitForRefreshedState(state)
        try assertIdentity(home: home, away: away, in: app)
        let firstState = state.label
        let firstProbability = try reading(in: app, home: home, state: firstState)
        capture(app, "Production selected game before relaunch")
        app.terminate()
        // No reinstall, preferences writes, fixture environment, or selection seed.
        let relaunchedAt = clock.string(from: Date())
        app.launch()
        XCTAssertTrue(state.waitForExistence(timeout: 30), "UNPAID: selected game was not restored")
        try await waitForRefreshedState(state)
        try assertIdentity(home: home, away: away, in: app)
        let reopenedState = state.label
        let reopenedProbability = try reading(in: app, home: home, state: reopenedState)
        capture(app, "Retained production game after relaunch and refresh")
        let evidence: [String: Any] = [
            "schema_version": 1, "configuration": "Release", "fixture": false,
            "picker_id": pickerID, "canonical_id": canonicalID,
            "home_team": home, "away_team": away,
            "first_state": firstState, "reopened_state": reopenedState,
            "refreshed_after_relaunch": true,
            "first_probability": firstProbability, "reopened_probability": reopenedProbability,
            "production_detail": detail, "requested_at": requestedAt,
            "relaunched_at": relaunchedAt
        ]
        let encoded = try JSONSerialization.data(withJSONObject: evidence, options: [.sortedKeys])
        print("WATCH_LIVE_EVIDENCE=\(try XCTUnwrap(String(data: encoded, encoding: .utf8)))")
    }

    @MainActor
    private func waitForRefreshedState(_ state: XCUIElement) async throws {
        let fresh = NSPredicate(format: "exists == true AND NOT (label CONTAINS[c] %@) AND NOT (label CONTAINS[c] %@) AND NOT (label CONTAINS[c] %@) AND NOT (label CONTAINS[c] %@)", "Saved reading", "Couldn't", "Offline", "Try again")
        let ready = XCTNSPredicateExpectation(predicate: fresh, object: state)
        await fulfillment(of: [ready], timeout: 30)
        XCTAssertFalse(state.label.contains("Saved reading"), "UNPAID: restored reading never refreshed")
    }

    @MainActor
    private func assertIdentity(home: String, away: String, in app: XCUIApplication) throws {
        let homeScore = app.descendants(matching: .any)["watch.home-score"].firstMatch
        let awayScore = app.descendants(matching: .any)["watch.away-score"].firstMatch
        XCTAssertTrue(homeScore.waitForExistence(timeout: 15)); XCTAssertTrue(awayScore.exists)
        XCTAssertTrue(homeScore.label.contains(home)); XCTAssertTrue(awayScore.label.contains(away))
        try reveal(homeScore, in: app)
        capture(app, "Retained named home side")
        try reveal(awayScore, in: app)
        capture(app, "Retained named away side")
    }

    @MainActor
    private func reading(in app: XCUIApplication, home: String, state: String) throws -> String {
        let probability = app.descendants(matching: .any)["watch.home-probability"].firstMatch
        if probability.exists {
            XCTAssertTrue(probability.label.contains(home) && probability.label.contains("%"), "UNPAID: probability must name its side")
            XCTAssertFalse(state.contains("Final") || state.contains("Closed"), "UNPAID: settled state displayed a forecast")
            try reveal(probability, in: app)
            return probability.label
        }
        if state.contains("Final") || state.contains("Closed") {
            return "No forecast: \(state)"
        }
        let unavailable = app.staticTexts["Win probability unavailable"]
        XCTAssertTrue(unavailable.exists, "UNPAID: missing probability lacks an honest explanation")
        try reveal(unavailable, in: app)
        return unavailable.label
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
        capture(app, "UNPAID unreachable \(element.identifier)")
        XCTFail("UNPAID: reading/control is not fully reachable")
        throw NSError(domain: "WatchLiveJourney", code: 1)
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
