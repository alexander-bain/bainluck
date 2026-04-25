import Combine
import Foundation
import os
#if canImport(UIKit)
import UIKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "pins")

final class PinManager: ObservableObject {
    @Published var pinnedEventIDs: Set<Int> = []
    @Published var pinnedFuturesIDs: Set<Int> = []

    static let maxPinsPerType = 6

    private let eventsKey = "bainluck_pinnedEvents"
    private let futuresKey = "bainluck_pinnedFutures"
    private let defaults = UserDefaults.standard

    /// Whether the user is authenticated (set externally).
    var isAuthenticated = false

    init() {
        loadFromDefaults()
    }

    // MARK: - Public API

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

    func togglePin(type: String, id: Int) {
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
                return
            }
            addLocally(type: type, id: id)
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            #endif
        }

        saveToDefaults()

        // Sync to server if authenticated
        if isAuthenticated {
            Task {
                do {
                    if alreadyPinned {
                        _ = try await APIClient.shared.removePin(type: type, id: id)
                    } else {
                        _ = try await APIClient.shared.addPin(type: type, id: id)
                    }
                } catch {
                    logger.error("Failed to sync pin to server: \(error)")
                }
            }
        }
    }

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
