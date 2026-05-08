import SwiftUI

struct SpecialEventMarketsView: View {
    let markets: [GameMarketOther]
    let eventStatus: String?

    private struct MarketCategory: Identifiable {
        let id: String
        let title: String
        let subtitle: String
        var items: [MarketItem]
    }

    private struct MarketItem: Identifiable {
        let id: String
        let name: String
        var outcomes: [OutcomeEntry]
    }

    private struct OutcomeEntry: Identifiable {
        var id: String { label }
        let label: String
        var prob: Double
        var sourceCount: Int
    }

    private static let categoryPatterns: [(pattern: String, category: String, subtitle: String)] = [
        ("first.*(?:score|td|touchdown|goal|basket)", "Game Props", "scoring & flow"),
        ("(?:halftime|half\\s*time|leader\\s*at)", "Game Props", "scoring & flow"),
        ("(?:overtime|OT\\b|extra\\s*time)", "Game Props", "scoring & flow"),
        ("(?:coin\\s*toss|gatorade|anthem|color)", "Novelty Props", "fun markets"),
        ("(?:mvp|most\\s*valuable)", "MVP", "game MVP probability"),
        ("(?:double\\s*double|triple\\s*double)", "Player Performance", "statistical milestones"),
        ("both\\s*teams?.*score", "Game Props", "scoring & flow"),
    ]

    private static func categorize(_ name: String) -> (category: String, subtitle: String) {
        let lower = name.lowercased()
        for (pattern, category, subtitle) in categoryPatterns {
            if lower.range(of: pattern, options: .regularExpression) != nil {
                return (category, subtitle)
            }
        }
        return ("Other Markets", "additional markets")
    }

    private static func isRedundantWithMarketMaps(_ m: GameMarketOther) -> Bool {
        let lower = m.marketName.lowercased()
        let outLower = m.outcomeName.lowercased()
        if lower.contains("spread") || lower.contains("handicap") { return true }
        if lower.contains("total") && (outLower.contains("over") || outLower.contains("under")) { return true }
        if lower.contains("moneyline") || lower.contains("winner") || lower.contains("match result") { return true }
        return false
    }

    private static func isWinProbabilityMarket(_ markets: [GameMarketOther]) -> Set<String> {
        var winProbMarkets: Set<String> = []
        let byMarket = Dictionary(grouping: markets) { $0.marketName }
        for (name, outcomes) in byMarket {
            if outcomes.count == 2 {
                let probs = outcomes.compactMap(\.probability)
                if probs.count == 2, abs(probs[0] + probs[1] - 1.0) < 0.1 {
                    winProbMarkets.insert(name)
                }
            }
        }
        return winProbMarkets
    }

    private var isGameFinished: Bool {
        eventStatus == "completed" || eventStatus == "closed"
    }

    private var categories: [MarketCategory] {
        let winProbNames = Self.isWinProbabilityMarket(markets)
        var filtered = markets.filter { !Self.isRedundantWithMarketMaps($0) && !winProbNames.contains($0.marketName) }
        // Hide resolved outcomes (100%/0%) for completed games
        if isGameFinished {
            filtered = filtered.filter { m in
                guard let p = m.probability else { return false }
                return p > 0.01 && p < 0.99
            }
        }
        guard !filtered.isEmpty else { return [] }

        var catMap: [String: MarketCategory] = [:]
        let categoryOrder = ["MVP", "Game Props", "Player Performance", "Novelty Props", "Other Markets"]

        for m in filtered {
            let name = m.marketName
            let (cat, sub) = Self.categorize(name)

            if catMap[cat] == nil {
                catMap[cat] = MarketCategory(id: cat, title: cat, subtitle: sub, items: [])
            }

            let itemIdx = catMap[cat]!.items.firstIndex(where: { $0.name == name })
            if let idx = itemIdx {
                let label = m.outcomeName
                if let oIdx = catMap[cat]!.items[idx].outcomes.firstIndex(where: { $0.label == label }) {
                    catMap[cat]!.items[idx].outcomes[oIdx].sourceCount += 1
                } else {
                    catMap[cat]!.items[idx].outcomes.append(
                        OutcomeEntry(label: label, prob: m.probability ?? 0, sourceCount: 1)
                    )
                }
            } else {
                catMap[cat]!.items.append(
                    MarketItem(id: "\(cat)-\(name)", name: name, outcomes: [
                        OutcomeEntry(label: m.outcomeName, prob: m.probability ?? 0, sourceCount: 1)
                    ])
                )
            }
        }

        return catMap.values
            .filter { !$0.items.isEmpty }
            .sorted { (categoryOrder.firstIndex(of: $0.title) ?? 99) < (categoryOrder.firstIndex(of: $1.title) ?? 99) }
    }

    var body: some View {
        let cats = categories
        if cats.isEmpty { EmptyView() }
        else {
            let totalItems = cats.reduce(0) { $0 + $1.items.count }
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Additional Markets")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text("\(totalItems) markets grouped by category")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                let columns = [GridItem(.flexible())]
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(cats) { cat in
                        VStack(alignment: .leading, spacing: 8) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(cat.title)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                Text(cat.subtitle)
                                    .font(.system(size: 10))
                                    .foregroundStyle(.tertiary)
                            }

                            ForEach(cat.items.prefix(5)) { item in
                                propMiniCard(item)
                            }
                            if cat.items.count > 5 {
                                Text("+\(cat.items.count - 5) more")
                                    .font(.system(size: 10))
                                    .foregroundStyle(.tertiary)
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .padding(12)
                        .background(Color.cardBackground)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.barTrack, lineWidth: 0.5)
                        )
                    }
                }
            }
        }
    }

    private func propMiniCard(_ item: MarketItem) -> some View {
        let sorted = item.outcomes.sorted { $0.prob > $1.prob }
        let maxSources = sorted.map(\.sourceCount).max() ?? 1

        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(item.name)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                Spacer()
                if maxSources > 1 {
                    Text("\(maxSources)x")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.blue)
                }
            }
            ForEach(sorted.indices, id: \.self) { i in
                let o = sorted[i]
                HStack(spacing: 6) {
                    Text(o.label)
                        .font(.system(size: 11))
                        .foregroundStyle(i == 0 ? .primary : .secondary)
                        .lineLimit(2)
                    Spacer()
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(i == 0 ? Color.purple.opacity(0.4) : Color.secondary.opacity(0.2))
                            .frame(width: geo.size.width * o.prob)
                    }
                    .frame(width: 60, height: 6)
                    Text("\(Int((o.prob * 100).rounded()))%")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .frame(width: 32, alignment: .trailing)
                }
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.barTrack.opacity(0.5), lineWidth: 0.5)
        )
    }
}
