import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "preferences")

@MainActor
final class PreferencesViewModel: ObservableObject {
    @Published var prefs: PreferencesResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var sportAffinities: [String: Double] = [:]

    private var affinitySaveTask: Task<Void, Never>?

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
                }
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
}
