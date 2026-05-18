import SwiftUI
import Combine
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Recent Searches

enum RecentSearches {
    private static let key = "recentSearches"
    private static let maxCount = 10

    static func load() -> [String] {
        UserDefaults.standard.stringArray(forKey: key) ?? []
    }

    static func save(_ query: String) {
        var searches = load()
        // Remove if already present, then insert at front
        searches.removeAll { $0.caseInsensitiveCompare(query) == .orderedSame }
        searches.insert(query, at: 0)
        if searches.count > maxCount {
            searches = Array(searches.prefix(maxCount))
        }
        UserDefaults.standard.set(searches, forKey: key)
    }

    static func remove(_ query: String) {
        var searches = load()
        searches.removeAll { $0.caseInsensitiveCompare(query) == .orderedSame }
        UserDefaults.standard.set(searches, forKey: key)
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: key)
    }
}

// MARK: - Sport Filter for Search

private struct SearchSportFilter: Identifiable, Hashable {
    let key: String // "" means "All"
    let label: String
    let icon: String

    var id: String { key }
}

private let searchSportFilters: [SearchSportFilter] = [
    .init(key: "", label: "All", icon: ""),
    .init(key: "basketball", label: "Basketball", icon: "basketball.fill"),
    .init(key: "americanfootball", label: "Football", icon: "football.fill"),
    .init(key: "baseball", label: "Baseball", icon: "baseball.fill"),
    .init(key: "icehockey", label: "Hockey", icon: "hockey.puck.fill"),
    .init(key: "soccer", label: "Soccer", icon: "soccerball"),
    .init(key: "golf", label: "Golf", icon: "figure.golf"),
    .init(key: "mma", label: "MMA", icon: "figure.boxing"),
]

// MARK: - Quick Search Item

private struct QuickSearchItem: Identifiable {
    let icon: String
    let label: String
    let query: String
    var id: String { query }
}

// MARK: - View

struct SearchView: View {
    @StateObject private var vm = SearchViewModel()
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @FocusState private var isSearchFocused: Bool
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var path = NavigationPath()
    @State private var landscapeColumns = false

    private let quickSearches: [QuickSearchItem] = [
        .init(icon: "basketball.fill", label: "NBA", query: "NBA"),
        .init(icon: "football.fill", label: "NFL", query: "NFL"),
        .init(icon: "baseball.fill", label: "MLB", query: "MLB"),
        .init(icon: "hockey.puck.fill", label: "NHL", query: "NHL"),
        .init(icon: "soccerball", label: "Soccer", query: "Soccer"),
        .init(icon: "figure.golf", label: "Golf", query: "Golf"),
        .init(icon: "figure.boxing", label: "UFC", query: "UFC"),
    ]

    private let fallbackTrendingSearches: [QuickSearchItem] = [
        .init(icon: "chart.bar.fill", label: "Championship", query: "Championship"),
        .init(icon: "trophy.fill", label: "MVP", query: "MVP"),
    ]

    private struct CategoryLink: Identifiable {
        let icon: String
        let label: String
        let route: Route
        var id: String { label }
    }

    private let categoryLinks: [CategoryLink] = [
        .init(icon: "building.columns.fill", label: "Politics", route: .politics),
        .init(icon: "cloud.sun.fill", label: "Weather", route: .weather),
        .init(icon: "chart.line.uptrend.xyaxis", label: "Economics", route: .economics),
        .init(icon: "star.fill", label: "Entertainment", route: .entertainment),
    ]

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                searchField
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                // Sport filter chips (shown when there's a query or results)
                if !vm.query.trimmingCharacters(in: .whitespaces).isEmpty || vm.results != nil {
                    sportFilterChips
                        .padding(.bottom, 4)
                }

