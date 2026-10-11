#if DEBUG
import Foundation

/// Deterministic UI-test data, excluded from Release. Never contacts the public API.
/// A separate defaults domain keeps fixture selections out of the reader's data.
nonisolated struct WatchUIFixture: WatchSelectedGameTransport, WatchGamePickerTransport {
    static let processID = UUID().uuidString
    let offline: Bool
    let suite: String
    var rounding = false
    var launchReceipt = false
    var sharedPublication = false
    var circularIdentity = false
    var rectangularScoreScenario: String? = nil
    var pickerNetworkFailure: WatchPickerNetworkFixture?
    var pickerAlias: WatchPickerAliasFixture?
    var fixedObservation: Date? = nil
    var pickerDesign: WatchPickerCurrentGameFixture?

    static let current: WatchUIFixture? = {
        var environment = ProcessInfo.processInfo.environment
        // XCTest URL launches on watchOS do not preserve launchEnvironment.
        // A normal fixture launch can seed one subsequent cold OS URL launch.
        // Consume immediately, so ordinary later launches cannot inherit fixtures.
        let seedKey = "watch.ui-test.one-shot-url-fixture"
        let seed = UserDefaults.standard.dictionary(forKey: seedKey) as? [String: String]
        UserDefaults.standard.removeObject(forKey: seedKey)
        if environment["BAINLUCK_WATCH_UI_TEST"] != "1", let seed {
            environment = seed
        } else if environment["BAINLUCK_WATCH_UI_SEED_URL"] == "1",
                  environment["BAINLUCK_WATCH_UI_TEST"] == "1",
                  let token = environment["BAINLUCK_WATCH_UI_SUITE"], UUID(uuidString: token) != nil {
            let keys = ["BAINLUCK_WATCH_UI_TEST", "BAINLUCK_WATCH_UI_SUITE",
                        "BAINLUCK_WATCH_UI_RESET", "BAINLUCK_WATCH_UI_OFFLINE",
                        "BAINLUCK_WATCH_UI_ROUNDING", "BAINLUCK_WATCH_UI_LAUNCH_RECEIPT",
                        "BAINLUCK_WATCH_UI_SHARED_PUBLICATION", "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY",
                        "BAINLUCK_WATCH_UI_FIXED_OBSERVATION", "BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_HOST"]
            UserDefaults.standard.set(environment.filter { keys.contains($0.key) }, forKey: seedKey)
        }
        guard environment["BAINLUCK_WATCH_UI_TEST"] == "1",
              let token = environment["BAINLUCK_WATCH_UI_SUITE"],
              UUID(uuidString: token) != nil else { return nil }
        let suite = "com.bainluck.watch.ui-test.\(token)"
        if environment["BAINLUCK_WATCH_UI_RESET"] == "1",
           environment["BAINLUCK_WATCH_UI_SEED_URL"] != "1" {
            UserDefaults(suiteName: suite)?.removePersistentDomain(forName: suite)
        }
        return Self(offline: environment["BAINLUCK_WATCH_UI_OFFLINE"] == "1", suite: suite,
                    rounding: environment["BAINLUCK_WATCH_UI_ROUNDING"] == "1",
                    launchReceipt: environment["BAINLUCK_WATCH_UI_LAUNCH_RECEIPT"] == "1",
                    sharedPublication: environment["BAINLUCK_WATCH_UI_SHARED_PUBLICATION"] == "1",
                    circularIdentity: environment["BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY"] == "1",
                    rectangularScoreScenario: environment["BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_HOST"].flatMap {
                        ["score", "final", "away-final", "tie", "zero"].contains($0) ? $0 : nil
                    },
                    pickerNetworkFailure: environment["BAINLUCK_WATCH_UI_PICKER_NETWORK"].map { WatchPickerNetworkFixture(scenario: $0) },
                    pickerAlias: environment["BAINLUCK_WATCH_UI_PICKER_ALIAS"] == "1" ? WatchPickerAliasFixture() : nil,
                    fixedObservation: environment["BAINLUCK_WATCH_UI_FIXED_OBSERVATION"].flatMap { ISO8601DateFormatter().date(from: $0) },
                    pickerDesign: environment["BAINLUCK_WATCH_UI_CURRENT_GAME"].map { WatchPickerCurrentGameFixture(scenario: $0) })
    }()

    @MainActor func makeStore() -> WatchSelectedGameStore {
        // Opt in only for a dedicated simulator's actual WidgetKit journey.
        // Ordinary fixtures retain their no-op publisher and isolated defaults.
        let publish: (WatchSelectedGame?, Date?) -> Void = { game, savedAt in
            if rectangularScoreScenario != nil {
                let defaults = UserDefaults(suiteName: suite)
                if let game {
                    // DEBUG receipt of the actual store callback, never a fixture-fed expected result.
                    // Per-process identity rejects a receipt left by the pre-termination process.
                    let receipt: [String: Any] = [
                        "process_id": Self.processID, "event_id": game.id,
                        "home_name": game.homeTeam, "away_name": game.awayTeam,
                        "home_score": game.homeScore.map { $0 as Any } ?? NSNull(),
                        "away_score": game.awayScore.map { $0 as Any } ?? NSNull(),
                        "score_observed_at": game.scoreObservedAt.map { $0.timeIntervalSince1970 as Any } ?? NSNull(),
                        "probability_absent": game.homeProbability == nil,
                        "status": game.status ?? ""
                    ]
                    if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]),
                       let text = String(data: data, encoding: .utf8) {
                        defaults?.set(text, forKey: "watch.ui-test.rectangular-score-store-receipt")
                    } else {
                        defaults?.removeObject(forKey: "watch.ui-test.rectangular-score-store-receipt")
                    }
                } else {
                    defaults?.removeObject(forKey: "watch.ui-test.rectangular-score-store-receipt")
                }
            }
            if sharedPublication {
                WatchComplicationPublisher.publish(game: game, savedAt: savedAt)
            }
        }
        return WatchSelectedGameStore(transport: self, defaults: UserDefaults(suiteName: suite)!, publish: publish)
    }

    var rectangularScoreStoreReceipt: String {
        guard rectangularScoreScenario != nil else { return "" }
        return UserDefaults(suiteName: suite)?.string(forKey: "watch.ui-test.rectangular-score-store-receipt") ?? ""
    }

    func fetchGames() async throws -> WatchGamePickerBatch {
        if let pickerDesign { return try await pickerDesign.fetchGames() }
        try await pickerNetworkFailure?.beforeFetch()
        // Alias journeys keep scripted rows available while the detail transport is
        // offline. They test retained selection, not feed connectivity or caching.
        if offline && pickerAlias == nil { throw URLError(.notConnectedToInternet) }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let standard = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live"}},{"type":"event","score":80,"data":{"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled"}}],"has_more":false}
        """
        let roundingFeed = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"Tampa Bay Rays","away_team":"Yankees","status":"live"}},{"type":"event","score":80,"data":{"id":202,"home_team":"Chelsea","away_team":"Arsenal","status":"scheduled"}}],"has_more":false}
        """
        let aliasFeed = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live"}},{"type":"event","score":80,"data":{"id":202,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"scheduled"}}],"has_more":false}
        """
        let scoreFeed = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"Association Sportive de Saint-Étienne Full Canonical Name","away_team":"Club de Football Long Complete Opponent Name","status":"live"}}],"has_more":false}
        """
        let source = rectangularScoreScenario != nil ? scoreFeed : (pickerAlias != nil ? aliasFeed : (rounding ? roundingFeed : standard))
        let feed = try decoder.decode(WatchFeedResponse.self, from: Data(source.utf8))
        return WatchGamePickerBatch(feed: feed)
    }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        if offline { throw URLError(.notConnectedToInternet) }
        if let pickerDesign { return try await pickerDesign.fetch(eventID: eventID) }
        if let pickerAlias { return try await pickerAlias.fetch(eventID: eventID) }
        guard [101, 202].contains(eventID) else { throw WatchSelectedGameRequestError.unavailable }
        let first = eventID == 101
        let time = ISO8601DateFormatter().string(from: fixedObservation ?? Date().addingTimeInterval(-60))
        var payload: [String: Any] = [
            "id": eventID,
            "home_team": first ? "San Francisco Giants" : "Buffalo Bills",
            "away_team": first ? "Los Angeles Dodgers" : "Kansas City Chiefs",
            "status": first ? "live" : "scheduled",
            "home_score": first ? 3 : 0, "away_score": first ? 2 : 0,
            "hero_probability": first ? 0.64 : 0.55,
            "score_observed_at": time, "hero_probability_observed_at": time
        ]
        if circularIdentity && first {
            payload["home_team_data"] = ["team_id": 1, "abbreviation": "SF"]
            payload["away_team_data"] = ["team_id": 2, "abbreviation": "LA"]
        }
        if rounding {
            payload["home_team"] = first ? "Tampa Bay Rays" : "Chelsea"
            payload["away_team"] = first ? "Yankees" : "Arsenal"
            payload["sport"] = first ? "baseball_mlb" : "soccer_epl"
            payload["hero_probability"] = 0.455
            payload["hero_probability_away"] = 0.545
        }
        if first, let scenario = rectangularScoreScenario {
            payload["home_team"] = "Association Sportive de Saint-Étienne Full Canonical Name"
            payload["away_team"] = "Club de Football Long Complete Opponent Name"
            payload["home_team_data"] = ["team_id": 1, "abbreviation": "SF"]
            payload["away_team_data"] = ["team_id": 2, "abbreviation": "LA"]
            payload["sport"] = "baseball_mlb"
            payload["status"] = ["final", "away-final", "tie"].contains(scenario) ? "completed" : "live"
            payload["home_score"] = scenario == "away-final" || scenario == "tie" ? 2 : 4
            payload["away_score"] = scenario == "away-final" ? 4 : scenario == "zero" ? 0 : 2
            payload.removeValue(forKey: "hero_probability")
            payload.removeValue(forKey: "hero_probability_away")
            payload.removeValue(forKey: "hero_probability_observed_at")
            // score_observed_at retains the supplied independent fixedObservation.
        }
        return try JSONDecoder().decode(WatchSelectedGame.self, from: JSONSerialization.data(withJSONObject: payload))
    }
}
/// Only the second picker request fails: initial options and later recovery
/// both use the normal deterministic fixture, with no timers or public network.
actor WatchPickerNetworkFixture {
    private var requests = 0
    private let failure: URLError.Code?

    init(scenario: String) {
        failure = ["offline": URLError.Code.notConnectedToInternet,
                   "interrupted": .networkConnectionLost, "timeout": .timedOut][scenario]
    }

    func beforeFetch() throws {
        requests += 1
        if requests == 2, let failure { throw URLError(failure) }
    }
}
/// One real store success establishes 101→111. Later requests cannot repair a
/// lost reading. No snapshot/defaults injection: production persistence owns it.
actor WatchPickerAliasFixture {
    private var resolved = false

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        try Task.checkCancellation()
        guard !resolved else { throw URLError(.notConnectedToInternet) }
        guard eventID == 101 else { throw WatchSelectedGameRequestError.unavailable }
        let formatter = ISO8601DateFormatter()
        let now = Date()
        let payload: [String: Any] = [
            "id": 111, "home_team": "San Francisco Giants", "away_team": "Los Angeles Dodgers",
            "status": "live", "home_score": 3, "away_score": 2,
            "hero_probability": 0.64, "hero_probability_away": 0.36,
            "score_observed_at": formatter.string(from: now.addingTimeInterval(-3660)),
            "hero_probability_observed_at": formatter.string(from: now.addingTimeInterval(-10860))
        ]
        let result = try JSONDecoder().decode(WatchSelectedGame.self,
            from: JSONSerialization.data(withJSONObject: payload))
        try Task.checkCancellation()
        resolved = true
        return result
    }
}

