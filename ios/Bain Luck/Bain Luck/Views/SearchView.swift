import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "search")

// MARK: - Recent Searches

private enum RecentSearches {
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

// MARK: - ViewModel

final class SearchViewModel: ObservableObject {
    @Published var query = ""
    @Published var suggestions: [TypeaheadSuggestion] = []
    @Published var results: SearchResponse?
    @Published var loading = false
    @Published var error: String?
    @Published var selectedSport = ""
    @Published var recentSearches: [String] = []

    private var debounceTask: Task<Void, Never>?

    init() {
        recentSearches = RecentSearches.load()
    }

    @MainActor
    func onQueryChange() {
        debounceTask?.cancel()

        let trimmed = query.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            suggestions = []
            results = nil
            return
        }

        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
            guard !Task.isCancelled else { return }
            await fetchTypeahead(trimmed)
        }
    }

    @MainActor
    func search() async {
        debounceTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 2 else { return }

        loading = true
        do {
            let sport = selectedSport.isEmpty ? nil : selectedSport
            results = try await APIClient.shared.fetchSearch(query: trimmed, sport: sport)
            suggestions = []
            error = nil
            loading = false
            let totalResults = (results?.results.count ?? 0) + (results?.futures.count ?? 0)
            AnalyticsService.trackSearch(query: trimmed, resultsCount: totalResults)

            // Save to recent searches
            RecentSearches.save(trimmed)
            recentSearches = RecentSearches.load()
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Search failed: \(error)")
        }
    }

    @MainActor
    func onSportFilterChange() {
        // Re-search with new sport filter if we have results
        if results != nil {
            Task { await search() }
        }
    }

    func removeRecentSearch(_ query: String) {
        RecentSearches.remove(query)
        recentSearches = RecentSearches.load()
    }

    func clearRecentSearches() {
        RecentSearches.clear()
        recentSearches = []
    }

    @MainActor
    private func fetchTypeahead(_ q: String) async {
        do {
            let response = try await APIClient.shared.fetchTypeahead(query: q)
            guard !Task.isCancelled else { return }
            suggestions = response.suggestions
        } catch {
            logger.error("Typeahead failed: \(error)")
        }
    }
}

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
    @EnvironmentObject var navCoordinator: NavigationCoordinator
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

    private let trendingSearches: [QuickSearchItem] = [
        .init(icon: "chart.bar.fill", label: "Championship", query: "Championship"),
        .init(icon: "trophy.fill", label: "MVP", query: "MVP"),
        .init(icon: "building.columns.fill", label: "Politics", query: "Politics"),
        .init(icon: "bitcoinsign.circle.fill", label: "Crypto", query: "Crypto"),
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
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EIRankingsView()
                case .preferences:
                    PreferencesView()
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                case .leagueGrid(let slug):
                    LeagueGridView(slug: slug)
                case .golfCategory:
                    Text("Golf Category")
                case .golfLeaderboard:
                    MastersLiveView()
                case .golfTournament(_, let name):
                    SportCategoryView(categoryKey: "golf", categoryName: name)
                case .futuresList:
                    FuturesListView()
                }
            }
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "search", type: "search")
            // Auto-focus the search field when tab appears
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                isSearchFocused = true
            }
            updateLandscapeColumns()
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
        .onReceive(NotificationCenter.default.publisher(for: UIDevice.orientationDidChangeNotification)) { _ in
            updateLandscapeColumns()
        }
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
        .background(Color(.secondarySystemGroupedBackground))
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
                        .background(isSelected ? Color.blue.opacity(0.15) : Color(.tertiarySystemGroupedBackground))
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

                // Trending / Explore
                VStack(alignment: .leading, spacing: 10) {
                    Text("Explore")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    FlowLayout(spacing: 8) {
                        ForEach(trendingSearches) { item in
                            quickSearchChip(icon: item.icon, label: item.label) {
                                vm.query = item.query
                                Task { await vm.search() }
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
            .background(Color(.tertiarySystemGroupedBackground))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Suggestions

    private var suggestionList: some View {
        List(vm.suggestions) { suggestion in
            Button {
                if suggestion.type == "futures", suggestion.marketId != nil {
                    // Navigate directly to futures detail
                    vm.query = suggestion.text
                    vm.results = nil
                    vm.suggestions = []
                    // Use NavigationLink value instead — handle via search
                    vm.query = suggestion.text
                    Task { await vm.search() }
                } else {
                    // For events, trigger a full search
                    vm.query = suggestion.text
                    Task { await vm.search() }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: suggestion.type == "futures" ? "chart.line.uptrend.xyaxis" : "figure.run")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(width: 20)
                    Text(suggestion.text)
                        .font(.subheadline)
                        .lineLimit(1)
                    Spacer()
                    Image(systemName: "arrow.up.left")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .buttonStyle(.plain)
        }
        .listStyle(.plain)
    }

    // MARK: - iPad Grid

    private var iPadGridColumns: [GridItem] {
        let count = landscapeColumns ? 3 : 2
        return Array(repeating: GridItem(.flexible(), spacing: 12), count: count)
    }

    private func updateLandscapeColumns() {
        guard sizeClass == .regular else { return }
        let bounds = UIScreen.main.bounds
        landscapeColumns = bounds.width > bounds.height
    }

    // MARK: - Search Results

    private func searchResults(_ results: SearchResponse) -> some View {
        List {
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
                                .background(Color(.tertiarySystemGroupedBackground))
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
                                .background(Color(.tertiarySystemGroupedBackground))
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

            if results.results.isEmpty && results.futures.isEmpty {
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
