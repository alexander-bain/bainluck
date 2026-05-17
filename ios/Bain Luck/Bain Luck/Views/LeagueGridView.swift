import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "leagueGrid")

private let sourceLabels: [String: String] = [
    "odds_api": "Sportsbooks",
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
    "datagolf": "DataGolf",
]

// Grid slug → full sport key for league markets API
private let slugToSportKey: [String: String] = [
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "wnba": "basketball_wnba",
    "ncaa-basketball": "basketball_ncaab",
    "ncaa-women-basketball": "basketball_ncaab",
    "ncaa-football": "americanfootball_ncaaf",
    "epl": "soccer_epl",
    "mls": "soccer_usa_mls",
    "la-liga": "soccer_spain_la_liga",
    "champions-league": "soccer_uefa_champs_league",
    "bundesliga": "soccer_germany_bundesliga",
    "golf": "golf",
]

// MARK: - ViewModel

final class LeagueGridViewModel: ObservableObject {
    let slug: String
    @Published var grid: ChampionshipGridResponse?
    @Published var leagueMarkets: LeagueMarketsResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var conferenceFilter: String?

    init(slug: String) {
        self.slug = slug
    }

    var displayName: String {
        grid?.name ?? slug.replacingOccurrences(of: "-", with: " ").uppercased()
    }

    var conferences: [String] {
        guard let grid else { return [] }
        if let grouped = grid.groupedTeams {
            return grouped.keys.sorted().filter { $0 != "Other" }
        }
        return []
    }

    var visibleTeams: [GridTeam] {
        guard let grid else { return [] }
        if let grouped = grid.groupedTeams {
            if let filter = conferenceFilter {
                return grouped[filter] ?? []
            }
            return grouped.values.flatMap { $0 }
        }
        if let filter = conferenceFilter {
            return grid.teams.filter { $0.conference == filter }
        }
        return grid.teams
    }

    /// In-memory cache shared across instances
    private static var cache: [String: (grid: ChampionshipGridResponse, date: Date)] = [:]

    @MainActor
    func load() async {
        // Show cached data immediately while refreshing in background
        if grid == nil, let cached = Self.cache[slug] {
            grid = cached.grid
            // If cache is fresh enough (<60s), skip network
            if Date().timeIntervalSince(cached.date) < 60 {
                await loadLeagueMarkets()
                return
            }
        }

        loading = true
        do {
            async let gridTask = APIClient.shared.fetchChampionshipGrid(slug: slug)
            async let marketsTask = loadLeagueMarkets()
            let freshGrid = try await gridTask
            _ = await marketsTask
            grid = freshGrid
            Self.cache[slug] = (freshGrid, Date())
            error = nil
        } catch {
            // Only show error if we have no cached data
            if grid == nil {
                self.error = error.localizedDescription
            }
            logger.error("Grid load failed for \(self.slug): \(error)")
        }
        loading = false
    }

    @MainActor
    private func loadLeagueMarkets() async {
        let sportKey = slugToSportKey[slug] ?? slug
        do {
            leagueMarkets = try await APIClient.shared.fetchLeagueMarkets(sportKey: sportKey)
            logger.info("League markets for \(self.slug): \(self.leagueMarkets?.totalMarkets ?? 0) total")
        } catch {
            logger.debug("League markets not available for \(self.slug): \(error)")
        }
    }
}

// MARK: - View

struct LeagueGridView: View {
    let slug: String
    @StateObject private var vm: LeagueGridViewModel

    init(slug: String) {
        self.slug = slug
        _vm = StateObject(wrappedValue: LeagueGridViewModel(slug: slug))
    }