/// Opt-in visual design journey. Real store selection establishes 101→111;
/// list omissions, failure and empty response never write selected snapshots.
actor WatchPickerCurrentGameFixture {
    private var requests = 0
    private let scenario: String
    private let scoreTime = Date().addingTimeInterval(-3660)
    private let probabilityTime = Date().addingTimeInterval(-10860)

    init(scenario: String) { self.scenario = scenario }

    func fetchGames() throws -> WatchGamePickerBatch {
        try Task.checkCancellation()
        requests += 1
        if requests == 3 { throw URLError(.notConnectedToInternet) }
        let first = #"{"type":"event","score":90,"data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live"}}"#
        let second = #"{"type":"event","score":80,"data":{"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled"}}"#
        let datedSecond = scenario == "scheduled-time"
            ? second.replacingOccurrences(of: "\"status\":\"scheduled\"", with: "\"status\":\"scheduled\",\"commence_time\":\"2026-10-09T02:00:00Z\"")
            : second

        let coloredSecond = scenario == "team-color"
            ? datedSecond.replacingOccurrences(of: "\"status\":\"scheduled\"", with: "\"status\":\"scheduled\",\"away_team_data\":{\"primary_color\":\"#E31837\"},\"home_team_data\":{\"primary_color\":\"#00338D\"}")
            : datedSecond
        // MAIN_SCORE_COLOR_FEED_BEGIN
        let scoreColorSecond: String
        if scenario == "team-color-invalid" {
            scoreColorSecond = datedSecond.replacingOccurrences(of: ##""status":"scheduled""##,
                with: ##""status":"scheduled","away_team_data":{"primary_color":"not-a-color"},"home_team_data":{"primary_color":"#12"}"##)
        } else if scenario == "team-color-long" {
            scoreColorSecond = datedSecond.replacingOccurrences(of: ##""status":"scheduled""##,
                with: ##""status":"scheduled","away_team_data":{"primary_color":"#E31837"},"home_team_data":{"primary_color":"#00338D"}"##)
                .replacingOccurrences(of: "Kansas City Chiefs", with: "Club de Football Long Complete Opponent Name")
                .replacingOccurrences(of: "Buffalo Bills", with: "Association Sportive de Saint-Étienne Full Canonical Name")
        } else {
            scoreColorSecond = coloredSecond
        }
        let scoreColorFirst = scenario == "team-color-alias"
            ? first.replacingOccurrences(of: ##""status":"live""##,
                with: ##""status":"live","away_team_data":{"primary_color":"#E31837"},"home_team_data":{"primary_color":"#00338D"}"##)
            : first
        // MAIN_SCORE_COLOR_FEED_END
        let malformed = #"{"type":"event","score":90,"data":{"id":101}}"#
        let items: String
        if requests == 2 { items = malformed + "," + scoreColorSecond }
        else if requests == 4 { items = "" }
        else { items = scoreColorFirst + "," + scoreColorSecond }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(WatchFeedResponse.self,
            from: Data("{\"items\":[\(items)],\"has_more\":false}".utf8))
        return WatchGamePickerBatch(feed: feed)
    }

    func fetch(eventID: Int) throws -> WatchSelectedGame {
        try Task.checkCancellation()
        if requests == 3 || requests == 4 { throw URLError(.notConnectedToInternet) }
        guard [101, 111, 202].contains(eventID) else { throw WatchSelectedGameRequestError.unavailable }
        let first = eventID != 202
        let formatter = ISO8601DateFormatter()
        var payload: [String: Any] = [
            "id": first ? 111 : 202,
            "home_team": first ? "San Francisco Giants" : "Buffalo Bills",
            "away_team": first ? "Los Angeles Dodgers" : "Kansas City Chiefs",
            "status": first ? "live" : "scheduled",
            "home_score": first ? 3 : 0, "away_score": first ? 2 : 0,
            "hero_probability": first ? 0.64 : 0.55,
            "score_observed_at": formatter.string(from: scoreTime),
            "hero_probability_observed_at": formatter.string(from: probabilityTime)
        ]
        // MAIN_SCORE_COLOR_DETAIL_BEGIN
        if !first && scenario == "team-color-long" {
            payload["away_team"] = "Club de Football Long Complete Opponent Name"
            payload["home_team"] = "Association Sportive de Saint-Étienne Full Canonical Name"
        }
        // MAIN_SCORE_COLOR_DETAIL_END
        if !first && scenario == "scheduled-time" {
            payload["commence_time"] = "2026-10-09T02:00:00Z"
        }
        if first && scenario == "final" { payload["status"] = "final" }
        if first && scenario == "unknown" {
            for key in ["status", "hero_probability", "hero_probability_observed_at", "score_observed_at"] {
                payload.removeValue(forKey: key)
            }
        }
        return try JSONDecoder().decode(WatchSelectedGame.self,
            from: JSONSerialization.data(withJSONObject: payload))
    }
}
#endif
