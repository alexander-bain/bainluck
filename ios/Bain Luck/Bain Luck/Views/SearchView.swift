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

/// The filter row for one search, derived from the server's `sports` facet.
///
/// This replaces a hard-coded list of seven sport FAMILIES. The API's `sport`
/// parameter is an exact `Sport.key` match, so none of those seven ever matched
/// anything (`?q=lakers&sport=basketball` → 0 results while the same query
/// unfiltered returns 5 NBA events). Building the row from the facet fixes all
/// seven and answers Alex's report at the same time: search a tennis player and
/// a tennis pill is there, because the results are tennis.
private func searchSportFilters(for facets: [SportFacet]) -> [SearchSportFilter] {
    guard !facets.isEmpty else { return [] }
    return [.init(key: "", label: "All", icon: "")] + facets.map {
        .init(key: $0.key, label: $0.name, icon: sportSymbolName(forSportKey: $0.key))
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
    @StateObject private var viewModel = SearchViewModel()
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @FocusState private var isSearchFocused: Bool
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var path = NavigationPath()

    /// Width available to the iPad card grids, in points. 0 until the first
    /// geometry pass resolves, which `DiscoverMasonry` reads as one column
    /// (#3723). Shared by both grids because they are two sections of the same
    /// `List` and are therefore always the same width.
    @State private var gridWidth: CGFloat = 0

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

                // Sport filter chips. Gated on the FACET, not on "there is a
                // query": with the row derived from the results there is nothing
                // honest to draw until a search has come back.
                let sportFilters = searchSportFilters(for: viewModel.sportFacets)
                if !sportFilters.isEmpty {
                    sportFilterChips(sportFilters)
                        .padding(.bottom, 4)
                }

                if viewModel.loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let results = viewModel.results {
                    searchResults(results)
                } else if !viewModel.suggestions.isEmpty {
                    suggestionList
                } else if viewModel.query.trimmingCharacters(in: .whitespaces).count >= 2 {
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
        }
        .onDisappear {
            // Navigating away invalidates any in-flight typeahead/search so a
            // late response can't publish onto an absent surface (L2-198).
            viewModel.cancelInFlightWork()
        }
        .task {
            consumePendingSearchQuery()
            await viewModel.loadTrending()
        }
        .onChange(of: navCoordinator.pendingSearchQuery) { _, _ in
            consumePendingSearchQuery()
        }
        .onChange(of: navCoordinator.pendingRoute) { _, _ in
            // Search tab doesn't handle route pushes — handled by feed/myStuff
        }
        // The orientation observer that used to live here drove
        // `landscapeColumns`, which nothing read (#3723). Its only real effect
        // was a `UIScreen.main.bounds` read — gotcha #27, the Stage Manager
        // trap, which measures the SCREEN and not the window. Column count now
        // comes from a `GeometryReader` on the grid itself, which IS the window
        // and updates on rotation without an observer.
    }

    /// Drains a deep-link query (`bainluck://search?q=…`) onto the field.
    ///
    /// Called on mount AND on change, because neither alone is enough. A TabView
    /// builds SearchView lazily, and `NavigationCoordinator.handleURL` selects
    /// the tab and sets the query in the same tick — so on a cold open the
    /// value has already changed by the time this view exists and `.onChange`
    /// never fires, and the reader who followed a search link lands on an empty
    /// Search screen. `.onAppear` alone would miss the warm case, where the view
    /// is already mounted and only the value moves. The query stays pending in
    /// the coordinator until one of the two drains it, so exactly one does
    /// (#3157).
    private func consumePendingSearchQuery() {
        guard navCoordinator.selectedTab == .search,
              let query = navCoordinator.consumeSearchQuery() else { return }
        viewModel.query = query
        Task { await viewModel.search() }
    }

    // MARK: - Search Field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(isSearchFocused ? .primary : .secondary)
            TextField("Search teams, games, futures...", text: $viewModel.query)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                .focused($isSearchFocused)
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .submitLabel(.search)
                .onSubmit {
                    Task { await viewModel.search() }
                }
                .onChange(of: viewModel.query) { _, _ in
                    viewModel.onQueryChange()
                }
            if !viewModel.query.isEmpty {
                Button {
                    // Cancels in-flight work first so a late response can't
                    // repopulate the field we're clearing (L2-198), then resets
                    // every piece of search state including the facet row.
                    viewModel.clear()
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

    private func sportFilterChips(_ filters: [SearchSportFilter]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(filters) { filter in
                    let isSelected = viewModel.selectedSport == filter.key
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            viewModel.selectedSport = filter.key
                        }
                        viewModel.onSportFilterChange()
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
                if !viewModel.recentSearches.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Recent")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 4)
                            Spacer()
                            Button {
                                viewModel.clearRecentSearches()
                            } label: {
                                Text("Clear")
                                    .font(.caption)
                                    .foregroundStyle(.blue)
                            }
                        }

                        ForEach(viewModel.recentSearches, id: \.self) { recent in
                            HStack(spacing: 10) {
                                Button {
                                    viewModel.query = recent
                                    Task { await viewModel.search() }
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
                                    viewModel.removeRecentSearch(recent)
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

                // Tournaments with a hub screen. These navigate straight to the
                // hub rather than seeding a text query, because the query is the
                // thing that does not work: "US Open" matches no event text.
                if !featuredTournaments.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Tournaments")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)

                        FlowLayout(spacing: 8) {
                            ForEach(featuredTournaments) { hub in
                                quickSearchChip(icon: hub.icon, label: hub.title) {
                                    path.append(Route.tournamentHub(slug: hub.slug, name: hub.title))
                                }
                            }
                        }
                    }
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
                                viewModel.query = item.query
                                Task { await viewModel.search() }
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
                    Text(viewModel.trendingSearches.isEmpty ? "Explore" : "Trending")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    FlowLayout(spacing: 8) {
                        if viewModel.trendingSearches.isEmpty {
                            ForEach(fallbackTrendingSearches) { item in
                                quickSearchChip(icon: item.icon, label: item.label) {
                                    viewModel.query = item.query
                                    Task { await viewModel.search() }
                                }
                            }
                        } else {
                            ForEach(viewModel.trendingSearches) { trend in
                                quickSearchChip(icon: "flame.fill", label: trend.query.capitalized) {
                                    viewModel.query = trend.query
                                    Task { await viewModel.search() }
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
            if let dym = viewModel.didYouMean {
                Section {
                    Button {
                        viewModel.query = dym
                        viewModel.didYouMean = nil
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

            ForEach(viewModel.suggestions) { suggestion in
                Button {
                    RecentSearches.save(suggestion.text)
                    viewModel.recentSearches = RecentSearches.load()

                    switch suggestion.type {
                    case "team":
                        if let slug = suggestion.teamSlug {
                            path.append(Route.teamDetail(slug: slug))
                        } else {
                            viewModel.query = suggestion.text
                            Task { await viewModel.search() }
                        }
                    case "event":
                        if let eventId = suggestion.eventId {
                            path.append(Route.eventDetail(id: eventId))
                        } else {
                            viewModel.query = suggestion.text
                            Task { await viewModel.search() }
                        }
                    case "futures":
                        if let marketId = suggestion.marketId {
                            path.append(Route.futuresDetail(id: marketId))
                        }
                    default:
                        viewModel.query = suggestion.text
                        Task { await viewModel.search() }
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
                                    if let commenceTime = suggestion.commenceTime {
                                        RelativeTimeText(dateString: commenceTime)
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

    /// Both iPad card grids on this screen — Events and More markets — rendered
    /// as a masonry deal rather than a `LazyVGrid` (#3723).
    ///
    /// `LazyVGrid` lays out in ROWS and pads every cell to the tallest cell in
    /// its row; see `DiscoverMasonry` for the whole story. #3709 fixed three
    /// other `List`-backed surfaces and deliberately excused this file, on the
    /// grounds that each of its two grids is built by a single row function and
    /// so has no tall/short pairing. **One row builder is not one shape.**
    /// `searchFuturesRow` has a `lineLimit(2)` title, a badge row that is empty
    /// when the market has neither a category nor a source, and a top-outcome
    /// row that is absent when there are no outcomes — at least four heights,
    /// and any width.
    ///
    /// MEASURED on `bainluck://search?q=US%20Open`, iPad Pro 11-inch, "More
    /// markets" (`artifacts-native-046/MEASUREMENT.md`). "US Open Winner" is a
    /// one-line title with no outcome row; every other card in the grid has a
    /// two-line title and an outcome row:
    ///
    ///     card               width    height
    ///     US Open Winner     291 px   164 px
    ///     all the others    ~721 px   204 px
    ///
    /// Two separate defects, and the grid is only one of them:
    ///
    /// 1. **The row padding**, 20 px above the short card and 20 px below it.
    ///    The left column's inter-row gap read 44 px against the right column's
    ///    24 px, and 24 px *is* the 12 pt design spacing — so the right column
    ///    is the control and it does not move. Fixed by the deal: a `VStack`
    ///    packs its children at exactly its spacing, so no cell can be padded
    ///    to a neighbour at any column count.
    ///
    /// 2. **The card does not fill its column** — 291 px of a ~721 px column,
    ///    centred, with 261 px of empty page to its left and 269 px to its
    ///    right, lining up with nothing. `searchFuturesRow` is a
    ///    `VStack(alignment: .leading)` whose intrinsic width is its longest
    ///    line, and nothing asked it to fill the cell. A grid is not what was
    ///    wrong here and the deal alone would not have fixed it: the
    ///    `.frame(maxWidth: .infinity, alignment: .leading)` below is what does,
    ///    and it sits INSIDE the `.padding(12)` so the card grows to the column
    ///    rather than to the column plus 24 px.
    ///
    /// The three surfaces #3709 converted do not have the second defect —
    /// measured at 750 px in both columns on
    /// `artifacts-native-045/AFTER-ipad-category-tennis.png` — because their
    /// cards' content fills on its own. This is why the fix is scoped here.
    ///
    /// The scaffolding below is now the fifth inline copy of the deal
    /// (`FeedView` has two, `SportCategoryView` and `MyStuffView` one each).
    /// Lifting it into one shared view is the right end state and is filed
    /// rather than done here: it would touch `MyStuffView`, which cannot be
    /// photographed behind its sign-in wall, on top of a #3709 that has not yet
    /// reached production.
    @ViewBuilder
    private func iPadCardGrid<Item: Identifiable, Card: View>(
        _ items: [Item],
        @ViewBuilder card: @escaping (Item) -> Card
    ) -> some View {
        let columnCount = DiscoverMasonry.listColumnCount(availableWidth: gridWidth)
        let masonryColumns = DiscoverMasonry.columns(
            cardCount: items.count,
            columnCount: columnCount
        )
        HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
            ForEach(Array(masonryColumns.enumerated()), id: \.offset) { _, indices in
                VStack(spacing: DiscoverMasonry.listCardSpacing) {
                    ForEach(indices, id: \.self) { idx in
                        card(items[idx])
                            .buttonStyle(.plain)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.cardBackgroundDark)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { gridWidth = geo.size.width }
                    .onChange(of: geo.size.width) { _, newValue in
                        gridWidth = newValue
                    }
            }
        )
    }

    // MARK: - Search Results

    private func searchResults(_ results: SearchResponse) -> some View {
        List {
            // Tournament hubs the query names, above everything else.
            //
            // Searching "US Open" during the US Open returned no events at all —
            // the matches are there (`tennis_atp_us_open`, Alcaraz vs Paul) but
            // nothing in an event's searchable text says "US Open", so the whole
            // tournament came back as ten loose futures rows and no way in. The
            // hub is the answer to that query and it goes first.
            let hubs = featuredTournaments(matching: results.query)
            if !hubs.isEmpty {
                Section {
                    ForEach(hubs) { hub in
                        NavigationLink(value: Route.tournamentHub(slug: hub.slug, name: hub.title)) {
                            searchTournamentRow(hub)
                        }
                    }
                } header: {
                    Label("Tournament", systemImage: "trophy.fill")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }

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
                        // #3723. `searchEventRow` is an `HStack` with a
                        // `Spacer()` and a `lineLimit(1)` title, so this grid
                        // really was close to uniform and it is not the one the
                        // measurement caught. It is converted anyway: it held
                        // the same idiom, and "close to uniform" is the excuse
                        // that left the futures grid broken for two sessions.
                        iPadCardGrid(results.results) { event in
                            Button {
                                path.append(Route.eventDetail(id: event.id))
                            } label: {
                                searchEventRow(event)
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

            // #3124: the server already grouped these. Ten sibling rows for
            // "US Open" — the same two questions, twice each, once per source —
            // were ten rows because the phone decoded `futures` and threw
            // `futures_families` away. Families draw first, as one answer each,
            // and their markets come OUT of the flat list below so nothing is
            // drawn twice. Backend is the composition source of truth; the phone
            // only decides what to show, exactly as `/search` does on the web.
            let families = results.futuresFamilies ?? []
            let flatFutures = SearchGrouping.flatFutures(results.futures, families: families)

            ForEach(families) { family in
                Section {
                    NavigationLink(value: Route.futuresDetail(id: family.headline.id)) {
                        searchFamilyRow(family.headline, prominent: true)
                    }
                    ForEach(family.members) { member in
                        NavigationLink(value: Route.futuresDetail(id: member.id)) {
                            searchFamilyRow(member, prominent: false)
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Label(family.label, systemImage: "square.stack.3d.up.fill")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .textCase(nil)
                        // Counts the rows this section DRAWS, like every other
                        // header here — never `memberCount`, which counts members
                        // the payload does not carry.
                        Text("\(family.members.count + 1)")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12))
                            .clipShape(Capsule())
                    }
                } footer: {
                    if let more = SearchGrouping.moreBelowLabel(family) {
                        Text(more)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Concepts the page does not already draw as markets. Almost always
            // empty — see `SearchGrouping.novelConcepts` for the measurement and
            // why drawing them unfiltered would re-create the very duplication
            // the families above remove.
            let concepts = SearchGrouping.novelConcepts(
                results.eventConcepts ?? [],
                families: families,
                flatFutures: flatFutures
            )
            if !concepts.isEmpty {
                Section {
                    ForEach(concepts) { concept in
                        if let marketId = concept.marketId {
                            NavigationLink(value: Route.futuresDetail(id: marketId)) {
                                searchConceptRow(concept)
                            }
                        }
                    }
                } header: {
                    Label("Events", systemImage: "calendar")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }

            if !flatFutures.isEmpty {
                Section {
                    if sizeClass == .regular {
                        // #3723 — the grid that was measured. This is where
                        // "US Open Winner" was drawn 291 px wide in a 721 px
                        // column, centred, with 20 px of dead space above and
                        // below it.
                        iPadCardGrid(flatFutures) { market in
                            Button {
                                path.append(Route.futuresDetail(id: market.id))
                            } label: {
                                searchFuturesRow(market)
                            }
                        }
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    } else {
                        ForEach(flatFutures) { market in
                            NavigationLink(value: Route.futuresDetail(id: market.id)) {
                                searchFuturesRow(market)
                            }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        // "More markets" once families have taken the headline
                        // answers: calling this section "Futures" above a family
                        // card would imply the family was something else.
                        Label(families.isEmpty ? "Futures" : "More markets",
                              systemImage: "chart.line.uptrend.xyaxis")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .textCase(nil)
                        Text("\(flatFutures.count)")
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

            // A hub counts as a result. Saying "No results found for US Open"
            // above a US Open hub row would be the page contradicting itself.
            // Families count too: they can carry a headline the flat `futures`
            // slice had no room for, so a page with a family is never empty.
            if results.results.isEmpty && results.futures.isEmpty
                && families.isEmpty && concepts.isEmpty
                && (results.teams ?? []).isEmpty && hubs.isEmpty {
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

    // MARK: - Tournament Row

    private func searchTournamentRow(_ hub: FeaturedTournament) -> some View {
        HStack(spacing: 10) {
            Image(systemName: hub.icon)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(Color.yellow.gradient, in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(hub.title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text(hub.subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()
        }
        .padding(.vertical, 2)
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
                    if event.status == "scheduled", let commenceTime = event.commenceTime {
                        RelativeTimeText(dateString: commenceTime)
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

    // MARK: - Family Rows (#3124)

    /// One answer inside a family card: the question on the left, its leader and
    /// probability on the right.
    ///
    /// Deliberately NOT `searchFuturesRow`. That row exists to tell loose results
    /// apart, so it prints the source badge and the category — and inside a family
    /// those are the two things that made the page look broken, because the
    /// duplicate pair differs by nothing else. Here the source is dropped: which
    /// venue is quoting is not the reader's question (the blend is the product),
    /// and a family is a set of questions, so the answer belongs on each row.
    private func searchFamilyRow(_ market: SearchFuturesMarket, prominent: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(market.name)
                .font(.subheadline)
                .fontWeight(prominent ? .semibold : .regular)
                .foregroundStyle(prominent ? Color.primary : Color.secondary)
                .lineLimit(2)

            Spacer(minLength: 4)

            if let leader = SearchGrouping.leaderOutcome(market),
               let probability = leader.probability {
                HStack(spacing: 4) {
                    Text(leader.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Text(formatProbability(probability))
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                }
                .layoutPriority(1)
            } else if let count = market.outcomeCount {
                // No priced leader is a real state, not a blank: a market with 48
                // runners and no quote should say so rather than print nothing.
                Text("\(count) outcome\(count == 1 ? "" : "s")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .layoutPriority(1)
            }
        }
        .padding(.vertical, 2)
    }

    /// A tournament/ceremony concept — named as the thing, not as the market.
    private func searchConceptRow(_ concept: SearchEventConcept) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let domain = concept.domain {
                Text(domain.uppercased())
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Text(concept.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)
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
