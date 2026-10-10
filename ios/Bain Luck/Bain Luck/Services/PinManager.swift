import Combine
import Foundation
import os
#if canImport(UIKit)
import UIKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "pins")

struct PinActionFeedback: Identifiable, Equatable {
    let id = UUID()
    let message: String
    let systemImage: String
    let isWarning: Bool
    /// A save still in flight. The toast stays up until the outcome replaces it,
    /// so "Saving…" never quietly disappears into nothing (#9495).
    var isPending: Bool = false
    var managementType: String? = nil
    var managementAlertTitle: String = "Manage pins"
}

final class PinManager: ObservableObject {
    @Published var pinnedEventIDs: Set<Int> = []
    @Published var pinnedFuturesIDs: Set<Int> = []
    @Published var feedback: PinActionFeedback?
    /// Pins whose server save has not answered yet, keyed `type:id`.
    @Published private(set) var savingKeys: Set<String> = []

    // Product sync consumes server-confirmed identities, not optimistic screen state.
    @Published private(set) var confirmedPinsForWatch: [SavedPin]?
    private(set) var confirmedPinsForWatchAt: Date?
    @Published private(set) var watchPinSaveFailed = false
    private var confirmedMutationsForWatch: [SavedPin: (revision: Int, pinned: Bool)] = [:]
    @Published private(set) var loadState: PinLoadState = .local
    @Published private(set) var identityGeneration = UUID()
    @Published var managementPresentation: PinManagementRequest?
    private var pendingRemovals: Set<SavedPin> = []
    private var binding = PinAccountBinding(userID: nil, authenticated: false)
    private var usesAccountStorage = false
    private var mutationRevision = 0
    private var mutations: [SavedPin: (revision: Int, pinned: Bool)] = [:]
    private var loadRequest = UUID()

    var savedPins: [SavedPin] {
        let events = pinnedEventIDs.map { SavedPin(type: "event", value: $0) }
        let futures = pinnedFuturesIDs.map { SavedPin(type: "future", value: $0) }
        return Set(events + futures).union(pendingRemovals).sorted {
            $0.type == $1.type ? $0.value < $1.value : $0.type < $1.type
        }
    }

    func presentManagement(type: String? = nil) {
        managementPresentation = PinManagementRequest(focusType: type)
        feedback = nil
    }

    /// Only the message being dismissed may clear; a newer message and an open
    /// management destination are independent of this action.
    func dismissFeedback(id: UUID) {
        guard feedback?.id == id else { return }
        feedback = nil
    }

    /// A remembered identity during restore is still that account, not a guest.
    func bindAccount(_ next: PinAccountBinding) {
        guard !usesAccountStorage || binding != next else { return }
        usesAccountStorage = true
        binding = next
        isAuthenticated = next.authenticated
        identityGeneration = UUID()
        loadRequest = UUID()
        mutationRevision += 1
        savingKeys.removeAll()
        pendingRemovals.removeAll()
        mutations.removeAll()
        watchPinSaveFailed = false
        confirmedPinsForWatchAt = nil
        confirmedPinsForWatch = nil
        confirmedMutationsForWatch.removeAll()
        feedback = nil
        managementPresentation = nil
        loadFromDefaults()
        loadState = next.userID == nil ? .local : .loading
    }

    static let maxPinsPerType = 6

    /// Writes one pin change to the server: `pinned` true adds, false removes.
    typealias ServerSync = (_ type: String, _ id: Int, _ pinned: Bool) async throws -> Void

    private var eventsKey: String { storageKey("Events") }
    private var futuresKey: String { storageKey("Futures") }
    private func storageKey(_ suffix: String) -> String {
        guard usesAccountStorage else { return "bainluck_pinned\(suffix)" }
        return "bainluck_pins.\(binding.userID.map { "user.\($0)" } ?? "guest").\(suffix)"
    }
    private let defaults: UserDefaults
    private let serverSync: ServerSync
    private let serverLoad: () async throws -> PinsResponse

    /// Whether the user is authenticated (set externally).
    private(set) var isAuthenticated = false

    init(defaults: UserDefaults = .standard, allowLegacyGuestPins: Bool = true, initialBinding: PinAccountBinding? = nil, serverLoad: (() async throws -> PinsResponse)? = nil, serverSync: ServerSync? = nil) {
        self.defaults = defaults
        self.serverLoad = serverLoad ?? { try await APIClient.shared.fetchPins() }
        // Build 32 shared these keys between guests and accounts. Import only
        // on a device with no remembered account; account pins come from server.
        if !defaults.bool(forKey: "bainluck_pins.guestMigrationDone") {
            if allowLegacyGuestPins {
                for suffix in ["Events", "Futures"] {
                    if let data = defaults.data(forKey: "bainluck_pinned\(suffix)") {
                        defaults.set(data, forKey: "bainluck_pins.guest.\(suffix)")
                    }
                }
            }
            defaults.set(true, forKey: "bainluck_pins.guestMigrationDone")
        }
        self.serverSync = serverSync ?? { type, id, pinned in
            if pinned {
                _ = try await APIClient.shared.addPin(type: type, id: id)
            } else {
                _ = try await APIClient.shared.removePin(type: type, id: id)
            }
        }
        if let initialBinding { bindAccount(initialBinding) }
        else { loadFromDefaults() }
    }