                if vm.loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let results = vm.results {
                    searchResults(results)
                } else if !vm.suggestions.isEmpty {
                    suggestionList
                } else if vm.query.trimmingCharacters(in: .whitespaces).count >= 2 {
                    Spacer()
                    ContentUnavailableView(
                        "Search",
                        systemImage: "magnifyingglass",
                        description: Text("Press return to search")
                    )
                    Spacer()
                } else {
                    emptyStateContent
                }
            }
            .navigationTitle("Search")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "search", type: "search")
            updateLandscapeColumns()
        }
        .task {
            await vm.loadTrending()
        }
        .onChange(of: navCoordinator.pendingSearchQuery) { _, _ in
            if navCoordinator.selectedTab == .search,
               let query = navCoordinator.consumeSearchQuery() {
                vm.query = query
                Task { await vm.search() }
            }
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            // Search tab doesn't handle route pushes — handled by feed/myStuff
        }
        #if os(iOS)
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
        #endif
    }

    // MARK: - Search Field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(isSearchFocused ? .primary : .secondary)
            TextField("Search teams, games, futures...", text: $vm.query)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                .focused($isSearchFocused)
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .submitLabel(.search)
                .onSubmit {
                    Task { await vm.search() }
                }
                .onChange(of: vm.query) { _, _ in
                    vm.onQueryChange()
                }
            if !vm.query.isEmpty {
                Button {
                    vm.query = ""
                    vm.suggestions = []
                    vm.results = nil
                    vm.selectedSport = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isSearchFocused ? Color.accentColor.opacity(0.5) : Color.clear, lineWidth: 1.5)
        )
        .animation(.easeInOut(duration: 0.2), value: isSearchFocused)
    }

    // MARK: - Sport Filter Chips

    private var sportFilterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(searchSportFilters) { filter in
                    let isSelected = vm.selectedSport == filter.key
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            vm.selectedSport = filter.key
                        }
                        vm.onSportFilterChange()
                    } label: {
                        HStack(spacing: 4) {
                            if !filter.icon.isEmpty {
                                Image(systemName: filter.icon)
                                    .font(.system(size: 10))
                            }
                            Text(filter.label)
                                .font(.caption)
                                .fontWeight(isSelected ? .semibold : .regular)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(isSelected ? Color.blue.opacity(0.15) : Color.cardBackgroundDark)
                        .foregroundStyle(isSelected ? .blue : .primary)
                        .clipShape(Capsule())
                    }
                }
            }
            .padding(.horizontal)
        }
    }

    // MARK: - Empty State with Recent + Quick Searches

    private var emptyStateContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Recent Searches
                if !vm.recentSearches.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Recent")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 4)
                            Spacer()
                            Button {
                                vm.clearRecentSearches()
                            } label: {
                                Text("Clear")
                                    .font(.caption)
                                    .foregroundStyle(.blue)
                            }
                        }

                        ForEach(vm.recentSearches, id: \.self) { recent in
                            HStack(spacing: 10) {
                                Button {
                                    vm.query = recent
                                    Task { await vm.search() }
                                } label: {
                                    HStack(spacing: 8) {
                                        Image(systemName: "clock.arrow.circlepath")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .frame(width: 20)
                                        Text(recent)
                                            .font(.subheadline)
                                            .foregroundStyle(.primary)
                                        Spacer()
                                        Image(systemName: "arrow.up.left")
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)
                                    }
                                }
                                .buttonStyle(.plain)

                                Button {
                                    vm.removeRecentSearch(recent)
                                } label: {
                                    Image(systemName: "xmark")
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    Divider()
                        .padding(.vertical, 4)
                }

                // Quick Search by Sport
                VStack(alignment: .leading, spacing: 10) {
                    Text("Browse by Sport")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    FlowLayout(spacing: 8) {
                        ForEach(quickSearches) { item in
                            quickSearchChip(icon: item.icon, label: item.label) {
                                vm.query = item.query
                                Task { await vm.search() }
                            }
                        }
                    }
                }

                // Categories (navigate to dedicated views)
                VStack(alignment: .leading, spacing: 10) {
                    Text("Categories")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    FlowLayout(spacing: 8) {
                        ForEach(categoryLinks) { item in
                            quickSearchChip(icon: item.icon, label: item.label) {
                                path.append(item.route)
                            }
                        }
                    }
                }

                // Trending / Explore
                VStack(alignment: .leading, spacing: 10) {
                    Text(vm.trendingSearches.isEmpty ? "Explore" : "Trending")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    FlowLayout(spacing: 8) {
                        if vm.trendingSearches.isEmpty {
                            ForEach(fallbackTrendingSearches) { item in
                                quickSearchChip(icon: item.icon, label: item.label) {
                                    vm.query = item.query
                                    Task { await vm.search() }
                                }
                            }
                        } else {
                            ForEach(vm.trendingSearches) { trend in
                                quickSearchChip(icon: "flame.fill", label: trend.query.capitalized) {
                                    vm.query = trend.query
                                    Task { await vm.search() }
                                }
                            }
                        }
                    }
                }

                // Hint
                HStack {
                    Spacer()
                    VStack(spacing: 6) {
                        Image(systemName: "lightbulb.min")
                            .font(.title3)
                            .foregroundStyle(.secondary.opacity(0.5))
                        Text("Try searching for a team name, player, or market")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    Spacer()
                }
                .padding(.top, 8)
            }
            .padding(.horizontal)
            .padding(.top, 12)
        }
    }

    private func quickSearchChip(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(label)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.cardBackgroundDark)
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Suggestions

    private var suggestionList: some View {
        List {
            if let dym = vm.didYouMean {
                Section {
                    Button {
                        vm.query = dym
                        vm.didYouMean = nil
                    } label: {
                        HStack(spacing: 4) {
                            Text("Showing results for")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(dym)
                                .font(.caption)
                                .fontWeight(.medium)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            ForEach(vm.suggestions) { suggestion in
                Button {
                    RecentSearches.save(suggestion.text)
                    vm.recentSearches = RecentSearches.load()

                    switch suggestion.type {
                    case "team":
                        if let slug = suggestion.teamSlug {
                            path.append(Route.teamDetail(slug: slug))
                        } else {
                            vm.query = suggestion.text
                            Task { await vm.search() }
                        }
                    case "event":
                        if let eventId = suggestion.eventId {
                            path.append(Route.eventDetail(id: eventId))
                        } else {
                            vm.query = suggestion.text
                            Task { await vm.search() }
                        }
                    case "futures":
                        if let marketId = suggestion.marketId {
                            path.append(Route.futuresDetail(id: marketId))
                        }
                    default:
                        vm.query = suggestion.text
                        Task { await vm.search() }
                    }
                } label: {
                    HStack(spacing: 10) {
                        suggestionIcon(suggestion)
                            .frame(width: 24)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(suggestion.text)
                                .font(.subheadline)
                                .lineLimit(1)
                            if suggestion.type == "event", let status = suggestion.status {
                                HStack(spacing: 4) {
                                    StatusBadge(status: status)
                                    if let ct = suggestion.commenceTime {
                                        RelativeTimeText(dateString: ct)
                                    }
                                }
                            }
                            if suggestion.type == "futures", let label = suggestion.marketTypeLabel {
                                Text(label)
                                    .font(.caption2)
                                    .foregroundStyle(.blue)
                            }
                        }
                        Spacer()
                        Text(suggestion.type == "team" ? "Team" : suggestion.type == "event" ? "Game" : "Futures")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .listStyle(.plain)
    }

    @ViewBuilder
    private func suggestionIcon(_ s: TypeaheadSuggestion) -> some View {
        if s.type == "team", let logo = s.logo, let url = URL(string: logo) {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFit()
            } placeholder: {
                Image(systemName: "basketball.fill").font(.caption).foregroundStyle(.secondary)
            }
            .frame(width: 24, height: 24)
        } else if s.type == "event" {
            Image(systemName: s.status == "live" ? "circle.fill" : "calendar")
                .font(.caption)
                .foregroundStyle(s.status == "live" ? .red : .secondary)
        } else {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - iPad Grid

    private var iPadGridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 340), spacing: 12)]
    }

    private func updateLandscapeColumns() {
        guard sizeClass == .regular else { return }
        #if os(iOS)
        let bounds = UIScreen.main.bounds
        landscapeColumns = bounds.width > bounds.height
        #else
        landscapeColumns = true
        #endif
    }

    // MARK: - Search Results

    private func searchResults(_ results: SearchResponse) -> some View {
        List {
            // Did you mean
            if let dym = results.didYouMean {
                Section {
                    HStack(spacing: 4) {
                        Text("Showing results for")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(dym)
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                }
            }

            // Teams
            if let teams = results.teams, !teams.isEmpty {
                Section {
                    ForEach(teams) { team in
                        if let slug = team.slug {
                            NavigationLink(value: Route.teamDetail(slug: slug)) {
                                searchTeamRow(team)
                            }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Label("Teams", systemImage: "person.3.fill")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .textCase(nil)
                        Text("\(teams.count)")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12))
                            .clipShape(Capsule())
                    }
                }
            }

            if !results.results.isEmpty {
                Section {
                    if sizeClass == .regular {
                        LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                            ForEach(results.results) { event in
                                Button {
                                    path.append(Route.eventDetail(id: event.id))
                                } label: {
                                    searchEventRow(event)
                                }
                                .buttonStyle(.plain)
                                .padding(12)
                                .background(Color.cardBackgroundDark)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                        }
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    } else {
                        ForEach(results.results) { event in
                            NavigationLink(value: Route.eventDetail(id: event.id)) {
                                searchEventRow(event)
                            }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Label("Events", systemImage: "figure.run")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .textCase(nil)
                        Text("\(results.results.count)")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12))
                            .clipShape(Capsule())
                    }
                }
            }

            if !results.futures.isEmpty {
                Section {
                    if sizeClass == .regular {
                        LazyVGrid(columns: iPadGridColumns, spacing: 12) {
                            ForEach(results.futures) { market in
                                Button {
                                    path.append(Route.futuresDetail(id: market.id))
                                } label: {
                                    searchFuturesRow(market)
                                }
                                .buttonStyle(.plain)
                                .padding(12)
                                .background(Color.cardBackgroundDark)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                        }
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    } else {
                        ForEach(results.futures) { market in
                            NavigationLink(value: Route.futuresDetail(id: market.id)) {
                                searchFuturesRow(market)
                            }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Label("Futures", systemImage: "chart.line.uptrend.xyaxis")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .textCase(nil)
                        Text("\(results.futures.count)")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12))
                            .clipShape(Capsule())
                    }
                }
            }

            if results.results.isEmpty && results.futures.isEmpty && (results.teams ?? []).isEmpty {
                ContentUnavailableView(
                    "No Results",
                    systemImage: "magnifyingglass",
                    description: Text("No results found for \"\(results.query)\".")
                )
                .listRowBackground(Color.clear)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    // MARK: - Event Row

    private func searchEventRow(_ event: SearchEvent) -> some View {
        HStack(spacing: 10) {
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
                    StatusBadge(status: event.status)
                    if event.status == "scheduled", let ct = event.commenceTime {
                        RelativeTimeText(dateString: ct)
                    }
                }
            }

            Spacer()

            if event.status == "completed" || event.status == "closed" {
                if let away = event.awayScore, let home = event.homeScore {
                    Text("\(away) - \(home)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .monospacedDigit()
                }
            } else if let odds = event.currentOdds,
                      let home = odds.homeProbability {
                Text(formatProbability(home))
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .monospacedDigit()
                    .foregroundStyle(.blue)
            }

            if let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Team Row

    private func searchTeamRow(_ team: SearchTeam) -> some View {
        HStack(spacing: 10) {
            if let logo = team.logo, let url = URL(string: logo) {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    RoundedRectangle(cornerRadius: 4).fill(Color.secondary.opacity(0.2))
                }
                .frame(width: 32, height: 32)
            } else {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.secondary.opacity(0.2))
                    .frame(width: 32, height: 32)
                    .overlay(Text(team.abbreviation ?? String(team.name.prefix(1))).font(.caption2).bold())
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(team.name).font(.subheadline).fontWeight(.medium)
                HStack(spacing: 6) {
                    if let record = team.record {
                        Text(record).font(.caption2).foregroundStyle(.secondary)
                    }
                    if let sport = team.sportKey {
                        Text(sport.split(separator: "_").dropFirst().joined(separator: " ").uppercased())
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            Spacer()
        }
        .padding(.vertical, 2)
    }

    // MARK: - Futures Row

    private func searchFuturesRow(_ market: SearchFuturesMarket) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(market.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            HStack(spacing: 6) {
                if let category = market.llmSportCategory ?? market.category {
                    Text(category.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let source = market.source {
                    searchSourceBadge(source)
                }
            }

            if let outcomes = market.topOutcomes, let top = outcomes.first {
                HStack(spacing: 4) {
                    Text(top.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let prob = top.probability {
                        Text(formatProbability(prob))
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func searchSourceBadge(_ source: String) -> some View {
        let label: String
        let color: Color
        switch source {
        case "polymarket":
            label = "Polymarket"
            color = .blue
        case "kalshi":
            label = "Kalshi"
            color = Color(hex: "#22c55e")
        case "odds_api":
            label = "Sportsbooks"
            color = Color(hex: "#d97706")
        default:
            label = source.capitalized
            color = .gray
        }
        return Text(label)
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}
