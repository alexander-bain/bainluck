import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            FeedView()
                .tabItem {
                    Label("Feed", systemImage: "rectangle.stack.fill")
                }

            SearchView()
                .tabItem {
                    Label("Search", systemImage: "magnifyingglass")
                }

            EIRankingsView()
                .tabItem {
                    Label("EI Rankings", systemImage: "chart.bar.fill")
                }
        }
    }
}
