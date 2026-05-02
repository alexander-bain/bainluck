import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var columnVisibility = NavigationSplitViewVisibility.automatic

    var body: some View {
        if sizeClass == .regular {
            iPadLayout
        } else {
            iPhoneLayout
        }
    }

    // MARK: - iPhone (Compact)

    private var iPhoneLayout: some View {
        TabView(selection: $navCoordinator.selectedTab) {
            FeedView()
                .tabItem {
                    Label("Sports", systemImage: "rectangle.stack.fill")
                }
                .tag(AppTab.feed)
                .badge(navCoordinator.liveGameCount > 0 ? "\(navCoordinator.liveGameCount) live" : nil)

            NavigationStack {
                DiscoverView()
                    .navigationDestination(for: Route.self) { route in
                        switch route {
                        case .eventDetail(let id): EventDetailView(eventId: id)
                        case .futuresDetail(let id): FuturesDetailView(marketId: id)
                        case .predictionStats: PredictionStatsView()
                        default: EmptyView()
                        }
                    }
            }
            .tabItem {
                Label("Discover", systemImage: "safari")
            }
            .tag(AppTab.discover)

            LeaguesView()
                .tabItem {
                    Label("Leagues", systemImage: "trophy.fill")
                }
                .tag(AppTab.leagues)

            SearchView()
                .tabItem {
                    Label("Search", systemImage: "magnifyingglass")
                }
                .tag(AppTab.search)
                #if os(macOS)
                .keyboardShortcut("k", modifiers: .command)
                #endif

            MyStuffView()
                .tabItem {
                    Label("My Stuff", systemImage: "person.fill")
                }
                .tag(AppTab.myStuff)
        }
    }

    // MARK: - iPad (Regular)

    /// Wraps `selectedTab` as optional for `List(selection:)` compatibility.
    private var tabSelection: Binding<AppTab?> {
        Binding(
            get: { navCoordinator.selectedTab },
            set: { if let tab = $0 { navCoordinator.selectedTab = tab } }
        )
    }

    private var iPadLayout: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            List(selection: tabSelection) {
                Section {
                    HStack {
                        Label("Sports", systemImage: "rectangle.stack.fill")
                        Spacer()
                        if navCoordinator.liveGameCount > 0 {
                            Text("\(navCoordinator.liveGameCount) live")
                                .font(.caption2)
                                .fontWeight(.semibold)
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.red)
                                .clipShape(Capsule())
                        }
                    }
                    .tag(AppTab.feed)

                    Label("Discover", systemImage: "safari")
                        .tag(AppTab.discover)

                    Label("Leagues", systemImage: "trophy.fill")
                        .tag(AppTab.leagues)

                    Label("Search", systemImage: "magnifyingglass")
                        .tag(AppTab.search)

                    Label("My Stuff", systemImage: "person.fill")
                        .tag(AppTab.myStuff)
                }

                Section("Quick Links") {
                    NavigationLink(value: Route.futuresList) {
                        Label("Futures", systemImage: "chart.line.uptrend.xyaxis")
                    }
                    NavigationLink(value: Route.eiRankings) {
                        Label("EI Rankings", systemImage: "trophy.fill")
                    }
                    NavigationLink(value: Route.preferences) {
                        Label("Preferences", systemImage: "gearshape")
                    }
                }
            }
            .navigationTitle("🍀 Bain Luck")
            .navigationSplitViewColumnWidth(min: 160, ideal: 200, max: 260)
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
                    GolfCategoryView()
                case .golfLeaderboard:
                    MastersLiveView()
                case .golfTournament(_, let name):
                    SportCategoryView(categoryKey: "golf", categoryName: name)
                case .futuresList:
                    FuturesListView()
                case .teamDetail(_):
                    Text("Team")
                case .predictionStats:
                    PredictionStatsView()
                }
            }
        } detail: {
            switch navCoordinator.selectedTab {
            case .feed:
                FeedView()
            case .discover:
                DiscoverView()
            case .leagues:
                LeaguesView()
            case .search:
                SearchView()
            case .myStuff:
                MyStuffView()
            }
        }
    }
}
