import SwiftUI

// MARK: - Sport Category Model

struct SportCategory: Identifiable, Hashable {
    let id: String
    let name: String
    let sportPrefixes: [String]
    let futuresCategories: [String]
    let route: Route?

    func matches(_ item: FeedItem) -> Bool {
        if id == "all" { return true }
        if let event = item.event, let sport = event.sport {
            if sportPrefixes.contains(where: { sport.hasPrefix($0) }) { return true }
        }
        if let futures = item.futures, let cat = futures.llmSportCategory?.lowercased() {
            if futuresCategories.contains(cat) { return true }
        }
        return false
    }
}

let sportCategories: [SportCategory] = [
    .init(id: "all", name: "All", sportPrefixes: [], futuresCategories: [], route: nil),
    .init(id: "basketball", name: "NBA", sportPrefixes: ["basketball"], futuresCategories: ["basketball"], route: .leagueGrid(slug: "nba")),
    .init(id: "football", name: "NFL", sportPrefixes: ["americanfootball"], futuresCategories: ["football"], route: .leagueGrid(slug: "nfl")),
    .init(id: "baseball", name: "MLB", sportPrefixes: ["baseball"], futuresCategories: ["baseball"], route: .leagueGrid(slug: "mlb")),
    .init(id: "hockey", name: "NHL", sportPrefixes: ["icehockey"], futuresCategories: ["hockey"], route: .leagueGrid(slug: "nhl")),
    .init(id: "soccer", name: "Soccer", sportPrefixes: ["soccer"], futuresCategories: ["soccer"], route: .leagueGrid(slug: "epl")),
    .init(id: "golf", name: "Golf", sportPrefixes: ["golf"], futuresCategories: ["golf"], route: .golfCategory),
    .init(id: "politics", name: "Politics", sportPrefixes: [], futuresCategories: ["politics"], route: .politics),
    .init(id: "entertainment", name: "Entmt", sportPrefixes: [], futuresCategories: ["entertainment"], route: .entertainment),
    .init(id: "economics", name: "Econ", sportPrefixes: [], futuresCategories: ["economics"], route: .economics),
    .init(id: "weather", name: "Weather", sportPrefixes: [], futuresCategories: ["weather"], route: .weather),
]

// MARK: - Filter Chips View

struct SportFilterChips: View {
    @Binding var selectedCategory: String
    var onNavigate: ((Route) -> Void)? = nil

    var body: some View {
        ZStack(alignment: .trailing) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(sportCategories) { category in
                        chipButton(category)
                    }
                    Spacer().frame(width: 20)
                }
                .padding(.horizontal)
            }

            LinearGradient(
                colors: [
                    Color.groupedBackground.opacity(0),
                    Color.groupedBackground,
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: 32)
            .allowsHitTesting(false)
        }
    }

    private func chipButton(_ category: SportCategory) -> some View {
        let isAll = category.id == "all"
        let isSelected = selectedCategory == category.id
        return Button {
            if isAll {
                withAnimation(.easeInOut(duration: 0.2)) {
                    selectedCategory = "all"
                }
            } else if let route = category.route {
                onNavigate?(route)
            }
        } label: {
            HStack(spacing: 4) {
                if !isAll {
                    Image(systemName: chipIcon(for: category.id))
                        .font(.system(size: 10))
                }
                Text(category.name)
                    .font(.caption)
                    .fontWeight(isSelected ? .semibold : .regular)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(isSelected ? Color.blue.opacity(0.15) : Color.secondary.opacity(0.08))
            .foregroundStyle(isSelected ? .blue : .primary)
            .clipShape(Capsule())
        }
    }

    private func chipIcon(for key: String) -> String {
        switch key {
        case "basketball": return "basketball.fill"
        case "football": return "football.fill"
        case "baseball": return "baseball.fill"
        case "hockey": return "hockey.puck.fill"
        case "soccer": return "soccerball"
        case "golf": return "figure.golf"
        case "politics": return "building.columns.fill"
        case "entertainment": return "film.fill"
        case "economics": return "chart.bar.fill"
        case "weather": return "cloud.sun.fill"
        default: return "sportscourt"
        }
    }
}