    // MARK: - Public API

    func setAuthenticated(_ authenticated: Bool) {
        isAuthenticated = authenticated
    }

    func isPinned(type: String, id: Int) -> Bool {
        switch type {
        case "event": return pinnedEventIDs.contains(id)
        case "future": return pinnedFuturesIDs.contains(id)
        default: return false
        }
    }

    func canPin(type: String) -> Bool {
        switch type {
        case "event": return savedPins.filter { $0.type == "event" }.count < Self.maxPinsPerType
        case "future": return savedPins.filter { $0.type == "future" }.count < Self.maxPinsPerType
        default: return false
        }
    }

    func isSaving(type: String, id: Int) -> Bool {
        savingKeys.contains(Self.key(type: type, id: id))
    }

    /// Every tap says what happened (#9495). Signed out, the device is the
    /// store, so the local save is the confirmation. Signed in, "Pinned" waits
    /// for the server; a failed save is shown and the local change is undone
    /// so the app never disagrees with the account in silence.
    /// Returns the server save, if one started, so tests can await it.
    @discardableResult
    func togglePin(type: String, id: Int) -> Task<Void, Never>? {
        guard type == "event" || type == "future" else { return nil }
        if usesAccountStorage, binding.userID != nil, !isAuthenticated {
            feedback = PinActionFeedback(message: "Restoring your account. Try again in a moment.", systemImage: "arrow.triangle.2.circlepath", isWarning: true)
            return nil
        }
        let generation = identityGeneration
        let key = Self.key(type: type, id: id)
        guard !savingKeys.contains(key) else {
            feedback = PinActionFeedback(
                message: "Still saving…",
                systemImage: "arrow.triangle.2.circlepath",
                isWarning: false,
                isPending: true
            )
            return nil
        }

        let alreadyPinned = isPinned(type: type, id: id)

        if alreadyPinned {
            removeLocally(type: type, id: id)
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        } else {
            if usesAccountStorage, binding.userID != nil, loadState != .loaded {
                feedback = PinActionFeedback(message: "Refresh your saved pins before adding another.", systemImage: "bookmark", isWarning: true, managementType: type, managementAlertTitle: "Refresh saved pins")
                return nil
            }
            guard canPin(type: type) else {
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.warning)
                #endif
                feedback = PinActionFeedback(
                    message: Self.limitMessage(type: type, count: savedPins.filter { $0.type == type }.count),
                    systemImage: "exclamationmark.triangle.fill",
                    isWarning: true,
                    managementType: type,
                    managementAlertTitle: "Pin limit reached"
                )
                return nil
            }
            addLocally(type: type, id: id)
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            #endif
        }

        mutationRevision += 1
        mutations[SavedPin(type: type, value: id)] = (mutationRevision, !alreadyPinned)
        if isAuthenticated, alreadyPinned { pendingRemovals.insert(SavedPin(type: type, value: id)) }
        saveToDefaults()

        guard isAuthenticated else {
            feedback = Self.confirmed(removed: alreadyPinned)
            return nil
        }

