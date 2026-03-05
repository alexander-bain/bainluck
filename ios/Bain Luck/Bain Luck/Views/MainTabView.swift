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
                    Label("Feed", systemImage: "rectangle.stack.fill")
                }
                .tag(AppTab.feed)
                .badge(navCoordinator.liveGameCount > 0 ? "\(navCoordinator.liveGameCount) live" : nil)

            ExploreView()
                .tabItem {
                    Label("Explore", systemImage: "binoculars.fill")
                }
                .tag(AppTab.explore)

            SearchView()
                .tabItem {
                    Label("Search", systemImage: "magnifyingglass")
                }
                .tag(AppTab.search)

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
                        Label("Feed", systemImage: "rectangle.stack.fill")
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

                    Label("Explore", systemImage: "binoculars.fill")
                        .tag(AppTab.explore)

                    Label("Search", systemImage: "magnifyingglass")
                        .tag(AppTab.search)

                    Label("My Stuff", systemImage: "person.fill")
                        .tag(AppTab.myStuff)
                }

                Section("Explore") {
                    NavigationLink(value: Route.eiRankings) {
                        Label("EI Rankings", systemImage: "trophy.fill")
                    }
                    NavigationLink(value: Route.preferences) {
                        Label("Preferences", systemImage: "gearshape")
                    }
                }
            }
            .navigationTitle("🍀 Bain Luck")
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
                }
            }
        } detail: {
            switch navCoordinator.selectedTab {
            case .feed:
                FeedView()
            case .explore:
                ExploreView()
            case .search:
                SearchView()
            case .myStuff:
                MyStuffView()
            }
        }
    }
}
