#if DEBUG
import Foundation

/// Dedicated retained-reading refresh fixture. Never changes the shared fixture
/// or contacts the API; the same cached value preserves every producer clock.
actor WatchUpdatingUIFixture: WatchSelectedGameTransport {
    nonisolated static var enabled: Bool {
        WatchUIFixture.current != nil &&
            ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_UPDATING"] == "1"
    }

    private let fixture: WatchUIFixture
    private var cached: WatchSelectedGame?

    init(fixture: WatchUIFixture) { self.fixture = fixture }

    @MainActor static func makeStore(fixture: WatchUIFixture) -> WatchSelectedGameStore {
        WatchSelectedGameStore(transport: Self(fixture: fixture),
            defaults: UserDefaults(suiteName: fixture.suite)!)
    }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        if let cached, cached.id == eventID {
            // Long enough for bounded scrolling captures; the journey waits for
            // real completion instead of treating elapsed test time as success.
            try await Task.sleep(for: .seconds(60))
            try Task.checkCancellation()
            return cached
        }
        let game = try await fixture.fetch(eventID: eventID)
        try Task.checkCancellation()
        cached = game
        return game
    }
}
#endif
