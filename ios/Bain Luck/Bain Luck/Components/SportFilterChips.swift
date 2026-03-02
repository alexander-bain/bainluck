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
    var onCategoryLongPress: ((SportCategory) -> Void)? = nil

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(sportCategories) { category in
                    chipButton(category)
                }
            }
            .padding(.horizontal)
        }
    }

    private func chipButton(_ category: SportCategory) -> some View {
        let isSelected = selectedCategory == category.id
        return Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedCategory = category.id
            }
        } label: {
            Text(category.name)
                .font(.caption)
                .fontWeight(isSelected ? .semibold : .regular)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.blue.opacity(0.15) : Color.cardBackground)
                .foregroundStyle(isSelected ? .blue : .primary)
                .clipShape(Capsule())
        }
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.5).onEnded { _ in
                if category.id != "all" {
                    onCategoryLongPress?(category)
                }
            }
        )
    }
}
