import SwiftUI

struct TeamDetailView: View {
    let slug: String

    @State private var data: TeamPageResponse?
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        Group {
            if loading {
                ProgressView()
            } else if let error {
                ContentUnavailableView("Team Not Found", systemImage: "person.crop.circle.badge.questionmark", description: Text(error))
            } else if let data {
                teamContent(data)
            }
        }
        .task { await loadTeam() }
    }

    @MainActor
    private func loadTeam() async {
        do {
            data = try await APIClient.shared.fetchTeamPage(slug: slug)
            loading = false
        } catch {
            self.error = "Could not load team"
            loading = false
        }
    }

    private func teamContent(_ data: TeamPageResponse) -> some View {
        let team = data.team
        return List {
            // Hero
            Section {
                HStack(spacing: 16) {
                    if let logo = team.logoLarge ?? team.logoSmall, let url = URL(string: logo) {
                        AsyncImage(url: url) { image in
                            image.resizable().scaledToFit()
                        } placeholder: {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color(hex: team.primaryColor ?? "#6B7280"))
                                .overlay(Text(team.abbreviation ?? String(team.name.prefix(1))).font(.title2).bold().foregroundStyle(.white))
                        }
                        .frame(width: 64, height: 64)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text(team.name).font(.title2).bold()
                        HStack(spacing: 8) {
                            if let record = team.record {
                                Text(record).font(.subheadline).foregroundStyle(.secondary)
                            }
                            if let sport = team.sportName {
                                Text(sport).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Championship Path
            if !data.championshipPath.isEmpty {
                Section("Championship Path") {
                    ForEach(data.championshipPath) { entry in
                        NavigationLink(value: Route.futuresDetail(id: entry.marketId)) {
                            HStack {
                                Text(entry.label).font(.subheadline)
                                Spacer()
                                if let prob = entry.probability {
                                    Text(formatPct(prob))
                                        .font(.subheadline).bold().monospacedDigit()
                                }
                                if let rank = entry.rank {
                                    Text("#\(rank)").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }

            // Upcoming Games
            if !data.upcomingEvents.isEmpty {
                Section("Upcoming") {
                    ForEach(data.upcomingEvents) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            gameRow(event, teamName: team.name)
                        }
                    }
                }
            }

            // Recent Games
            if !data.recentEvents.isEmpty {
                Section("Recent") {
                    ForEach(data.recentEvents) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            gameRow(event, teamName: team.name)
                        }
                    }
                }
            }

            // Futures
            if !data.futures.isEmpty {
                Section("Season Futures") {
                    ForEach(data.futures) { future in
                        NavigationLink(value: Route.futuresDetail(id: future.marketId)) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(future.marketName).font(.subheadline).lineLimit(1)
                                HStack(spacing: 6) {
                                    if let prob = future.probability {
                                        Text(formatPct(prob)).font(.caption).bold().monospacedDigit()
                                    }
                                    if let rank = future.rank, let total = future.totalOutcomes {
                                        Text("#\(rank) of \(total)").font(.caption2).foregroundStyle(.secondary)
                                    }
                                    Text(future.source).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(team.name)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private func gameRow(_ event: SearchEvent, teamName: String) -> some View {
        let isHome = event.homeTeam == teamName
        let opponent = isHome ? event.awayTeam : event.homeTeam
        let prefix = isHome ? "vs" : "@"

        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("\(prefix) \(opponent)").font(.subheadline).fontWeight(.medium)
                HStack(spacing: 4) {
                    StatusBadge(status: event.status)
                    if let ct = event.commenceTime {
                        RelativeTimeText(dateString: ct)
                    }
                }
            }
            Spacer()
            if let home = event.homeScore, let away = event.awayScore {
                let teamScore = isHome ? home : away
                let oppScore = isHome ? away : home
                let won = teamScore > oppScore
                Text("\(teamScore)–\(oppScore)")
                    .font(.subheadline).bold().monospacedDigit()
                    .foregroundStyle(won ? .primary : .secondary)
            } else if let odds = event.currentOdds, let homeProb = odds.homeProbability {
                let prob = isHome ? homeProb : (1 - homeProb)
                Text(formatPct(prob)).font(.subheadline).bold().monospacedDigit().foregroundStyle(.blue)
            }
        }
    }

    private func formatPct(_ p: Double) -> String {
        "\(Int(round(p * 100)))%"
    }
}
