import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "preferences")

/// Persists the Morning Digest push preference; returns the server-confirmed
/// value. Injectable so tests can drive success/failure without the network.
typealias MorningDigestUpdater = @Sendable (_ enabled: Bool) async throws -> Bool

@MainActor
final class PreferencesViewModel: ObservableObject {
    @Published private(set) var prefs: PreferencesResponse?
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var sportAffinities: [String: Double] = [:]

    // MARK: - Morning Digest (push preference)
    @Published private(set) var morningDigestEnabled = false
    @Published private(set) var morningDigestSaving = false
    @Published private(set) var morningDigestError: String?

    private let morningDigestUpdater: MorningDigestUpdater
    private var morningDigestSaveTask: Task<Void, Never>?

    private var affinitySaveTask: Task<Void, Never>?

    init(morningDigestUpdater: @escaping MorningDigestUpdater = { enabled in
        let response = try await APIClient.shared.updatePushPreferences(morningDigest: enabled)
        return response.pushPreferences?.morningDigest ?? enabled
    }) {
        self.morningDigestUpdater = morningDigestUpdater
    }

    // MARK: - Computed: Teams grouped by relation type

    var followTeams: [FavoriteItem] {
        prefs?.favorites.filter { $0.relationType == "follow" } ?? []
    }

    var localTeams: [FavoriteItem] {
        prefs?.favorites.filter { $0.relationType == "local" } ?? []
    }

    var almaMaterTeams: [FavoriteItem] {
        prefs?.favorites.filter { $0.relationType == "alma_mater" } ?? []
    }

    var rivalTeams: [FavoriteItem] {
        prefs?.favorites.filter { $0.relationType == "rival" } ?? []
    }

    var hasAnyTeams: Bool {
        prefs?.favorites.isEmpty == false
    }

    // MARK: - Load

    func load() async {
        loading = true
        do {
            let response = try await APIClient.shared.fetchPreferences()
            prefs = response
            sportAffinities = response.sportAffinities
            // Reflect the server's stored value; opt-in default is false.
            morningDigestEnabled = response.pushPreferences?.morningDigest ?? false
            morningDigestError = nil
            error = nil
            logger.info("Preferences loaded: \(response.favorites.count) favorites")
        } catch {
            self.error = error.localizedDescription
            logger.error("Preferences load error: \(error)")
        }
        loading = false
    }

    // MARK: - Remove Favorite

    func removeFavorite(teamId: Int, relationType: String) {
        // Optimistic: remove from local state immediately
        prefs = prefs.map { current in
            PreferencesResponse(
                homeLocation: current.homeLocation,
                sportAffinities: current.sportAffinities,
                onboardingCompleted: current.onboardingCompleted,
                favorites: current.favorites.filter {
                    !($0.teamId == teamId && $0.relationType == relationType)
                },
                pushPreferences: current.pushPreferences
            )
        }

        Task {
            do {
                _ = try await APIClient.shared.removeFavorite(teamId: teamId, relationType: relationType)
                logger.info("Removed favorite: team \(teamId) (\(relationType))")
            } catch {
                logger.error("Remove favorite failed: \(error)")
                // Reload to restore correct state
                await load()
            }
        }
    }

    // MARK: - Affinity

    func affinityLevel(for key: String) -> AffinityLevel {
        guard let value = sportAffinities[key] else { return .nah }
        return AffinityLevel.allCases.first { $0.rawValue == value } ?? .nah
    }

    func setAffinity(_ key: String, level: AffinityLevel) {
        sportAffinities[key] = level.rawValue
        debounceSaveAffinities()
    }

    private func debounceSaveAffinities() {
        affinitySaveTask?.cancel()
        affinitySaveTask = Task {
            do {
                try await Task.sleep(nanoseconds: 2_000_000_000)
            } catch {
                return // cancelled
            }
            await saveAffinities()
        }
    }

    private func saveAffinities() async {
        do {
            _ = try await APIClient.shared.updateSportAffinities(sportAffinities)
            logger.info("Sport affinities saved")
        } catch {
            logger.error("Save affinities failed: \(error)")
        }
    }

    // MARK: - Morning Digest

    /// Optimistically flips the toggle and persists it; supersedes any in-flight save.
    func setMorningDigest(_ enabled: Bool) {
        morningDigestSaveTask?.cancel()
        morningDigestSaveTask = Task { await self.applyMorningDigest(enabled) }
    }

    /// Applies the change: optimistic update, persist, and roll back on failure.
    /// Exposed (not private) so tests can await the full round-trip deterministically.
    func applyMorningDigest(_ enabled: Bool) async {
        guard enabled != morningDigestEnabled else { return }
        let previous = morningDigestEnabled
        morningDigestEnabled = enabled          // optimistic
        morningDigestError = nil
        morningDigestSaving = true
        do {
            let confirmed = try await morningDigestUpdater(enabled)
            if Task.isCancelled { return }      // superseded by a newer toggle
            morningDigestEnabled = confirmed
        } catch {
            if Task.isCancelled { return }
            morningDigestEnabled = previous     // roll back to pre-tap state
            morningDigestError = "Couldn't update Morning Digest. Try again."
            logger.error("Morning digest save failed: \(error)")
        }
        morningDigestSaving = false
    }
}
