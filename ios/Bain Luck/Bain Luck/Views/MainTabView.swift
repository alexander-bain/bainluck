import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var navCoordinator: NavigationCoordinator

    var body: some View {
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
}
