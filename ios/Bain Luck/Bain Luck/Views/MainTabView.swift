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
            DiscoverView()
                .tabItem {
                    Label("Discover", systemImage: "safari")
                }
                .tag(AppTab.discover)

            FeedView()
                .tabItem {
                    Label("Sports", systemImage: "rectangle.stack.fill")
                }
                .tag(AppTab.feed)
                .badge(navCoordinator.liveGameCount > 0 ? "\(navCoordinator.liveGameCount) live" : nil)

            LeaguesView()
                .tabItem {
                    Label("Browse", systemImage: "square.grid.2x2")
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
                    Label("Discover", systemImage: "safari")
                        .tag(AppTab.discover)

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

                    Label("Browse", systemImage: "square.grid.2x2")
                        .tag(AppTab.leagues)

                    Label("Search", systemImage: "magnifyingglass")
                        .tag(AppTab.search)

                    Label("My Stuff", systemImage: "person.fill")
                        .tag(AppTab.myStuff)
                }

                Section("Quick Links") {
                    Label("Futures", systemImage: "chart.line.uptrend.xyaxis")
                        .tag(AppTab.futures)
                    Label("Weather", systemImage: "cloud.sun.fill")
                        .tag(AppTab.weather)
                    Label("Economics", systemImage: "chart.bar.fill")
                        .tag(AppTab.economics)
                    Label("Politics", systemImage: "building.columns.fill")
                        .tag(AppTab.politics)
                    Label("Entertainment", systemImage: "film.fill")
                        .tag(AppTab.entertainment)
                    Label("Preferences", systemImage: "gearshape")
                        .tag(AppTab.preferences)
                }
            }
            .navigationTitle("🍀 Bain Luck")
            .navigationSplitViewColumnWidth(min: 160, ideal: 200, max: 260)
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
            case .futures:
                NavigationStack { FuturesListView() }
            case .weather:
                NavigationStack { WeatherView() }
            case .economics:
                NavigationStack { EconomicsView() }
            case .politics:
                NavigationStack { PoliticsView() }
            case .entertainment:
                NavigationStack { EntertainmentView() }
            case .preferences:
                NavigationStack { PreferencesView() }
            }
        }
    }
}
