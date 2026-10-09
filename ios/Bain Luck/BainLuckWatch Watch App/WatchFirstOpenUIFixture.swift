#if DEBUG
import Foundation

/// Explicitly suspended detail transport for first-open UI acceptance; no delays,
/// provider requests, polling timers or changes to previously accepted fixtures.
nonisolated struct WatchFirstOpenUITransport: WatchSelectedGameTransport, WatchGamePickerTransport {
    func fetchGames() async throws -> WatchGamePickerBatch {
        try await WatchFirstOpenUIFixture.shared.fetchGames()
    }
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        try await WatchFirstOpenUIFixture.shared.fetch(eventID: eventID)
    }
}

actor WatchFirstOpenUIFixture {
    nonisolated static let shared = WatchFirstOpenUIFixture()
    nonisolated static var enabled: Bool {
        WatchUIFixture.current != nil && ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_FIRST_OPEN"] != nil
    }
    private struct Pending {
        let eventID: Int
        let continuation: CheckedContinuation<WatchSelectedGame, Error>
    }
    private var pending: [UUID: Pending] = [:]
    private let scoreTime = Date().addingTimeInterval(-3660)
    private let probabilityTime = Date().addingTimeInterval(-10860)

    @MainActor static func makeStore(fixture: WatchUIFixture) -> WatchSelectedGameStore {
        let store = WatchSelectedGameStore(transport: WatchFirstOpenUITransport(),
            defaults: UserDefaults(suiteName: fixture.suite)!)
        if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_FIRST_OPEN"] == "missing" {
            store.select(eventID: 303)
        }
        return store
    }

    func fetchGames() throws -> WatchGamePickerBatch {
        try Task.checkCancellation()
        let data = Data(#"{"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"scheduled","commence_time":"2026-10-09T02:00:00Z","home_score":9,"away_score":9,"current_odds":{"home_probability":0.99}}},{"type":"event","score":80,"data":{"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled","current_odds":{"home_probability":0.99}}}],"has_more":false}"#.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return WatchGamePickerBatch(feed: try decoder.decode(WatchFeedResponse.self, from: data))
    }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        let request = UUID()
        print("WATCH_FIRST_OPEN_REQUEST=\(eventID)")
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                guard !Task.isCancelled else {
                    continuation.resume(throwing: CancellationError())
                    return
                }
                pending[request] = Pending(eventID: eventID, continuation: continuation)
            }
        } onCancel: {
            Task { await self.cancel(request) }
        }
    }

    private func cancel(_ request: UUID) {
        if let cancelled = pending.removeValue(forKey: request) {
            print("WATCH_FIRST_OPEN_CANCELLED=\(cancelled.eventID)")
            cancelled.continuation.resume(throwing: CancellationError())
        }
    }

    func resolve(eventID: Int, fail: Bool) {
        let requests = pending.filter { $0.value.eventID == eventID }
        for (id, request) in requests {
            pending.removeValue(forKey: id)
            print("WATCH_FIRST_OPEN_RESOLVED=\(eventID),failed=\(fail)")
            if fail {
                request.continuation.resume(throwing: URLError(.notConnectedToInternet))
                continue
            }
            do {
                let first = eventID == 101
                let formatter = ISO8601DateFormatter()
                let payload: [String: Any] = [
                    "id": eventID, "home_team": first ? "San Francisco Giants" : "Buffalo Bills",
                    "away_team": first ? "Los Angeles Dodgers" : "Kansas City Chiefs",
                    "status": "live", "home_score": 3, "away_score": 2,
                    "hero_probability": first ? 0.64 : 0.55,
                    "score_observed_at": formatter.string(from: scoreTime),
                    "hero_probability_observed_at": formatter.string(from: probabilityTime)
                ]
                let game = try JSONDecoder().decode(WatchSelectedGame.self,
                    from: JSONSerialization.data(withJSONObject: payload))
                request.continuation.resume(returning: game)
            } catch { request.continuation.resume(throwing: error) }
        }
    }
}
#endif