    var body: some View {
        Group {
            if vm.loading && vm.grid == nil {
                gridSkeleton
            } else if let error = vm.error, vm.grid == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let grid = vm.grid {
                gridContent(grid)
            }
        }
        .navigationTitle(vm.displayName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "league_grid_\(slug)", type: "playoff_grid")
        }
    }

    // MARK: - Skeleton Loading

    private var gridSkeleton: some View {
        List {
            Section {
                ForEach(0..<8, id: \.self) { _ in
                    HStack {
                        Circle()
                            .fill(Color.secondary.opacity(0.15))
                            .frame(width: 20, height: 20)
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.secondary.opacity(0.15))
                            .frame(width: 80, height: 14)
                        Spacer()
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.secondary.opacity(0.1))
                            .frame(width: 40, height: 14)
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.secondary.opacity(0.1))
                            .frame(width: 40, height: 14)
                    }
                    .padding(.vertical, 2)
                }
            } header: {
                Text("Championship Probabilities")
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .redacted(reason: .placeholder)
    }

    // MARK: - Grid Content

    private func gridContent(_ grid: ChampionshipGridResponse) -> some View {
        List {
            // Sources + season
            Section {
                if let season = grid.season {
                    HStack {
                        Text("Season")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(season)
                            .fontWeight(.medium)
                    }
                    .font(.caption)
                }
                HStack {
                    Text("Sources")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    HStack(spacing: 4) {
                        ForEach(grid.sourcesAvailable, id: \.self) { source in
                            Text(sourceLabels[source] ?? source.capitalized)
                                .font(.system(size: 10, weight: .medium))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.secondary.opacity(0.12))
                                .clipShape(Capsule())
                        }
                    }
                }
            }

            // Conference filter
            if vm.conferences.count > 1 {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            filterButton("All", isActive: vm.conferenceFilter == nil) {
                                vm.conferenceFilter = nil
                            }
                            ForEach(vm.conferences, id: \.self) { conf in
                                filterButton(conf, isActive: vm.conferenceFilter == conf) {
                                    vm.conferenceFilter = vm.conferenceFilter == conf ? nil : conf
                                }
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Movers
            if !grid.movers.isEmpty {
                Section("Biggest Movers (24h)") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(grid.movers) { mover in
                                moverChip(mover)
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Teams grid
            Section("Championship Probabilities") {
                // Column headers
                HStack {
                    Text("Team")
                        .frame(maxWidth: .infinity, alignment: .leading)
                    ForEach(grid.columns, id: \.key) { col in
                        Text(col.label)
                            .frame(width: columnWidth(grid.columns.count))
                    }
                }
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)

                ForEach(vm.visibleTeams) { team in
                    teamRow(team, columns: grid.columns)
                }
            }

            // League market sections (series, awards, playoff props, etc.)
            leagueMarketSections
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    // MARK: - League Market Sections

    private static let sectionOrder = ["series", "awards", "playoff_props", "season_stats", "novelty"]
    private static let sectionLabels: [String: String] = [
        "series": "Playoff Series",
        "awards": "Awards",
        "playoff_props": "Playoff Props",
        "season_stats": "Season Stats",
        "novelty": "More Markets",
    ]
    private static let sectionIcons: [String: String] = [
        "series": "sportscourt.fill",
        "awards": "trophy.fill",
        "playoff_props": "chart.bar.fill",
        "season_stats": "chart.line.uptrend.xyaxis",
        "novelty": "sparkles",
    ]

    @ViewBuilder
    private var leagueMarketSections: some View {
        if let lm = vm.leagueMarkets {
            ForEach(Self.sectionOrder, id: \.self) { key in
                if let markets = lm.sections[key], !markets.isEmpty {
                    Section {
                        ForEach(markets.prefix(8)) { market in
                            NavigationLink(value: Route.futuresDetail(id: market.id)) {
                                leagueMarketRow(market)
                            }
                        }
                        if markets.count > 8 {
                            Text("+\(markets.count - 8) more")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } header: {
                        Label(
                            Self.sectionLabels[key] ?? key.capitalized,
                            systemImage: Self.sectionIcons[key] ?? "list.bullet"
                        )
                    }
                }
            }
        }
    }

    private func leagueMarketRow(_ market: LeagueMarketItem) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(market.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            if let outcomes = market.topOutcomes, !outcomes.isEmpty {
                ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { _, o in
                    HStack(spacing: 4) {
                        Text(o.name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text("\(Int(o.prob))%")
                            .font(.caption)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    }
                }
            }

            HStack(spacing: 4) {
                Text(sourceLabels[market.source] ?? market.source.capitalized)
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(market.source == "kalshi" ? Color.green.opacity(0.1) : Color.blue.opacity(0.1))
                    .clipShape(Capsule())
                if let count = market.outcomeCount, count > 3 {
                    Text("+\(count - 3) more")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Team Row

    private func teamRow(_ team: GridTeam, columns: [GridColumn]) -> some View {
        HStack {
            // Team name with logo
            HStack(spacing: 6) {
                if let logoUrl = team.logoUrl, let url = URL(string: logoUrl) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().aspectRatio(contentMode: .fit)
                        default:
                            teamColorDot(team.primaryColor)
                        }
                    }
                    .frame(width: 20, height: 20)
                } else {
                    teamColorDot(team.primaryColor)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(team.shortName ?? team.name)
                        .font(.caption)
                        .fontWeight(.medium)
                        .lineLimit(1)
                    if let record = team.record {
                        Text(record)
                            .font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Probability cells
            ForEach(columns, id: \.key) { col in
                let cell = team.cells[col.key]
                probabilityCell(cell, columnCount: columns.count)
                    .frame(width: columnWidth(columns.count))
            }
        }
        .padding(.vertical, 2)
    }

    private func probabilityCell(_ cell: GridCell?, columnCount: Int) -> some View {
        Group {
            if let prob = cell?.mergedProbability {
                VStack(spacing: 1) {
                    Text(formatProb(prob))
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    if let trend = cell?.trend24h, abs(trend) >= 0.005 {
                        HStack(spacing: 1) {
                            Image(systemName: trend > 0 ? "arrow.up" : "arrow.down")
                                .font(.system(size: 6))
                            Text(formatProb(abs(trend)))
                                .font(.system(size: 8))
                        }
                        .foregroundStyle(trend > 0 ? .green : .red)
                    }
                }
            } else {
                Text("-")
                    .font(.caption)
                    .foregroundStyle(.quaternary)
            }
        }
    }

    // MARK: - Helpers

    private func filterButton(_ label: String, isActive: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.caption)
                .fontWeight(.medium)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isActive ? Color.accentColor.opacity(0.2) : Color.cardBackground)
                .foregroundStyle(isActive ? Color.accentColor : Color.secondary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private func moverChip(_ mover: GridMover) -> some View {
        let isUp = mover.direction == "up"
        let pct = abs(mover.change24h * 100)

        return HStack(spacing: 4) {
            if let logoUrl = mover.logoUrl, let url = URL(string: logoUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().aspectRatio(contentMode: .fit)
                    default:
                        EmptyView()
                    }
                }
                .frame(width: 16, height: 16)
            }
            Text(mover.shortName ?? String(mover.name.prefix(6)))
                .font(.caption)
                .fontWeight(.medium)
            Text("\(isUp ? "+" : "-")\(pct >= 1 ? String(format: "%.0f", pct) : String(format: "%.1f", pct))%")
                .font(.system(size: 11, weight: .medium, design: .monospaced))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(isUp ? Color.green.opacity(0.1) : Color.red.opacity(0.1))
        .foregroundStyle(isUp ? .green : .red)
        .clipShape(Capsule())
        .overlay(Capsule().stroke(isUp ? Color.green.opacity(0.2) : Color.red.opacity(0.2), lineWidth: 1))
    }

    private func teamColorDot(_ hex: String?) -> some View {
        Circle()
            .fill(hex.flatMap { Color(hex: $0) } ?? Color.secondary)
            .frame(width: 12, height: 12)
    }

    private func columnWidth(_ count: Int) -> CGFloat {
        count <= 3 ? 65 : count <= 5 ? 55 : 48
    }

    private func formatProb(_ p: Double) -> String {
        let pct = p * 100
        if pct >= 99.5 { return ">99%" }
        if pct < 0.5 && pct > 0 { return "<1%" }
        if pct >= 10 { return String(format: "%.0f%%", pct) }
        return String(format: "%.1f%%", pct)
    }
}
