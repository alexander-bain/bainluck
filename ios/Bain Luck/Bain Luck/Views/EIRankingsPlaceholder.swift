import SwiftUI

struct EIRankingsPlaceholder: View {
    var body: some View {
        ContentUnavailableView(
            "EI Rankings",
            systemImage: "chart.bar.fill",
            description: Text("The most exciting games, ranked by Excitement Index.")
        )
    }
}
