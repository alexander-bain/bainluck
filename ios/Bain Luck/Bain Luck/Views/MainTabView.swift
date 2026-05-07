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
                        case .weather: WeatherView()
                        case .economics: EconomicsView()
                        case .about: Text("About")
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
            set: { newTab in
                guard let tab = newTab else { return }
                DispatchQueue.main.async { navCoordinator.selectedTab = tab }
            }
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
                    NavigationLink(value: Route.weather) {
                        Label("Weather", systemImage: "cloud.sun.fill")
                    }
                    NavigationLink(value: Route.economics) {
                        Label("Economics", systemImage: "chart.bar.fill")
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
                case .preferences:
                    PreferencesView()
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                case .leagueGrid(let slug):
                    LeagueGridView(slug: slug)
                case .golfCategory:
                    GolfCategoryView()
                case .golfLeaderboard:
                    GolfCategoryView()
                case .golfTournament(_, let name):
                    SportCategoryView(categoryKey: "golf", categoryName: name)
                case .futuresList:
                    FuturesListView()
                case .teamDetail(_):
                    Text("Team")
                case .predictionStats:
                    PredictionStatsView()
                case .weather:
                    WeatherView()
                case .economics:
                    EconomicsView()
                case .eiRankings:
                    Text("EI Rankings")
                case .about:
                    Text("About")
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
