import SwiftUI

// MARK: - View

struct LeagueGridView: View {
    let slug: String
    @StateObject private var viewModel: LeagueGridViewModel
    @State private var showAllUpcoming = false
    @State private var showAllRecent = false

    init(slug: String, preloadedViewModel: LeagueGridViewModel? = nil) {
        self.slug = slug
        _viewModel = StateObject(wrappedValue: preloadedViewModel ?? LeagueGridViewModel(slug: slug))
    }

    var body: some View {
        Group {
            if viewModel.loading && viewModel.grid == nil && viewModel.leagueMarkets == nil {
                gridSkeleton
            } else if let error = viewModel.error, viewModel.grid == nil && viewModel.leagueMarkets == nil {
                ContentUnavailableView(
                    "Error",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else {
                gridContent(viewModel.grid)
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

    private func gridContent(_ grid: ChampionshipGridResponse?) -> some View {
        List {
            // #13001 + #12932: Games first (live, upcoming, recent), then futures.
            leagueGamesSections

            if let grid {
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
            }

            // League market sections (series, awards, playoff props, etc.)
            leagueMarketSections
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    @ViewBuilder
    private var leagueGamesSections: some View {
        let live = viewModel.liveGames
        let upcoming = viewModel.upcomingGames
        let recent = viewModel.recentGames

        if viewModel.loadingMarkets && viewModel.leagueMarkets == nil {
            Section {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Loading games…")
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
        }

        if !live.isEmpty {
            gameSection(
                title: EventState.liveSectionTitle(hasSuspended: viewModel.liveHasSuspended),
                systemImage: "circle.fill",
                imageColor: .red,
                games: live,
                limit: live.count,
                expanded: .constant(true)
            )
        }

        if !upcoming.isEmpty {
            gameSection(
                title: "Upcoming",
                systemImage: "calendar",
                imageColor: .blue,
                games: upcoming,
                limit: 5,
                expanded: $showAllUpcoming
            )
        }

        if !recent.isEmpty {
            gameSection(
                title: "Just Happened",
                systemImage: "clock.arrow.circlepath",
                imageColor: .secondary,
                games: recent,
                limit: 4,
                expanded: $showAllRecent
            )
        }
    }

    private func gameSection(
        title: String,
        systemImage: String,
        imageColor: Color,
        games: [FeedEventData],
        limit: Int,
        expanded: Binding<Bool>
    ) -> some View {
        let visible = expanded.wrappedValue ? games : Array(games.prefix(limit))
        return Section {
            ForEach(visible) { event in
                NavigationLink(value: Route.eventDetail(id: event.id)) {
                    EventCardView(
                        event: event,
                        reason: nil,
                        personalizationReasons: nil,
                        headline: nil
                    )
                }
                .buttonStyle(.plain)
            }
            if games.count > limit {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        expanded.wrappedValue.toggle()
                    }
                } label: {
                    Text(expanded.wrappedValue ? "Show fewer" : "Show all \(games.count)")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blueReadable)
                }
                .buttonStyle(.borderless)
            }
        } header: {
            HStack(spacing: 6) {
                Label(title, systemImage: systemImage)
                    .foregroundStyle(imageColor)
                    .font(.subheadline.weight(.semibold))
                    .textCase(nil)
                Text("\(games.count)")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    // MARK: - League Market Sections

    // #888: the section vocabulary is `LeagueMarketSections` and is NOT restated
    // here. Two views held their own copy of these five strings, both copies named
    // two keys the API has never emitted, and `sections[key]` misses silently — so
    // the markets behind them vanished with no empty state and no count. The
    // catalog carries the measurement and the reasoning.

    @ViewBuilder
    private var leagueMarketSections: some View {
        if let leagueData = viewModel.leagueMarkets {
            ForEach(LeagueMarketSections.order, id: \.self) { key in
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
                            LeagueMarketSections.label(for: key),
                            systemImage: LeagueMarketSections.icon(for: key)
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
                let shown = NumericalMarketScaleOrder228.orderedSlice(
                    outcomes,
                    limit: 3,
                    label: \.name,
                    probability: { $0.prob / 100.0 },
                    totalOutcomeCount: market.outcomeCount ?? outcomes.count
                )?.map(\.element) ?? Array(outcomes.prefix(3))
                ForEach(Array(shown.enumerated()), id: \.offset) { _, o in
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
                if let sourceLabel = SourceLabels.cardFaceLabel(for: market.source) {
                    Text(sourceLabel)
                        .font(.caption2)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.secondary.opacity(0.1))
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
