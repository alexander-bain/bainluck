import Combine
import Foundation

nonisolated protocol WatchSelectedGameTransport: Sendable {
    func fetch(eventID: Int) async throws -> WatchSelectedGame
}

nonisolated struct WatchSelectedGameHTTPTransport: WatchSelectedGameTransport {
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        let url = URL(string: "https://api.bainluck.com/api/events/\(eventID)")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(WatchSelectedGame.self, from: data)
    }
}

/// Persist one last-good public reading without changing its observation clocks.
/// Each request is fenced against selection/refresh races.
final class WatchSelectedGameStore: ObservableObject {
    @Published private(set) var selectedEventID: Int?
    @Published private(set) var game: WatchSelectedGame?
    @Published private(set) var fetchedAt: Date?
    @Published private(set) var isRefreshing = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var isRestoredReading = false
    private let transport: any WatchSelectedGameTransport
    private let defaults: UserDefaults
    private let now: () -> Date
    private var revision = 0
    private var consecutiveFailures = 0
    private static let selectionKey = "bainluck_watch_selected_event_id"

    private static let snapshotKey = "bainluck_watch_selected_game_snapshot_v1"
    private struct Snapshot: Codable {
        let version: Int
        let game: WatchSelectedGame
        let fetchedAt: Date
    }

    init(transport: any WatchSelectedGameTransport = WatchSelectedGameHTTPTransport(),
         defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.transport = transport
        self.defaults = defaults
        self.now = now
        let stored = defaults.integer(forKey: Self.selectionKey)
        selectedEventID = stored > 0 ? stored : nil
        if let data = defaults.data(forKey: Self.snapshotKey),
           let snapshot = try? JSONDecoder().decode(Snapshot.self, from: data),
           snapshot.version == 1, snapshot.game.id == selectedEventID {
            game = snapshot.game
            fetchedAt = snapshot.fetchedAt
            isRestoredReading = true
        } else {
            defaults.removeObject(forKey: Self.snapshotKey)
        }
    }

    @MainActor func select(eventID: Int) {
        guard eventID > 0, eventID != selectedEventID else { return }
        revision += 1
        consecutiveFailures = 0
        selectedEventID = eventID
        defaults.set(eventID, forKey: Self.selectionKey)
        defaults.removeObject(forKey: Self.snapshotKey)
        isRestoredReading = false
        game = nil
        fetchedAt = nil
        errorMessage = nil
        isRefreshing = false
    }

    @MainActor func clearSelection() {
        revision += 1
        consecutiveFailures = 0
        selectedEventID = nil
        defaults.removeObject(forKey: Self.selectionKey)
        defaults.removeObject(forKey: Self.snapshotKey)
        isRestoredReading = false
        game = nil
        fetchedAt = nil
        errorMessage = nil
        isRefreshing = false
    }

    /// Foreground scheduling only; this is not a watchOS background guarantee.
    /// Waiting happens after completion, so slow responses never overlap polls.
    var nextRefreshDelay: TimeInterval {
        if consecutiveFailures > 0 {
            return min(300, 30 * pow(2, Double(consecutiveFailures - 1)))
        }
        return game?.isLive == true ? 30 : 300
    }

    @MainActor func runForegroundRefresh(
        sleep: (TimeInterval) async throws -> Void = { seconds in
            try await Task.sleep(for: .seconds(seconds))
        }
    ) async {
        while !Task.isCancelled, selectedEventID != nil {
            await refresh()
            guard !Task.isCancelled, selectedEventID != nil else { return }
            do { try await sleep(nextRefreshDelay) }
            catch { return }
        }
    }

    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        guard let id = selectedEventID else { return }
        revision += 1
        let requestRevision = revision
        isRefreshing = true
        errorMessage = nil
        do {
            let result = try await transport.fetch(eventID: id)
            try Task.checkCancellation()
            guard requestRevision == revision, selectedEventID == id else { return }
            // Detail can resolve an absorbed alias to the surviving canonical id.
            selectedEventID = result.id
            defaults.set(result.id, forKey: Self.selectionKey)
            consecutiveFailures = 0
            game = result
            let receivedAt = now()
            fetchedAt = receivedAt
            isRestoredReading = false
            if let data = try? JSONEncoder().encode(Snapshot(version: 1, game: result, fetchedAt: receivedAt)) {
                defaults.set(data, forKey: Self.snapshotKey)
            } else {
                defaults.removeObject(forKey: Self.snapshotKey)
            }
            isRefreshing = false
        } catch {
            guard requestRevision == revision, selectedEventID == id else { return }
            isRefreshing = false
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            consecutiveFailures = min(consecutiveFailures + 1, 5)
            let code = (error as? URLError)?.code
            errorMessage = (code == .notConnectedToInternet || code == .networkConnectionLost)
                ? "Offline. Try again." : "Couldn't refresh. Try again."
            // Keep the last successful game and its original timestamps.
        }
    }
}
