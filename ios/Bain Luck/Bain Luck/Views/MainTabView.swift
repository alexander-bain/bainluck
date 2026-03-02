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
                Label("Feed", systemImage: "rectangle.stack.fill")
                    .tag(AppTab.feed)
                Label("Search", systemImage: "magnifyingglass")
                    .tag(AppTab.search)
                Label("My Stuff", systemImage: "person.fill")
                    .tag(AppTab.myStuff)
            }
            .navigationTitle("Bain Luck")
        } detail: {
            switch navCoordinator.selectedTab {
            case .feed:
                FeedView()
            case .search:
                SearchView()
            case .myStuff:
                MyStuffView()
            }
        }
    }
}