        watchPinSaveFailed = false
        savingKeys.insert(key)
        feedback = PinActionFeedback(
            message: alreadyPinned ? "Removing…" : "Saving…",
            systemImage: "bookmark",
            isWarning: false,
            isPending: true
        )
        let serverSync = serverSync
        return Task { @MainActor in
            guard identityGeneration == generation else { return }
            do {
                try await serverSync(type, id, !alreadyPinned)
                guard identityGeneration == generation else { return }
                // Advance only after the server acknowledges this exact account's write.
                mutationRevision += 1
                let pin = SavedPin(type: type, value: id)
                confirmedMutationsForWatch[pin] = (mutationRevision, !alreadyPinned)
                if let confirmedPinsForWatch {
                    var saved = Set(confirmedPinsForWatch)
                    if alreadyPinned { saved.remove(pin) } else { saved.insert(pin) }
                    self.confirmedPinsForWatchAt = Date()
                    self.confirmedPinsForWatch = Self.sortedWatchPins(saved)
                }
                feedback = Self.confirmed(removed: alreadyPinned)
            } catch {
                guard identityGeneration == generation else { return }
                watchPinSaveFailed = true
                logger.error("Failed to sync pin to server: \(error)")
                if alreadyPinned {
                    addLocally(type: type, id: id)
                } else {
                    removeLocally(type: type, id: id)
                }
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                #endif
                feedback = PinActionFeedback(
                    message: alreadyPinned ? "Couldn't remove pin. Try again." : "Couldn't save pin. Try again.",
                    systemImage: "exclamationmark.triangle.fill",
                    isWarning: true
                )
            }
            pendingRemovals.remove(SavedPin(type: type, value: id))
            // Only now may the stored cache drop a removed pin (#9875).
            saveToDefaults()
            mutationRevision += 1
            mutations[SavedPin(type: type, value: id)] = (mutationRevision, isPinned(type: type, id: id))
            savingKeys.remove(key)
        }
    }

    static func limitMessage(type: String, count: Int = maxPinsPerType) -> String {
        let noun = type == "future" ? "markets" : "games"
        return "You already have \(count) pinned \(noun). Unpin one in My Stuff."
    }

    private static func confirmed(removed: Bool) -> PinActionFeedback {
        PinActionFeedback(
            message: removed ? "Removed from My Stuff" : "Pinned to My Stuff",
            systemImage: removed ? "bookmark.slash.fill" : "bookmark.fill",
            isWarning: false
        )
    }

    private static func key(type: String, id: Int) -> String { "\(type):\(id)" }

    @MainActor
    func loadPins() async {
        if isAuthenticated {
            await loadFromServer()
        } else {
            loadFromDefaults()
        }
    }

    /// Kept for existing callers. Account binding never uploads a shared cache.
    @MainActor
    func syncLocalToServer() async {
        await loadPins()
    }

    private static func sortedWatchPins(_ pins: Set<SavedPin>) -> [SavedPin] {
        pins.sorted { $0.type == $1.type ? $0.value < $1.value : $0.type < $1.type }
    }

    // MARK: - Private

    private func addLocally(type: String, id: Int) {
        switch type {
        case "event": pinnedEventIDs.insert(id)
        case "future": pinnedFuturesIDs.insert(id)
        default: break
        }
    }

    private func removeLocally(type: String, id: Int) {
        switch type {
        case "event": pinnedEventIDs.remove(id)
        case "future": pinnedFuturesIDs.remove(id)
        default: break
        }
    }

    private func loadFromDefaults() {
        if let data = defaults.data(forKey: eventsKey),
           let ids = try? JSONDecoder().decode([Int].self, from: data) {
            pinnedEventIDs = Set(ids)
        } else { pinnedEventIDs = [] }
        if let data = defaults.data(forKey: futuresKey),
           let ids = try? JSONDecoder().decode([Int].self, from: data) {
            pinnedFuturesIDs = Set(ids)
        } else { pinnedFuturesIDs = [] }
    }

    /// A removal the server has not confirmed is still a saved pin on disk: a
    /// cold restart whose first load fails must find it, not lose it (#9875).
    private func saveToDefaults() {
        func removing(_ type: String) -> [Int] { pendingRemovals.filter { $0.type == type }.map(\.value) }
        if let data = try? JSONEncoder().encode(Array(pinnedEventIDs.union(removing("event")))) {
            defaults.set(data, forKey: eventsKey)
        }
        if let data = try? JSONEncoder().encode(Array(pinnedFuturesIDs.union(removing("future")))) {
            defaults.set(data, forKey: futuresKey)
        }
    }

    @MainActor
    private func loadFromServer() async {
        let generation = identityGeneration
        let revision = mutationRevision
        let request = UUID()
        loadRequest = request
        loadState = .loading
        do {
            let pins = try await serverLoad()
            guard identityGeneration == generation, loadRequest == request else { return }
            // Keep unrelated server pins while preserving edits made during this
            // read. Dropping the entire response would hide those other pins.
            pinnedEventIDs = Set(pins.events)
            pinnedFuturesIDs = Set(pins.futures)
            for (pin, mutation) in mutations where mutation.revision > revision || savingKeys.contains(pin.id) {
                if mutation.pinned { addLocally(type: pin.type, id: pin.value) }
                else { removeLocally(type: pin.type, id: pin.value) }
            }
            var confirmed = Set(pins.events.map { SavedPin(type: "event", value: $0) }
                + pins.futures.map { SavedPin(type: "future", value: $0) })
            // A delayed read may predate a write acknowledged while it was in flight.
            for (pin, change) in confirmedMutationsForWatch where change.revision > revision {
                if change.pinned { confirmed.insert(pin) } else { confirmed.remove(pin) }
            }
            watchPinSaveFailed = false
            confirmedPinsForWatchAt = Date()
            confirmedPinsForWatch = Self.sortedWatchPins(confirmed)
            saveToDefaults()
            loadState = .loaded
        } catch {
            guard identityGeneration == generation, loadRequest == request else { return }
            logger.error("Failed to load pins from server: \(error)")
            loadState = .failed
        }
    }
}
