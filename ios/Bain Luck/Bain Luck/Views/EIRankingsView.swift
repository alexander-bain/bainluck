import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "eiRankings")

// MARK: - Sport Filter

private struct SportFilter: Identifiable {
    let id: String
    let label: String
    let sportKey: String?
}

private let sportFilters: [SportFilter] = [
    SportFilter(id: "all", label: "All", sportKey: nil),
    SportFilter(id: "nfl", label: "NFL", sportKey: "americanfootball_nfl"),
    SportFilter(id: "nba", label: "NBA", sportKey: "basketball_nba"),
    SportFilter(id: "ncaab", label: "NCAAB", sportKey: "basketball_ncaab"),
    SportFilter(id: "nhl", label: "NHL", sportKey: "icehockey_nhl"),
    SportFilter(id: "mlb", label: "MLB", sportKey: "baseball_mlb"),
]

// MARK: - ViewModel

final class EIRankingsViewModel: ObservableObject {
    @Published var rankings: EIRankingsResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var selectedFilterId: String = "all"

    var selectedSportKey: String? {
        sportFilters.first { $0.id == selectedFilterId }?.sportKey
    }

    @MainActor
    func load() async {
        loading = rankings == nil
        do {
            rankings = try await APIClient.shared.fetchEIRankings(sport: selectedSportKey)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load EI rankings: \(error)")
        }
    }
}

// MARK: - View

struct EIRankingsView: View {
    @StateObject private var vm = EIRankingsViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.loading {
                    ProgressView("Loading rankings...")
                } else if let error = vm.error, vm.rankings == nil {
                    ContentUnavailableView(
                        "Couldn't Load Rankings",
                        systemImage: "wifi.exclamationmark",
                        description: Text(error)
                    )
                } else if let rankings = vm.rankings {
                    rankingsList(rankings)
                }
            }
            .navigationTitle("EI Rankings")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                }
            }
        }
        .task {
            await vm.load()
        }
    }

    // MARK: - Sport Picker

    private var sportPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(sportFilters) { filter in
                    Button {
                        vm.selectedFilterId = filter.id
                        vm.rankings = nil
                        Task { await vm.load() }
                    } label: {
                        Text(filter.label)
                            .font(.caption)
                            .fontWeight(vm.selectedFilterId == filter.id ? .semibold : .regular)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(
                                vm.selectedFilterId == filter.id
                                    ? Color.blue.opacity(0.15)
                                    : Color.cardBackground
                            )
                            .foregroundStyle(vm.selectedFilterId == filter.id ? .blue : .primary)
                            .clipShape(Capsule())
                    }
                }
            }
            .padding(.horizontal)
        }
    }

    // MARK: - Rankings List

    private func rankingsList(_ rankings: EIRankingsResponse) -> some View {
        List {
            Section {
                sportPicker
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
            }

            if !rankings.highest.isEmpty {
                Section {
                    ForEach(rankings.highest) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            rankingRow(event: event)
                        }
                    }
                } header: {
                    Label("Most Exciting", systemImage: "flame.fill")
                        .foregroundStyle(.orange)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }

            if !rankings.lowest.isEmpty {
                Section {
                    ForEach(rankings.lowest) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            rankingRow(event: event)
                        }
                    }
                } header: {
                    Label("Least Exciting", systemImage: "moon.zzz.fill")
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Ranking Row

    private func rankingRow(event: EIRankedEvent) -> some View {
        HStack(spacing: 10) {
            // Rank number
            Text("#\(event.rank)")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
                .frame(width: 28, alignment: .leading)

            // Team names and metadata
            VStack(alignment: .leading, spacing: 3) {
                Text("\(event.awayTeam) vs \(event.homeTeam)")
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    if let sport = event.sport {
                        Text(sportDisplayName(for: sport))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let ct = event.commenceTime {
                        RelativeTimeText(dateString: ct)
                    }
                }
            }

            Spacer()

            // Score (if finished)
            if let away = event.awayScore, let home = event.homeScore,
               event.status == "completed" || event.status == "closed" {
                Text("\(away) - \(home)")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }

            // EI badge
            if let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }
        }
        .padding(.vertical, 2)
    }
}
