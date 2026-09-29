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
}

final class PinManager: ObservableObject {
    @Published var pinnedEventIDs: Set<Int> = []
    @Published var pinnedFuturesIDs: Set<Int> = []
    @Published var feedback: PinActionFeedback?
    /// Pins whose server save has not answered yet, keyed `type:id`.
    @Published private(set) var savingKeys: Set<String> = []

    static let maxPinsPerType = 6

    /// Writes one pin change to the server: `pinned` true adds, false removes.
    typealias ServerSync = (_ type: String, _ id: Int, _ pinned: Bool) async throws -> Void

    private let eventsKey = "bainluck_pinnedEvents"
    private let futuresKey = "bainluck_pinnedFutures"
    private let defaults: UserDefaults
    private let serverSync: ServerSync

    /// Whether the user is authenticated (set externally).
    private(set) var isAuthenticated = false

    init(defaults: UserDefaults = .standard, serverSync: ServerSync? = nil) {
        self.defaults = defaults
        self.serverSync = serverSync ?? { type, id, pinned in
            if pinned {
                _ = try await APIClient.shared.addPin(type: type, id: id)
            } else {
                _ = try await APIClient.shared.removePin(type: type, id: id)
            }
        }
        loadFromDefaults()
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
        case "event": return pinnedEventIDs.count < Self.maxPinsPerType
        case "future": return pinnedFuturesIDs.count < Self.maxPinsPerType
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
            guard canPin(type: type) else {
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.warning)
                #endif
                feedback = PinActionFeedback(
                    message: Self.limitMessage(type: type),
                    systemImage: "exclamationmark.triangle.fill",
                    isWarning: true
                )
                return nil
            }
            addLocally(type: type, id: id)
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            #endif
        }

        saveToDefaults()

        guard isAuthenticated else {
            feedback = Self.confirmed(removed: alreadyPinned)
            return nil
        }

        savingKeys.insert(key)
        feedback = PinActionFeedback(
            message: alreadyPinned ? "Removing…" : "Saving…",
            systemImage: "bookmark",
            isWarning: false,
            isPending: true
        )
        let serverSync = serverSync
        return Task {
            do {
                try await serverSync(type, id, !alreadyPinned)
                feedback = Self.confirmed(removed: alreadyPinned)
            } catch {
                logger.error("Failed to sync pin to server: \(error)")
                if alreadyPinned {
                    addLocally(type: type, id: id)
                } else {
                    removeLocally(type: type, id: id)
                }
                saveToDefaults()
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                #endif
                feedback = PinActionFeedback(
                    message: alreadyPinned ? "Couldn't remove pin. Try again." : "Couldn't save pin. Try again.",
                    systemImage: "exclamationmark.triangle.fill",
                    isWarning: true
                )
            }
            savingKeys.remove(key)
        }
    }

    static func limitMessage(type: String) -> String {
        let noun = type == "future" ? "markets" : "games"
        return "You already have \(maxPinsPerType) pinned \(noun). Unpin one in My Stuff."
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

    @MainActor
    func syncLocalToServer() async {
        guard isAuthenticated else { return }
        let localEvents = pinnedEventIDs
        let localFutures = pinnedFuturesIDs

        guard !localEvents.isEmpty || !localFutures.isEmpty else { return }

        for id in localEvents {
            do {
                _ = try await APIClient.shared.addPin(type: "event", id: id)
            } catch {
                logger.error("Failed to sync event pin \(id): \(error)")
            }
        }
        for id in localFutures {
            do {
                _ = try await APIClient.shared.addPin(type: "future", id: id)
            } catch {
                logger.error("Failed to sync future pin \(id): \(error)")
            }
        }

        // Reload from server to get the merged set
        await loadFromServer()
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
        }
        if let data = defaults.data(forKey: futuresKey),
           let ids = try? JSONDecoder().decode([Int].self, from: data) {
            pinnedFuturesIDs = Set(ids)
        }
    }

    private func saveToDefaults() {
        if let data = try? JSONEncoder().encode(Array(pinnedEventIDs)) {
            defaults.set(data, forKey: eventsKey)
        }
        if let data = try? JSONEncoder().encode(Array(pinnedFuturesIDs)) {
            defaults.set(data, forKey: futuresKey)
        }
    }

    @MainActor
    private func loadFromServer() async {
        do {
            let pins = try await APIClient.shared.fetchPins()
            pinnedEventIDs = Set(pins.events)
            pinnedFuturesIDs = Set(pins.futures)
            saveToDefaults()
            logger.info("Loaded pins from server: \(pins.events.count) events, \(pins.futures.count) futures")
        } catch {
            logger.error("Failed to load pins from server: \(error)")
            // Fall back to local
            loadFromDefaults()
        }
    }
}
