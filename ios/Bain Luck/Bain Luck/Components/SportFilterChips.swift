import SwiftUI

// MARK: - Sport Category Model

struct SportCategory: Identifiable, Hashable {
    let id: String
    let name: String
    /// Sport key prefixes for matching events (e.g., "basketball" matches "basketball_nba")
    let sportPrefixes: [String]
    /// LLM categories for matching futures (e.g., "basketball", "politics")
    let futuresCategories: [String]

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
    .init(id: "all", name: "All", sportPrefixes: [], futuresCategories: []),
    .init(id: "basketball", name: "Basketball", sportPrefixes: ["basketball"], futuresCategories: ["basketball"]),
    .init(id: "football", name: "Football", sportPrefixes: ["americanfootball"], futuresCategories: ["football"]),
    .init(id: "baseball", name: "Baseball", sportPrefixes: ["baseball"], futuresCategories: ["baseball"]),
    .init(id: "hockey", name: "Hockey", sportPrefixes: ["icehockey"], futuresCategories: ["hockey"]),
    .init(id: "soccer", name: "Soccer", sportPrefixes: ["soccer"], futuresCategories: ["soccer"]),
    .init(id: "golf", name: "Golf", sportPrefixes: ["golf"], futuresCategories: ["golf"]),
    .init(id: "tennis", name: "Tennis", sportPrefixes: ["tennis"], futuresCategories: ["tennis"]),
    .init(id: "mma", name: "MMA", sportPrefixes: ["mma"], futuresCategories: ["mma", "boxing"]),
    .init(id: "politics", name: "Politics", sportPrefixes: [], futuresCategories: ["politics"]),
    .init(id: "entertainment", name: "Entertainment", sportPrefixes: [], futuresCategories: ["entertainment"]),
    .init(id: "crypto", name: "Crypto", sportPrefixes: [], futuresCategories: ["crypto"]),
]

// MARK: - Filter Chips View

struct SportFilterChips: View {
    @Binding var selectedCategory: String
    var onCategoryTap: ((SportCategory) -> Void)? = nil

    var body: some View {
        ZStack(alignment: .trailing) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(sportCategories) { category in
                        chipButton(category)
                    }
                    // Trailing spacer so content doesn't hide under gradient
                    Spacer().frame(width: 20)
                }
                .padding(.horizontal)
            }

            // Fade hint showing more chips to the right
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
                // "All" always acts as a filter reset
                withAnimation(.easeInOut(duration: 0.2)) {
                    selectedCategory = "all"
                }
            } else {
                // Other categories navigate to their detail page
                onCategoryTap?(category)
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
            .background(isSelected ? Color.blue.opacity(0.15) : Color.cardBackground)
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
        case "tennis": return "tennis.racket"
        case "mma": return "figure.boxing"
        case "politics": return "building.columns.fill"
        case "entertainment": return "star.fill"
        case "crypto": return "bitcoinsign.circle.fill"
        default: return "sportscourt"
        }
    }
}
