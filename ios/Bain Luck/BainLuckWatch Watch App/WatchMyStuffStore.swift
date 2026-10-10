import Combine
import Foundation

/// Separate product state: telemetry consent never gates these identities.
@MainActor final class WatchMyStuffStore: ObservableObject {
    static let shared: WatchMyStuffStore = {
        #if os(watchOS) && DEBUG
        if let fixture = WatchUIFixture.current {
            return WatchMyStuffStore(defaults: UserDefaults(suiteName: fixture.suite)!)
        }
        #endif
        return WatchMyStuffStore()
    }()
    @Published private(set) var snapshot: WatchMyStuffSnapshot?
    @Published private(set) var connected = false
    @Published private(set) var connecting = false
    @Published private(set) var navigationGeneration = UUID()
    private struct Selection: Codable {
        let eventID: Int
        let origin: WatchMyStuffSnapshot.Item
        let publisher: UUID
        let generation: Int
    }
    private var selection: Selection?
    private static let selectionKey = "watch.my-stuff.selection.v1"
    private var cursor = WatchMyStuffCursor()
    private var nonce: UUID?
    private var expiry: Task<Void, Never>?
    private let defaults: UserDefaults
    private let now: () -> Date
    private static let snapshotKey = "watch.my-stuff.snapshot.v1"
    private static let cursorKey = "watch.my-stuff.cursor.v1"

    init(defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.defaults = defaults; self.now = now
        if let data = defaults.data(forKey: Self.selectionKey) {
            selection = try? JSONDecoder().decode(Selection.self, from: data)
        }
        if let data = defaults.data(forKey: Self.cursorKey) {
            cursor = (try? JSONDecoder().decode(WatchMyStuffCursor.self, from: data)) ?? .init()
        }
        if let data = defaults.data(forKey: Self.snapshotKey),
           let saved = WatchMyStuffSnapshot.decode(data, now: now()),
           saved.publisher == cursor.publisher, saved.revision == cursor.revision,
           saved.generation == cursor.generation {
            snapshot = saved
            scheduleExpiry()
        } else { defaults.removeObject(forKey: Self.snapshotKey) }
    }

    func beginHandshake() -> UUID {
        expireIfNeeded()
        let token = UUID(); nonce = token
        connected = false; connecting = true
        return token
    }
    func disconnect() { connected = false; connecting = false; nonce = nil; expireIfNeeded() }
    func failedHandshake(_ token: UUID) {
        guard nonce == token else { return }
        disconnect()
    }
    func receive(_ data: Data, handshake token: UUID? = nil) {
        let paired = token != nil && token == nonce
        if token != nil && !paired { return }
        guard let value = WatchMyStuffSnapshot.decode(data, now: now()) else {
            if let token { failedHandshake(token) }
            return
        }
        // An identical current reply still verifies a reconnect; it cannot replace data.
        if paired, value.publisher == cursor.publisher, value.generation == cursor.generation,
           value.revision == cursor.revision, snapshot == value {
            nonce = nil; connected = true; connecting = false; return
        }
        guard cursor.accept(value, pairedHandshake: paired) else {
            if let token { failedHandshake(token) }
            return
        }
        if snapshot?.publisher != value.publisher || snapshot?.generation != value.generation
            || value.account != .signedIn {
            navigationGeneration = UUID()
        }
        snapshot = value
        if paired { nonce = nil; connected = true; connecting = false }
        // Persist the tombstone and high-water mark as well as signed-in data.
        defaults.set(try? JSONEncoder().encode(cursor), forKey: Self.cursorKey)
        defaults.set(data, forKey: Self.snapshotKey)
        scheduleExpiry()
    }

    func select(eventID: Int, from item: WatchMyStuffSnapshot.Item, in selected: WatchSelectedGameStore) {
        guard eventID > 0, contains(item), let snapshot else { return }
        selection = Selection(eventID: eventID, origin: item, publisher: snapshot.publisher,
                              generation: snapshot.generation)
        defaults.set(try? JSONEncoder().encode(selection), forKey: Self.selectionKey)
        selected.select(eventID: eventID)
    }

    func reconcileSelection(in selected: WatchSelectedGameStore) {
        guard let selection else { return }
        if selected.isSelected(eventID: selection.eventID) {
            if snapshot?.publisher != selection.publisher || snapshot?.generation != selection.generation
                || !contains(selection.origin) {
                selected.clearSelection()
            } else { return }
        }
        self.selection = nil
        defaults.removeObject(forKey: Self.selectionKey)
    }

    func contains(_ item: WatchMyStuffSnapshot.Item) -> Bool {
        guard let snapshot, snapshot.account == .signedIn, snapshot.validUntil > now() else { return false }
        return (snapshot.pins.items + snapshot.teams.items).contains { $0.id == item.id }
    }
    func expireIfNeeded() {
        guard let snapshot, snapshot.account == .signedIn, snapshot.validUntil <= now() else { return }
        self.snapshot = nil; connected = false
        navigationGeneration = UUID()
        defaults.removeObject(forKey: Self.snapshotKey)
        // Cursor deliberately survives expiry so a late packet cannot roll it back.
    }
    private func scheduleExpiry() {
        expiry?.cancel()
        guard let snapshot, snapshot.account == .signedIn else { return }
        let seconds = max(0, snapshot.validUntil.timeIntervalSince(now()))
        expiry = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(seconds)) } catch { return }
            self?.expireIfNeeded()
        }
    }
}
