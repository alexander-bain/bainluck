import Combine
import Foundation

final class GolfCategoryViewModel: ObservableObject {
    enum State {
        case loading
        case loaded
        case error(String)
    }

    @Published var state: State = .loading
    @Published var currentEvent: GolfCurrentEventData?
    @Published var liveTournament: GolfTournamentData?
    @Published var tourSections: [TourSection] = []

    private static let tourOrder = ["pga", "euro", "liv", "kft", "lpga", "opp"]
    private static let tourNames: [String: String] = [
        "pga": "PGA Tour",
        "euro": "DP World Tour",
        "liv": "LIV Golf",
        "kft": "Korn Ferry Tour",
        "lpga": "LPGA Tour",
        "opp": "PGA Tour Americas",
        "alt": "Alternate Events",
        "major": "Majors",
    ]

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
                    displayName: Self.tourNames[key] ?? key.uppercased(),
                    isFollowing: key == "pga", // Default: PGA Tour followed
                    tournaments: grouped[key] ?? []
                ))
            }
            // Add any remaining tours not in the order
            for key in allKeys.sorted() where !Self.tourOrder.contains(key) {
                if key == "major" { continue } // Majors listed under their tour
                sections.append(TourSection(
                    tour: key,
                    displayName: Self.tourNames[key] ?? key.uppercased(),
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
