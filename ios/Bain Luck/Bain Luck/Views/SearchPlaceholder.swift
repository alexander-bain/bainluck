import SwiftUI

struct SearchPlaceholder: View {
    var body: some View {
        ContentUnavailableView(
            "Search",
            systemImage: "magnifyingglass",
            description: Text("Search for teams, games, and futures markets.")
        )
    }
}
