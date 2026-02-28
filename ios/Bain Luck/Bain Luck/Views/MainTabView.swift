import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            FeedView()
                .tabItem {
                    Label("Feed", systemImage: "rectangle.stack.fill")
                }

            SearchPlaceholder()
                .tabItem {
                    Label("Search", systemImage: "magnifyingglass")
                }

            EIRankingsPlaceholder()
                .tabItem {
                    Label("EI Rankings", systemImage: "chart.bar.fill")
                }
        }
    }
}
