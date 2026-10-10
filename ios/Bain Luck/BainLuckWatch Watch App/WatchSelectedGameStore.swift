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
        let url = URL(string: "https://api.bainluck.com/api/events/\(eventID)?fresh=true")!
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
    private let publish: (WatchSelectedGame?, Date?) -> Void
    private let now: () -> Date
    private var selectedIdentityIDs: [Int] = []
    private var revision = 0
    private var consecutiveFailures = 0
    private(set) var successfulRefreshSequence = 0
    @MainActor var activeForegroundStream: LiveStreamController?
    @MainActor var foregroundStreamGeneration = UUID()

    @MainActor func stopLiveForegroundUpdates() {
        foregroundStreamGeneration = UUID()
        activeForegroundStream?.stop()
        activeForegroundStream = nil
    }

    /// Stream invalidations may bypass the normal live polling cadence, never
    /// server-directed waits or the backoff of an unsuccessful detail fetch.
    var foregroundPollDelay: TimeInterval {
        max(0, max(automaticRefreshNotBefore.map { $0 - retryClock() } ?? 0, remainingServerDelay))
    }
    var foregroundInvalidationDelay: TimeInterval {
        consecutiveFailures > 0 ? foregroundPollDelay : remainingServerDelay
    }
    // Monotonic process clock keeps a wall-clock correction from extending the pause.
    private let retryClock: () -> TimeInterval
    private var retryNotBefore: TimeInterval?
    // Keep the completed-request cadence across task cancellation / wrist raises.
    private var automaticRefreshNotBefore: TimeInterval?
    private static let selectionKey = "bainluck_watch_selected_event_id"

    private static let snapshotKey = "bainluck_watch_selected_game_snapshot_v1"
    private struct Snapshot: Codable {
        let version: Int
        let game: WatchSelectedGame
        let fetchedAt: Date
        let selectedIdentityIDs: [Int]?

        private enum CodingKeys: String, CodingKey {
            case version, game, fetchedAt, selectedIdentityIDs
        }

        init(version: Int, game: WatchSelectedGame, fetchedAt: Date, selectedIdentityIDs: [Int]) {
            self.version = version
            self.game = game
            self.fetchedAt = fetchedAt
            self.selectedIdentityIDs = selectedIdentityIDs
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            version = try values.decode(Int.self, forKey: .version)
            game = try values.decode(WatchSelectedGame.self, forKey: .game)
            fetchedAt = try values.decode(Date.self, forKey: .fetchedAt)
            // Optional identity corruption must not destroy a valid saved reading.
            selectedIdentityIDs = try? values.decodeIfPresent([Int].self, forKey: .selectedIdentityIDs)
        }

        var validatedIdentityIDs: [Int] {
            guard let ids = selectedIdentityIDs, (1...8).contains(ids.count),
                  ids.allSatisfy({ $0 > 0 }), Set(ids).count == ids.count,
                  ids.contains(game.id) else { return [game.id] }
            return ids
        }
    }

    init(transport: any WatchSelectedGameTransport = WatchSelectedGameHTTPTransport(),
         defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init,
         retryClock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
         publish: @escaping (WatchSelectedGame?, Date?) -> Void = { _, _ in }) {
        self.transport = transport
        self.defaults = defaults
        self.now = now
        self.retryClock = retryClock
        self.publish = publish
        let stored = defaults.integer(forKey: Self.selectionKey)
        selectedEventID = stored > 0 ? stored : nil
        if let data = defaults.data(forKey: Self.snapshotKey),
           let snapshot = try? JSONDecoder().decode(Snapshot.self, from: data),
           snapshot.version == 1, snapshot.game.id == selectedEventID {
            selectedIdentityIDs = snapshot.validatedIdentityIDs
            game = snapshot.game
            fetchedAt = snapshot.fetchedAt
            isRestoredReading = true
        } else {
            defaults.removeObject(forKey: Self.snapshotKey)
        }
        publish(game, fetchedAt)
    }

    /// Only accepted detail responses establish equivalence for this one reading.
    func isSelected(eventID: Int) -> Bool {
        guard eventID > 0 else { return false }
        return eventID == selectedEventID
            || (game?.id == selectedEventID && selectedIdentityIDs.contains(eventID))
    }

    @MainActor private func retainIdentity(requestedID: Int, canonicalID: Int) {
        if selectedIdentityIDs.isEmpty { selectedIdentityIDs = [requestedID] }
        let anchor = selectedIdentityIDs[0]
        for id in [requestedID, canonicalID] where id != anchor {
            selectedIdentityIDs.removeAll { $0 == id }
            selectedIdentityIDs.append(id)
        }
        // Keep the original choice and the latest seven distinct proven IDs.
        if selectedIdentityIDs.count > 8 {
            selectedIdentityIDs = [anchor] + selectedIdentityIDs.suffix(7)
        }
    }

    @MainActor func select(eventID: Int) {
        guard eventID > 0, !isSelected(eventID: eventID) else { return }
        stopLiveForegroundUpdates()
        selectedIdentityIDs = []
        revision += 1
        consecutiveFailures = 0
        retryNotBefore = nil
        automaticRefreshNotBefore = nil
        selectedEventID = eventID
        publish(nil, nil)
        defaults.set(eventID, forKey: Self.selectionKey)
        defaults.removeObject(forKey: Self.snapshotKey)
        isRestoredReading = false
        game = nil
        fetchedAt = nil
        errorMessage = nil
        isRefreshing = false
    }

    @MainActor func clearSelection() {
        stopLiveForegroundUpdates()
        selectedIdentityIDs = []
        revision += 1
        consecutiveFailures = 0
        retryNotBefore = nil
        automaticRefreshNotBefore = nil
        selectedEventID = nil
        publish(nil, nil)
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
    @MainActor func allowManualRetry() {
        retryNotBefore = nil
        automaticRefreshNotBefore = nil
    }

    @MainActor func runForegroundRefresh(
        sleep: (TimeInterval) async throws -> Void = { seconds in
            try await Task.sleep(for: .seconds(seconds))
        }
    ) async {
        while !Task.isCancelled, selectedEventID != nil {
            // A scene restart reuses a recent reading and preserves failure/server waits.
            let cadenceDelay = max(0, automaticRefreshNotBefore.map { $0 - retryClock() } ?? 0)
            let delay = max(cadenceDelay, remainingServerDelay)
            if delay > 0 {
                do { try await sleep(delay) }
                catch { return }
                guard !Task.isCancelled, selectedEventID != nil else { return }
                continue
            }
            automaticRefreshNotBefore = nil // Consume only an elapsed local deadline.
            await refresh()
            guard !Task.isCancelled, selectedEventID != nil else { return }
            // Superseded or transport-canceled work did not record a deadline.
            // Preserve the ordinary wait rather than starting a tight retry loop.
            if automaticRefreshNotBefore == nil {
                do { try await sleep(nextRefreshDelay) }
                catch { return }
            }
        }
    }

    static func canAdopt(_ incoming: WatchSelectedGame, replacing held: WatchSelectedGame?) -> Bool {
        guard let held, incoming.id == held.id else { return true }
        if held.isFinal && !incoming.isFinal { return false }
        if held.isClosed && !incoming.isClosed && !incoming.isFinal { return false }
        if let old = held.scoreObservedAt, let next = incoming.scoreObservedAt, next < old { return false }
        // A fresh authoritative change of source or lifecycle is not ordered
        // by the old source's price clock or blend vector.
        if incoming.isFinal || incoming.isClosed || incoming.probabilitySource != held.probabilitySource {
            return true
        }
        if let old = held.blendRevision, let next = incoming.blendRevision {
            switch FoldRevision.compare(next, old) {
            case .older: return false
            case .newer, .incomparable:
                // A fresh full detail resolves changed membership or source removal.
                return true
            case .same: break
            }
        } else if held.blendRevision != nil, incoming.blendRevision == nil,
                  !incoming.isFinal, !incoming.isClosed { return false }
        if let old = held.probabilityObservedAt, let next = incoming.probabilityObservedAt, next < old {
            return false
        }
        if let old = held.scoreObservedAt, let next = incoming.scoreObservedAt, next < old { return false }
        if held.isFinal && !incoming.isFinal { return false }
        return true
    }

    /// Optional UI-owned diagnostics; tests and background data owners default to no sink.
    var telemetry: (@MainActor (String, Int, Int) -> Void)?

    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        guard let id = selectedEventID else { return }
        revision += 1
        let requestRevision = revision
        let telemetryStart = ProcessInfo.processInfo.systemUptime
        var telemetryOutcome = "cancelled"
        var telemetryCount = 0
        defer {
            let elapsed = Int(min(3_600_000, max(0, (ProcessInfo.processInfo.systemUptime - telemetryStart) * 1000)))
            telemetry?(telemetryOutcome, elapsed, telemetryCount)
        }
        isRefreshing = true
        // A retry is not recovery. Keep the previous failure visible until success.
        do {
            let result = try await transport.fetch(eventID: id)
            try Task.checkCancellation()
            guard requestRevision == revision, selectedEventID == id else { return }
            guard Self.canAdopt(result, replacing: game) else {
                throw WatchSelectedGameRequestError.invalidResponse
            }
            successfulRefreshSequence += 1
            retainIdentity(requestedID: id, canonicalID: result.id)
            // Detail can resolve an absorbed alias to the surviving canonical id.
            selectedEventID = result.id
            defaults.set(result.id, forKey: Self.selectionKey)
            consecutiveFailures = 0
            retryNotBefore = nil
            errorMessage = nil
            game = result
            telemetryCount = 1
            telemetryOutcome = "success"
            let receivedAt = now()
            fetchedAt = receivedAt
            isRestoredReading = false
            if let data = try? JSONEncoder().encode(Snapshot(version: 1, game: result, fetchedAt: receivedAt, selectedIdentityIDs: selectedIdentityIDs)) {
                defaults.set(data, forKey: Self.snapshotKey)
            } else {
                defaults.removeObject(forKey: Self.snapshotKey)
            }
            automaticRefreshNotBefore = retryClock() + nextRefreshDelay
            publish(result, receivedAt)
            isRefreshing = false
        } catch {
            guard requestRevision == revision, selectedEventID == id else { return }
            isRefreshing = false
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            switch (error as? URLError)?.code {
            case .notConnectedToInternet, .networkConnectionLost: telemetryOutcome = "offline"
            case .timedOut: telemetryOutcome = "timeout"
            default: telemetryOutcome = "failure"
            }
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
            automaticRefreshNotBefore = retryClock() + nextRefreshDelay
            // Keep the last successful game and its original timestamps.
        }
    }
}
