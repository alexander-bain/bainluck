import Combine
import Foundation

final class GolfCategoryViewModel: ObservableObject {
    enum State {
        case loading
        case loaded
        case error(String)
    }

    @Published private(set) var state: State = .loading
    @Published private(set) var currentEvent: GolfCurrentEventData?
    @Published private(set) var liveTournament: GolfTournamentData?
    @Published private(set) var tourSections: [TourSection] = []

    // Display order for known tours. Keys match the raw `tour` values the
    // backend sends (lower-cased, underscore-delimited). Display names come
    // from the shared `golfTourDisplayName` mapper so we never leak raw enums.
    private static let tourOrder = ["pga", "dp_world", "euro", "liv", "korn_ferry", "kft", "lpga", "opp", "americas"]

    @MainActor
    func load() async {
        do {
            let response = try await APIClient.shared.fetchGolfLanding()

            currentEvent = response.currentEvent
            liveTournament = response.tournaments.first(where: { $0.scheduleStatus == "in-progress" })

            // Group tournaments by tour, excluding the live tournament
            var grouped: [String: [GolfTournamentData]] = [:]
            for t in response.tournaments {
                let tourKey = t.tour ?? "other"
                if t.scheduleStatus == "in-progress" { continue } // Skip live — shown in hero
                grouped[tourKey, default: []].append(t)
            }

            // Build sections in order
            var sections: [TourSection] = []
            let allKeys = Set(grouped.keys)
            for key in Self.tourOrder where allKeys.contains(key) {
                sections.append(TourSection(
                    tour: key,
                    displayName: golfTourDisplayName(for: key),
                    isFollowing: key == "pga", // Default: PGA Tour followed
                    tournaments: grouped[key] ?? []
                ))
            }
            // Add any remaining tours not in the order
            for key in allKeys.sorted() where !Self.tourOrder.contains(key) {
                if key == "major" { continue } // Majors listed under their tour
                sections.append(TourSection(
                    tour: key,
                    displayName: golfTourDisplayName(for: key),
                    isFollowing: false,
                    tournaments: grouped[key] ?? []
                ))
            }

            tourSections = sections
            state = .loaded
        } catch {
            state = .error(error.localizedDescription)
        }
    }
}
