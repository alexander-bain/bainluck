import Combine
import Foundation

nonisolated protocol WatchSelectedGameTransport: Sendable {
    func fetch(eventID: Int) async throws -> WatchSelectedGame
}

nonisolated enum WatchSelectedGameRequestError: Error {
    case unavailable
    case serviceBusy
    case retryAfter(TimeInterval)
    case invalidResponse
}

nonisolated struct WatchSelectedGameHTTPTransport: WatchSelectedGameTransport {
    let session: URLSession

    init(session: URLSession = .shared) { self.session = session }

    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        let url = URL(string: "https://api.bainluck.com/api/events/\(eventID)")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw WatchSelectedGameRequestError.invalidResponse
        }
        switch http.statusCode {
        case 200: break
        case 404, 410: throw WatchSelectedGameRequestError.unavailable
        case 429, 503:
            if let delay = Self.retryDelay(from: http.value(forHTTPHeaderField: "Retry-After"), now: Date()) {
                throw WatchSelectedGameRequestError.retryAfter(delay)
            }
            throw WatchSelectedGameRequestError.serviceBusy
        default: throw WatchSelectedGameRequestError.invalidResponse
        }
        do { return try JSONDecoder().decode(WatchSelectedGame.self, from: data) }
        catch { throw WatchSelectedGameRequestError.invalidResponse }
    }

    /// Bound server-directed pauses; malformed headers retain ordinary backoff.
    static func retryDelay(from value: String?, now: Date) -> TimeInterval? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        if value.utf8.allSatisfy({ (48...57).contains($0) }), let seconds = Double(value), seconds.isFinite {
            return min(3600, seconds)
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss 'GMT'"
        formatter.isLenient = false
        guard let date = formatter.date(from: value), formatter.string(from: date) == value else { return nil }
        let seconds = date.timeIntervalSince(now)
        guard seconds.isFinite, seconds >= 0 else { return nil }
        return min(3600, seconds)
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
    // Monotonic process clock keeps a wall-clock correction from extending the pause.
    private let retryClock: () -> TimeInterval
    private var retryNotBefore: TimeInterval?
    private static let selectionKey = "bainluck_watch_selected_event_id"

    private static let snapshotKey = "bainluck_watch_selected_game_snapshot_v1"
    private struct Snapshot: Codable {
        let version: Int
        let game: WatchSelectedGame
        let fetchedAt: Date
    }

    init(transport: any WatchSelectedGameTransport = WatchSelectedGameHTTPTransport(),
         defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init,
         retryClock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.transport = transport
        self.defaults = defaults
        self.now = now
        self.retryClock = retryClock
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
        retryNotBefore = nil
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
        retryNotBefore = nil
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
    private var remainingServerDelay: TimeInterval {
        max(0, retryNotBefore.map { $0 - retryClock() } ?? 0)
    }

    var nextRefreshDelay: TimeInterval {
        let ordinary = consecutiveFailures > 0
            ? min(300, 30 * pow(2, Double(consecutiveFailures - 1)))
            : (game?.isLive == true ? 30.0 : 300.0)
        return max(ordinary, remainingServerDelay)
    }

    /// Only an explicit user action bypasses the current server-directed pause.
    @MainActor func allowManualRetry() { retryNotBefore = nil }

    @MainActor func runForegroundRefresh(
        sleep: (TimeInterval) async throws -> Void = { seconds in
            try await Task.sleep(for: .seconds(seconds))
        }
    ) async {
        while !Task.isCancelled, selectedEventID != nil {
            // A scene restart must not bypass a service's requested pause.
            let delay = remainingServerDelay
            if delay > 0 {
                do { try await sleep(delay) }
                catch { return }
                guard !Task.isCancelled, selectedEventID != nil else { return }
                continue
            }
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
        // A retry is not recovery. Keep the previous failure visible until success.
        do {
            let result = try await transport.fetch(eventID: id)
            try Task.checkCancellation()
            guard requestRevision == revision, selectedEventID == id else { return }
            // Detail can resolve an absorbed alias to the surviving canonical id.
            selectedEventID = result.id
            defaults.set(result.id, forKey: Self.selectionKey)
            consecutiveFailures = 0
            retryNotBefore = nil
            errorMessage = nil
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
            switch error {
            case WatchSelectedGameRequestError.unavailable:
                errorMessage = "Selected game is unavailable. Try again or choose another game."
            case WatchSelectedGameRequestError.retryAfter(let delay):
                if delay.isFinite, delay > 0 {
                    retryNotBefore = retryClock() + min(3600, delay)
                }
                errorMessage = "Service temporarily busy. Automatic retry will wait; you can refresh now."
            case WatchSelectedGameRequestError.serviceBusy:
                errorMessage = "Service temporarily busy. Try again."
            case WatchSelectedGameRequestError.invalidResponse:
                errorMessage = "Couldn't read this game. Try again."
            case let urlError as URLError where [.notConnectedToInternet, .networkConnectionLost].contains(urlError.code):
                errorMessage = "Offline. Try again."
            case let urlError as URLError where urlError.code == .timedOut:
                errorMessage = "Connection timed out. Try again."
            default:
                errorMessage = "Couldn't refresh. Try again."
            }
            // Keep the last successful game and its original timestamps.
        }
    }
}
