import SwiftUI
import Combine

// MARK: - Golf Category View (Tour-Based Layout)

struct GolfCategoryView: View {
    @StateObject private var vm = GolfCategoryViewModel()

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .error(let message):
                VStack(spacing: 8) {
                    Text("Error loading golf data")
                        .font(.headline)
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load() } }
                }
                .padding()
            case .loaded:
                loadedView
            }
        }
        .navigationTitle("Golf")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task { await vm.load() }
    }

    // MARK: - Loaded View

    private var loadedView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                // Live tournament hero card
                if let current = vm.currentEvent, let tournament = vm.liveTournament {
                    liveSection(current, tournament)
                }

                // Tour sections
                ForEach(vm.tourSections, id: \.tour) { section in
                    tourSection(section)
                }

                // Championship grid link
                gridLink
            }
            .padding(.horizontal)
            .padding(.bottom, 40)
        }
        .refreshable { await vm.load() }
    }

    // MARK: - Live Section

    private func liveSection(_ current: GolfCurrentEventData, _ tournament: GolfTournamentData) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 5) {
                Circle()
                    .fill(Color.red)
                    .frame(width: 6, height: 6)
                Text("LIVE NOW")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.red)
            }
            .padding(.top, 16)

            NavigationLink(value: Route.golfTournament(slug: tournament.slug ?? "", name: tournament.name)) {
                TournamentHeroCard(tournament: tournament)
            }
            .buttonStyle(.plain)

            // Masters live leaderboard shortcut during Masters week
            if tournament.name.lowercased().contains("masters") || tournament.key?.lowercased() == "masters" {
                NavigationLink(value: Route.golfLeaderboard) {
                    HStack {
                        Image(systemName: "list.number")
                        Text("Ultra-Light Leaderboard")
                            .font(.caption)
                            .fontWeight(.medium)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption2)
                    }
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.blue.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.bottom, 20)
    }

    // MARK: - Tour Section

    private func tourSection(_ section: TourSection) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Tour header
            HStack(alignment: .firstTextBaseline) {
                Text(section.displayName)
                    .font(.title3)
                    .fontWeight(.bold)

                Spacer()

                Button(action: {}) {
                    Text(section.isFollowing ? "✓ Following" : "+ Follow")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(section.isFollowing ? .green : .blue)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            section.isFollowing
                                ? Color.green.opacity(0.1)
                                : Color.blue.opacity(0.08)
                        )
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(section.isFollowing ? Color.green : Color.blue, lineWidth: 0.5)
                        )
                }
            }
            .padding(.top, 8)
            .padding(.bottom, 2)

            // Upcoming tournaments
            if section.tournaments.isEmpty {
                Text("No upcoming events")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.vertical, 8)
            } else {
                ForEach(section.tournaments) { tournament in
                    NavigationLink(value: Route.golfTournament(slug: tournament.slug ?? "", name: tournament.name)) {
                        TournamentCompactRow(tournament: tournament)
                    }
                    .buttonStyle(.plain)
                }
            }

            Divider()
                .padding(.top, 8)
        }
    }

    // MARK: - Championship Grid Link

    private var gridLink: some View {
        NavigationLink(value: Route.leagueGrid(slug: "golf")) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Season Championship Grid")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text("Major winners, odds across the full season")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("View →")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.blue)
            }
            .padding(12)
            .background(Color.systemGray6.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .padding(.top, 16)
    }
}

// MARK: - Tour Section Model

struct TourSection: Sendable {
    let tour: String
    let displayName: String
    let isFollowing: Bool
    let tournaments: [GolfTournamentData]
}

// MARK: - ViewModel

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
