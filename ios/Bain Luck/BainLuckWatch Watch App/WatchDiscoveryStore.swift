import Combine
import Foundation

/// Last-good questions are retained with their original producer clocks.
final class WatchDiscoveryStore: ObservableObject {
    @Published private(set) var readings: [WatchDiscoveryReading] = []
    @Published private(set) var fetchedAt: Date?
    @Published private(set) var isRefreshing = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var isSavedReading = false
    private let transport: any WatchDiscoveryTransport
    private let defaults: UserDefaults
    private let now: () -> Date
    private var revision = 0
    private static let snapshotKey = "bainluck_watch_discoveries_snapshot_v1"
    private struct Snapshot: Codable {
        let version: Int
        let readings: [WatchDiscoveryReading]
        let fetchedAt: Date
    }

    init(transport: any WatchDiscoveryTransport = WatchDiscoveryAPIClient(),
         defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.transport = transport
        self.defaults = defaults
        self.now = now
        if let data = defaults.data(forKey: Self.snapshotKey),
           let snapshot = try? JSONDecoder().decode(Snapshot.self, from: data),
           snapshot.version == 1, snapshot.readings.count <= 3,
           snapshot.readings.allSatisfy(\.isValid),
           Set(snapshot.readings.map(\.id)).count == snapshot.readings.count {
            readings = snapshot.readings
            fetchedAt = snapshot.fetchedAt
            isSavedReading = true
        } else {
            defaults.removeObject(forKey: Self.snapshotKey)
        }
    }

    func visibleReadings(hasSelectedGame: Bool) -> [WatchDiscoveryReading] {
        Array(readings.prefix(hasSelectedGame ? 2 : 3))
    }

    /// Cancel a dismissed page's request without erasing a saved reading/error.
    @MainActor func cancelRefresh() {
        revision += 1
        isRefreshing = false
    }

    @MainActor func refresh() async {
        guard !Task.isCancelled else { return }
        revision += 1
        let requestRevision = revision
        isRefreshing = true
        do {
            let result = try await transport.fetch()
            try Task.checkCancellation()
            guard requestRevision == revision else { return }
            var seen = Set<Int>()
            readings = Array(result.filter { $0.isValid && seen.insert($0.id).inserted }.prefix(3))
            let receivedAt = now()
            fetchedAt = receivedAt
            isSavedReading = false
            errorMessage = nil
            isRefreshing = false
            if let data = try? JSONEncoder().encode(Snapshot(version: 1, readings: readings, fetchedAt: receivedAt)) {
                defaults.set(data, forKey: Self.snapshotKey)
            } else { defaults.removeObject(forKey: Self.snapshotKey) }
        } catch {
            guard requestRevision == revision else { return }
            isRefreshing = false
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            isSavedReading = fetchedAt != nil
            switch error {
            case let error as URLError where [.notConnectedToInternet, .networkConnectionLost].contains(error.code):
                errorMessage = "Offline. Try again."
            case let error as URLError where error.code == .timedOut:
                errorMessage = "Connection timed out. Try again."
            case WatchDiscoveryRequestError.serviceBusy:
                errorMessage = "Service temporarily busy. Try again."
            default:
                errorMessage = "Couldn't read Discoveries. Try again."
            }
        }
    }
}
