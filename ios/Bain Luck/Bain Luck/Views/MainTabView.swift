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

            MyStuffView()
                .tabItem {
                    Label("My Stuff", systemImage: "person.fill")
                }
        }
    }
}
