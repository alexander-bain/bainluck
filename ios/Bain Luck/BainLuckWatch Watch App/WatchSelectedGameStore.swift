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

/// Only the canonical selection is persisted; scores and timestamps always come
/// from the public API. Each request is fenced against selection/refresh races.
final class WatchSelectedGameStore: ObservableObject {
    @Published private(set) var selectedEventID: Int?
    @Published private(set) var game: WatchSelectedGame?
    @Published private(set) var fetchedAt: Date?
    @Published private(set) var isRefreshing = false
    @Published private(set) var errorMessage: String?
    private let transport: any WatchSelectedGameTransport
    private let defaults: UserDefaults
    private let now: () -> Date
    private var revision = 0
    private static let selectionKey = "bainluck_watch_selected_event_id"

    init(transport: any WatchSelectedGameTransport = WatchSelectedGameHTTPTransport(),
         defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.transport = transport
        self.defaults = defaults
        self.now = now
        let stored = defaults.integer(forKey: Self.selectionKey)
        selectedEventID = stored > 0 ? stored : nil
    }

    @MainActor func select(eventID: Int) {
        guard eventID > 0, eventID != selectedEventID else { return }
        revision += 1
        selectedEventID = eventID
        defaults.set(eventID, forKey: Self.selectionKey)
        game = nil
        fetchedAt = nil
        errorMessage = nil
        isRefreshing = false
    }

    @MainActor func clearSelection() {
        revision += 1
        selectedEventID = nil
        defaults.removeObject(forKey: Self.selectionKey)
        game = nil
        fetchedAt = nil
        errorMessage = nil
        isRefreshing = false
    }

    @MainActor func refresh() async {
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
            game = result
            fetchedAt = now()
            isRefreshing = false
        } catch {
            guard requestRevision == revision, selectedEventID == id else { return }
            isRefreshing = false
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            let code = (error as? URLError)?.code
            errorMessage = (code == .notConnectedToInternet || code == .networkConnectionLost)
                ? "Offline. Try again." : "Couldn't refresh. Try again."
            // Keep the last successful game and its original timestamps.
        }
    }
}
