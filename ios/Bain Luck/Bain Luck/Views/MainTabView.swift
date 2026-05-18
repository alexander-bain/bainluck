import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
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
                    sidebarLabel("Weather", systemImage: "cloud.sun.fill")
                        .tag(AppTab.weather)
                    sidebarLabel("Economics", systemImage: "chart.bar.fill")
                        .tag(AppTab.economics)
                    sidebarLabel("Politics", systemImage: "building.columns.fill")
                        .tag(AppTab.politics)
                    sidebarLabel("Entertainment", systemImage: "film.fill")
                        .tag(AppTab.entertainment)
                    sidebarLabel("Preferences", systemImage: "gearshape")
                        .tag(AppTab.preferences)
                    sidebarLabel("Calibration", systemImage: "chart.dots.scatter")
                        .tag(AppTab.calibration)
                }
            }
            .navigationTitle("")
            .toolbar {
                ToolbarItem(placement: .principal) {
                    HStack(spacing: 6) {
                        Text("🍀")
                        Text("Bain Luck")
                            .font(.headline.weight(.semibold))
                    }
                    .lineLimit(1)
                }
            }
            .navigationSplitViewColumnWidth(min: 190, ideal: 220, max: 260)
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
                NavigationStack { FuturesListView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            case .weather:
                NavigationStack { WeatherView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            case .economics:
                NavigationStack { EconomicsView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            case .politics:
                NavigationStack { PoliticsView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            case .entertainment:
                NavigationStack { EntertainmentView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            case .preferences:
                NavigationStack { PreferencesView() }
            case .calibration:
                NavigationStack { CalibrationView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
            }
        }
    }

    private func sidebarLabel(_ title: String, systemImage: String) -> some View {
        Label {
            Text(title)
                .lineLimit(1)
                .minimumScaleFactor(0.82)
        } icon: {
            Image(systemName: systemImage)
        }
    }
}
