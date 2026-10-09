#if DEBUG
import Foundation

/// Opt-in full selected-game specimens for adaptive score layout; no network or cadence change.
nonisolated struct WatchScoreLayoutUIFixture: WatchSelectedGameTransport {
    let scenario: String
    private let capturedAt = Date()

    static var current: Self? {
        guard WatchUIFixture.current != nil,
              let scenario = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_SCORE_LAYOUT"],
              ["short-live", "compact-final", "long-final", "long-live", "long-clock", "missing-final", "probability-zero", "probability-hundred", "scheduled-no-score", "scheduled-no-time", "scheduled-with-score", "unknown-status-with-start", "missing-status-with-start", "final-home-win", "final-away-win", "final-score-tie", "final-negative-score", "completed-home-win", "selected-closed", "selected-unknown-probability", "long-unknown-probability", "live-missing-both", "live-missing-away", "live-missing-home"].contains(scenario) else { return nil }
        return Self(scenario: scenario)
    }

    @MainActor func makeStore(fixture: WatchUIFixture) -> WatchSelectedGameStore {
        let store = WatchSelectedGameStore(transport: self,
            defaults: UserDefaults(suiteName: fixture.suite)!)
        store.select(eventID: 101)
        return store
    }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        try Task.checkCancellation()
        guard eventID == 101 else { throw WatchSelectedGameRequestError.unavailable }
        // Opt-in saved closed-screen journey uses the real store restore path.
        if scenario == "selected-closed" || scenario.hasPrefix("scheduled-") || scenario == "final-home-win",
           ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_OFFLINE"] == "1" {
            throw URLError(.notConnectedToInternet)
        }
        let long = scenario == "long-final" || scenario == "long-live" || scenario == "long-unknown-probability"
        let formatter = ISO8601DateFormatter()
        var payload: [String: Any] = [
            "id": 101,
            "home_team": long ? "Association Sportive de Saint-Étienne Full Canonical Name" : "Buffalo Bills",
            "away_team": long ? "Club de Football Long Complete Opponent Name" : "Kansas City Chiefs",
            "status": scenario == "short-live" || scenario == "long-live" || scenario == "long-clock" || scenario.hasPrefix("probability-") ? "live" : "final",
            "home_score": 0, "away_score": 12,
            "score_observed_at": formatter.string(from: capturedAt.addingTimeInterval(-3660)),
            "hero_probability": 0.64,
            "hero_probability_observed_at": formatter.string(from: capturedAt.addingTimeInterval(-10860))
        ]
        if scenario.hasPrefix("scheduled-") {
            payload["status"] = "scheduled"
            payload["commence_time"] = "2026-10-09T02:00:00Z"
            if scenario != "scheduled-with-score" {
                payload.removeValue(forKey: "home_score")
                payload.removeValue(forKey: "away_score")
                payload.removeValue(forKey: "score_observed_at")
            }
            if scenario == "scheduled-no-time" { payload.removeValue(forKey: "commence_time") }
        }
        if scenario == "unknown-status-with-start" || scenario == "missing-status-with-start" {
            payload["commence_time"] = "2026-10-09T02:00:00Z"
            if scenario == "unknown-status-with-start" { payload["status"] = "mystery" }
            else { payload.removeValue(forKey: "status") }
            // Retain genuine0/12 scores; the timestamp must not infer a scheduled state.
        }
        // Confirmed-final presentation specimens reuse existing typed score fields.
        if scenario == "final-home-win" || scenario == "completed-home-win" {
            payload["home_score"] = 12
            payload["away_score"] = 0
        }
        if scenario == "completed-home-win" { payload["status"] = "completed" }
        if scenario == "final-score-tie" { payload["home_score"] = 2; payload["away_score"] = 2 }
        if scenario == "final-negative-score" { payload["home_score"] = -1 }
        // MISSING_LIVE_SCORE_BEGIN
        if ["live-missing-both", "live-missing-away", "live-missing-home"].contains(scenario) {
            payload["status"] = "live"
            if scenario != "live-missing-home" { payload.removeValue(forKey: "away_score") }
            if scenario != "live-missing-away" { payload.removeValue(forKey: "home_score") }
            // Retain the supplied probability and both independent observation timestamps.
        }
        // MISSING_LIVE_SCORE_END
        // SELECTED_BOUNDARIES_BEGIN
        if scenario == "selected-closed" {
            // Preserve supplied0/12 and64% with independent original clocks.
            // Closed is not a verified final result and must suppress this forecast.
            payload["status"] = "closed"
        }
        if scenario == "selected-unknown-probability" || scenario == "long-unknown-probability" {
            payload["status"] = "live"
            payload.removeValue(forKey: "hero_probability")
            // A supplied probability timestamp cannot fabricate a missing value.
        }
        // SELECTED_BOUNDARIES_END
        if scenario == "long-clock" {
            payload["espn"] = [
                "period": "4th Quarter",
                "game_clock": "12:34",
            ]
        }
        if scenario == "compact-final" {
            payload["home_team"] = "Chelsea"
            payload["away_team"] = "Arsenal"
        }
        if scenario == "probability-zero" { payload["hero_probability"] = 0.0 }
        if scenario == "probability-hundred" { payload["hero_probability"] = 1.0 }
        if scenario == "missing-final" { payload.removeValue(forKey: "home_score") }
        return try JSONDecoder().decode(WatchSelectedGame.self,
            from: JSONSerialization.data(withJSONObject: payload))
    }
}
#endif
