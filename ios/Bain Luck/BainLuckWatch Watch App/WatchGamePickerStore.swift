import Combine
import Foundation

nonisolated struct WatchGamePickerBatch: Sendable {
    let games: [WatchFeedEvent]
    let omittedGameCount: Int

    init(games: [WatchFeedEvent], omittedGameCount: Int = 0) {
        self.games = games
        self.omittedGameCount = omittedGameCount
    }

    init(feed: WatchFeedResponse) {
        games = feed.items.compactMap(\.event)
        omittedGameCount = feed.items.filter { $0.type == "event" && $0.event == nil }.count
    }
}

nonisolated protocol WatchGamePickerTransport: Sendable {
    func fetchGames() async throws -> WatchGamePickerBatch
}

/// A bounded Discover list, never a claim to be the complete sports schedule.
/// Keep prior options on failed refresh and reject responses from older requests.
final class WatchGamePickerStore: ObservableObject {
    @Published private(set) var games: [WatchFeedEvent] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var omittedGameCount = 0
    private let transport: any WatchGamePickerTransport
    private var revision = 0

    init(transport: any WatchGamePickerTransport) { self.transport = transport }

    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        revision += 1
        let requestRevision = revision
        isLoading = true
        defer {
            if requestRevision == revision { isLoading = false }
        }
        do {
            let received = try await transport.fetchGames()
            try Task.checkCancellation()
            guard requestRevision == revision else { return }
            var seen = Set<Int>()
            var omitted = received.omittedGameCount
            games = received.games.filter { game in
                guard game.id > 0,
                      let home = game.homeTeam?.trimmingCharacters(in: .whitespacesAndNewlines), !home.isEmpty,
                      let away = game.awayTeam?.trimmingCharacters(in: .whitespacesAndNewlines), !away.isEmpty else {
                    omitted += 1
                    return false
                }
                return seen.insert(game.id).inserted
            }
            omittedGameCount = omitted
            errorMessage = nil
        } catch {
            guard requestRevision == revision else { return }
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            errorMessage = "Couldn't refresh available games. Try again."
        }
    }
}
