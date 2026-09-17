import SwiftUI

// MARK: - View

struct LeagueGridView: View {
    let slug: String
    @StateObject private var viewModel: LeagueGridViewModel

    init(slug: String) {
        self.slug = slug
        _viewModel = StateObject(wrappedValue: LeagueGridViewModel(slug: slug))
    }

    var body: some View {
        Group {
            if viewModel.loading && viewModel.grid == nil {
                gridSkeleton
            } else if let error = viewModel.error, viewModel.grid == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else if let grid = viewModel.grid {
                gridContent(grid)
            }
        }
        .navigationTitle(viewModel.displayName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            await viewModel.load()
        }
        .refreshable {
            await viewModel.load()
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
            // Season info
            if let season = grid.season {
                Section {
                    HStack {
                        Text("Season")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(season)
                            .fontWeight(.medium)
                    }
                    .font(.caption)
                }
            }

            // Conference filter
            if viewModel.conferences.count > 1 {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            filterButton("All", isActive: viewModel.conferenceFilter == nil) {
                                viewModel.conferenceFilter = nil
                            }
                            ForEach(viewModel.conferences, id: \.self) { conf in
                                filterButton(conf, isActive: viewModel.conferenceFilter == conf) {
                                    viewModel.conferenceFilter = viewModel.conferenceFilter == conf ? nil : conf
                                }
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Movers (exclude zero-movement entries)
            let realMovers = grid.movers.filter { abs($0.change24H) >= 0.001 }
            if !realMovers.isEmpty {
                Section("Biggest Movers (24h)") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(realMovers) { mover in
                                moverChip(mover)
                            }
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }

            // Teams — design 2c (native grids Phase 2): a ranked list of self-labeled
            // per-team ladder cards built from the shipped LadderCardView "2b"
            // primitive, replacing the dense web-style matrix that never worked on a
            // phone. Each card carries its own milestone labels (in-cell), so no shared
            // column rail is needed; sorted by championship probability.
            Section("Championship Probabilities") {
                ForEach(Array(rankedTeams(grid.columns).enumerated()), id: \.element.id) { index, team in
                    LadderCardView(gridTeam: team, columns: grid.columns, rank: index + 1)
                        .listRowInsets(EdgeInsets(top: 5, leading: 12, bottom: 5, trailing: 12))
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
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

    // #888: these keys must be keys the API actually emits. `leagueData.sections[key]`
    // misses SILENTLY — an absent key and an empty section render identically — so
    // `playoff_props` and `novelty` dropped every market behind them for months.
    // The API builds exactly `futures · series · matches · awards · props ·
    // season_stats · more_markets` (`backend/app/routes/league_futures.py:2380`), and
    // `more_markets` is the classifier's DEFAULT return (`:1523`), which makes it the
    // biggest bucket on every league. Measured 2026-09-17: 378 markets dropped against
    // 189 rendered — NBA 11 of 64, NHL 4 of 41, UCL 3 of 38.
    //
    // `futures` and `matches` are deliberately not rendered here: neither is populated
    // for a team league, and the API omits empty sections. `LeagueGridSectionKeysMatchTheAPI888Tests`
    // pins that omission, so adding a section server-side fails a test rather than
    // disappearing.
    static let sectionOrder = ["series", "awards", "props", "season_stats", "more_markets"]
    static let sectionLabels: [String: String] = [
        "series": "Playoff Series",
        "awards": "Awards",
        // Not "Playoff Props": NCAAF's 31 are not playoff props, and most leagues
        // carrying this section are not in a playoff at all.
        "props": "Props",
        "season_stats": "Season Stats",
        "more_markets": "More Markets",
    ]
    static let sectionIcons: [String: String] = [
        "series": "sportscourt.fill",
        "awards": "trophy.fill",
        "props": "chart.bar.fill",
        "season_stats": "chart.line.uptrend.xyaxis",
        "more_markets": "sparkles",
    ]

    @ViewBuilder
    private var leagueMarketSections: some View {
        if let leagueData = viewModel.leagueMarkets {
            ForEach(Self.sectionOrder, id: \.self) { key in
                if let markets = leagueData.sections[key], !markets.isEmpty {
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
                if let sourceLabel = SourceLabels.label(for: market.source) {
                    Text(sourceLabel)
                        .font(.caption2)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(market.source == "kalshi" ? Color.green.opacity(0.1) : Color.blue.opacity(0.1))
                        .clipShape(Capsule())
                }
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

    // MARK: - Ladder ordering (design 2c)

    /// The ranked ladder list. The ordering itself lives on the view model, where a
    /// test can reach it — the rank number a reader reads is a product decision, not
    /// a rendering detail.
    private func rankedTeams(_ columns: [GridColumn]) -> [GridTeam] {
        viewModel.rankedTeams(columns)
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
        let pct = abs(mover.change24H * 100)

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
            Text(mover.shortName ?? mover.name)
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

}
