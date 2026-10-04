#if DEBUG
import Foundation

/// Deterministic UI-test data, excluded from Release. Never contacts the public API.
/// A separate defaults domain keeps fixture selections out of the reader's data.
nonisolated struct WatchUIFixture: WatchSelectedGameTransport, WatchGamePickerTransport {
    let offline: Bool
    let suite: String
    var rounding = false

    static let current: WatchUIFixture? = {
        let environment = ProcessInfo.processInfo.environment
        guard environment["BAINLUCK_WATCH_UI_TEST"] == "1",
              let token = environment["BAINLUCK_WATCH_UI_SUITE"],
              UUID(uuidString: token) != nil else { return nil }
        let suite = "com.bainluck.watch.ui-test.\(token)"
        if environment["BAINLUCK_WATCH_UI_RESET"] == "1" {
            UserDefaults(suiteName: suite)?.removePersistentDomain(forName: suite)
        }
        return Self(offline: environment["BAINLUCK_WATCH_UI_OFFLINE"] == "1", suite: suite,
                    rounding: environment["BAINLUCK_WATCH_UI_ROUNDING"] == "1")
    }()

    func makeStore() -> WatchSelectedGameStore {
        WatchSelectedGameStore(transport: self, defaults: UserDefaults(suiteName: suite)!)
    }

    func fetchGames() async throws -> WatchGamePickerBatch {
        if offline { throw URLError(.notConnectedToInternet) }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let standard = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live"}},{"type":"event","score":80,"data":{"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled"}}],"has_more":false}
        """
        let roundingFeed = """
        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"Tampa Bay Rays","away_team":"Yankees","status":"live"}},{"type":"event","score":80,"data":{"id":202,"home_team":"Chelsea","away_team":"Arsenal","status":"scheduled"}}],"has_more":false}
        """
        let feed = try decoder.decode(WatchFeedResponse.self, from: Data((rounding ? roundingFeed : standard).utf8))
        return WatchGamePickerBatch(feed: feed)
    }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        if offline { throw URLError(.notConnectedToInternet) }
        guard [101, 202].contains(eventID) else { throw WatchSelectedGameRequestError.unavailable }
        let first = eventID == 101
        let time = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-60))
        var payload: [String: Any] = [
            "id": eventID,
            "home_team": first ? "San Francisco Giants" : "Buffalo Bills",
            "away_team": first ? "Los Angeles Dodgers" : "Kansas City Chiefs",
            "status": first ? "live" : "scheduled",
            "home_score": first ? 3 : 0, "away_score": first ? 2 : 0,
            "hero_probability": first ? 0.64 : 0.55,
            "score_observed_at": time, "hero_probability_observed_at": time
        ]
        if rounding {
            payload["home_team"] = first ? "Tampa Bay Rays" : "Chelsea"
            payload["away_team"] = first ? "Yankees" : "Arsenal"
            payload["sport"] = first ? "baseball_mlb" : "soccer_epl"
            payload["hero_probability"] = 0.455
            payload["hero_probability_away"] = 0.545
        }
        return try JSONDecoder().decode(WatchSelectedGame.self, from: JSONSerialization.data(withJSONObject: payload))
    }
}
#endif
