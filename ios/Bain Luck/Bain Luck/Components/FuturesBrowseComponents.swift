import Foundation
import SwiftUI

struct FuturesCategoryOption: Identifiable, Hashable {
    let tag: String
    let title: String
    let group: FuturesCategoryGroup
    let count: Int?

    var id: String { tag.isEmpty ? "all" : tag }

    var icon: String {
        switch tag.lowercased() {
        case "": return "square.grid.2x2.fill"
        case "basketball": return "basketball.fill"
        case "football": return "football.fill"
        case "baseball": return "baseball.fill"
        case "hockey": return "hockey.puck.fill"
        case "soccer": return "soccerball"
        case "golf": return "figure.golf"
        case "tennis": return "tennis.racket"
        case "mma", "boxing": return "figure.boxing"
        case "politics": return "building.columns.fill"
        case "economics": return "chart.line.uptrend.xyaxis"
        case "weather": return "cloud.sun.fill"
        case "entertainment": return "popcorn.fill"
        case "culture": return "sparkles"
        case "tech": return "cpu.fill"
        case "geopolitics": return "globe.americas.fill"
        case "cricket": return "figure.cricket"
        default: return "chart.bar.fill"
        }
    }

    var color: Color {
        switch tag.lowercased() {
        case "basketball": return .orange
        case "football": return .brown
        case "baseball": return .red
        case "hockey": return .cyan
        case "soccer": return .green
        case "golf": return .mint
        case "tennis": return .yellow
        case "mma", "boxing": return .red
        case "politics": return .indigo
        case "economics": return Color(hex: "#0d9488")
        case "weather": return .blue
        case "entertainment": return .pink
        case "culture": return .purple
        case "tech": return Color(hex: "#475569")
        case "geopolitics": return Color(hex: "#2563eb")
        case "cricket": return Color(hex: "#16a34a")
        default: return .accentColor
        }
    }

    static func makeOptions(from facets: [FacetTag]) -> [FuturesCategoryOption] {
        var options: [FuturesCategoryOption] = [
            .init(tag: "", title: "All", group: .featured, count: nil)
        ]

        options.append(contentsOf: facets.map { facet in
            let tag = facet.tag.lowercased()
            return FuturesCategoryOption(
                tag: facet.tag,
                title: title(for: tag),
                group: group(for: tag),
                count: facet.count
            )
        })

        return options.sorted { lhs, rhs in
            if lhs.group != rhs.group { return lhs.group.sortOrder < rhs.group.sortOrder }
            if lhs.tag.isEmpty { return true }
            if rhs.tag.isEmpty { return false }
            let lhsCount = lhs.count ?? 0
            let rhsCount = rhs.count ?? 0
            if lhsCount != rhsCount { return lhsCount > rhsCount }
            return lhs.title < rhs.title
        }
    }

    private static func title(for tag: String) -> String {
        // Acronym-safe: "pga_tour" -> "PGA Tour", "mma" -> "MMA" (no more "Pga").
        //
        // #5723: through the shared rule rather than straight to the raw-key
        // formatter under it. The two agree on all 77 production
        // `llm_sport_category` values, so no chip's text moves today — the
        // point is that the chip and the row it filters cannot drift apart
        // later, which is how this label came to have four spellings.
        sportCategoryDisplayName(tag)
    }

    private static func group(for tag: String) -> FuturesCategoryGroup {
        switch tag {
        case "politics", "economics", "weather", "entertainment", "culture", "tech", "geopolitics":
            return .world
        case "basketball", "football", "baseball", "hockey", "soccer", "golf", "tennis", "mma", "boxing", "cricket":
            return .sports
        default:
            return .other
        }
    }
}

enum FuturesCategoryGroup: String, CaseIterable, Hashable {
    case featured = "Featured"
    case sports = "Sports"
    case world = "World"
    case other = "More"

    var sortOrder: Int {
        switch self {
        case .featured: return 0
        case .sports: return 1
        case .world: return 2
        case .other: return 3
        }
    }
}

struct FuturesCategoryRail: View {
    let options: [FuturesCategoryOption]
    let selectedTag: String
    let onSelect: (String) -> Void

    private var groups: [FuturesCategoryGroup] {
        FuturesCategoryGroup.allCases.filter { group in
            options.contains { $0.group == group }
        }
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 16) {
                ForEach(groups, id: \.self) { group in
                    VStack(alignment: .leading, spacing: 7) {
                        Text(group.rawValue)
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)

                        HStack(spacing: 8) {
                            ForEach(options.filter { $0.group == group }) { option in
                                FuturesCategoryChip(
                                    option: option,
                                    isSelected: selectedTag == option.tag,
                                    action: { onSelect(option.tag) }
                                )
                            }
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 10)
        }
        .background(Color.systemBackground)
    }
}

private struct FuturesCategoryChip: View {
    let option: FuturesCategoryOption
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: option.icon)
                    .font(.system(size: 12, weight: .semibold))
                    .frame(width: 14)

                Text(option.title)
                    .font(.caption)
                    .fontWeight(isSelected ? .semibold : .medium)
                    .lineLimit(1)

                if let count = option.count, !isSelected {
                    Text("\(count)")
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 11)
            .frame(height: 32)
            .background(chipBackground)
            .foregroundStyle(isSelected ? option.color : .primary)
            .clipShape(Capsule())
            .overlay(
                Capsule()
                    .stroke(isSelected ? option.color.opacity(0.45) : Color.primary.opacity(0.08), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel(option.count.map { "\(option.title), \($0) markets" } ?? option.title)
        .accessibilityValue(isSelected ? "Selected" : "")
    }

    private var chipBackground: Color {
        isSelected ? option.color.opacity(0.14) : Color.cardBackgroundDark
    }
}

struct FuturesBrowseMarketRow: View {
    let market: FacetedFuturesMarket

    private var category: FuturesCategoryOption {
        FuturesCategoryOption(
            tag: market.llmSportCategory ?? "",
            // #5723: the shared rule rather than the raw-key formatter under
            // it, so a league key resolves ("americanfootball_nfl" -> "NFL",
            // not "Americanfootball Nfl") and Browse agrees with every other
            // surface. `sportCategoryDisplayName` delegates here for keys its
            // maps do not cover, so nothing this row printed correctly moves.
            title: market.llmSportCategory.map(sportCategoryDisplayName) ?? "Futures",
            group: .other,
            count: nil
        )
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            thumbnail

            VStack(alignment: .leading, spacing: 8) {
                header

                Text(market.name)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                if let hook = market.hookDescription, !hook.isEmpty {
                    Text(hook)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                // #5872 — A ROW WITH NO PRICE SAYS NOTHING ABOUT WHY.
                //
                // This `if` used to have an `else` that drew "Outcomes update
                // when market prices are available" in the body of every
                // unpriced card. That is a sentence explaining an emptiness,
                // which is notice 34 / D102: "If a number cannot be shown
                // honestly, leave the space empty; do not explain the emptiness
                // in a paragraph." Photographed on production 2026-09-13 09:19Z
                // (`artifacts-native-142/futureslist.png`) directly above a row
                // that HAD a price and simply showed it — "Christian Langmo
                // 51%" — which is the contrast that makes the note read as an
                // apology rather than as information.
                //
                // Not rare, either: `GET /api/futures/faceted?page=1&per_page=20`,
                // the app's own query, returned 20 of 20 rows with no
                // `top_outcomes` at 09:20Z, so it was most of the first screen.
                //
                // The string existed only here — no web twin, no backend copy —
                // so the web list has always drawn nothing in this slot and this
                // only brings the phone into line with it.
                if let outcomes = market.topOutcomes, !outcomes.isEmpty {
                    VStack(spacing: 5) {
                        ForEach(Array(outcomes.prefix(3))) { outcome in
                            FuturesBrowseOutcomeRow(outcome: outcome, tint: category.color)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    private var header: some View {
        HStack(spacing: 6) {
            Label(category.title, systemImage: category.icon)
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundStyle(category.color)
                .lineLimit(1)

            if let source = market.source {
                FuturesSourceBadge(source: source)
            }

            if let resolution = formattedResolutionDate {
                Text(resolution)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            PinButton(type: "future", id: market.id, compact: true)
        }
    }

    @ViewBuilder
    private var thumbnail: some View {
        if let imageUrl = market.imageUrl, let url = URL(string: imageUrl) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                default:
                    thumbnailFallback
                }
            }
            .frame(width: 56, height: 56)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        } else {
            thumbnailFallback
                .frame(width: 56, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private var thumbnailFallback: some View {
        ZStack {
            category.color.opacity(0.12)
            Image(systemName: category.icon)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(category.color)
        }
        .frame(width: 56, height: 56)
    }

    private var formattedResolutionDate: String? {
        guard let raw = market.resolutionDate else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: raw) ?? {
            formatter.formatOptions = [.withInternetDateTime]
            return formatter.date(from: raw)
        }()
        guard let date else { return nil }

        let output = DateFormatter()
        output.dateFormat = "MMM d"
        return output.string(from: date)
    }
}

private struct FuturesBrowseOutcomeRow: View {
    let outcome: FacetedFuturesOutcome
    let tint: Color

    private var probability: Double {
        min(max(outcome.probability ?? 0, 0), 1)
    }

    var body: some View {
        HStack(spacing: 8) {
            Text(outcome.name)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(1)

            Spacer(minLength: 8)

            movementIndicator

            Text(outcome.probability.map { formatProbability($0) } ?? "--")
                .font(.caption)
                .fontWeight(.semibold)
                .monospacedDigit()
                .foregroundStyle(.primary)
                .frame(width: 42, alignment: .trailing)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 7)
        .background(
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 5)
                        .fill(Color.primary.opacity(0.035))
                    RoundedRectangle(cornerRadius: 5)
                        .fill(tint.opacity(0.11))
                        .frame(width: geo.size.width * probability)
                }
            }
        )
    }

    @ViewBuilder
    private var movementIndicator: some View {
        if let movement = outcome.movement, abs(movement) >= 0.005 {
            HStack(spacing: 2) {
                Image(systemName: movement > 0 ? "arrow.up" : "arrow.down")
                    .font(.system(size: 8, weight: .bold))
                Text(formatProbability(abs(movement)))
                    .font(.system(size: 10, weight: .semibold, design: .rounded))
                    .monospacedDigit()
            }
            .foregroundStyle(movement > 0 ? Color.green : Color.red)
        }
    }
}

private struct FuturesSourceBadge: View {
    let source: String

    private var label: String? { SourceLabels.label(for: source) }

    private var color: Color {
        switch source {
        case "polymarket": return .blue
        case "kalshi": return Color(hex: "#22c55e")
        case "odds_api": return Color(hex: "#d97706")
        default: return .gray
        }
    }

    var body: some View {
        if let label {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(color)
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(color.opacity(0.12))
                .clipShape(Capsule())
        }
    }
}

struct FuturesBrowseLoadingView: View {
    var body: some View {
        List {
            Section {
                ForEach(0..<8, id: \.self) { _ in
                    HStack(alignment: .top, spacing: 12) {
                        SkeletonShape(width: 56, height: 56, cornerRadius: 8)
                        VStack(alignment: .leading, spacing: 9) {
                            HStack {
                                SkeletonShape(width: 88, height: 10)
                                SkeletonShape(width: 54, height: 10)
                            }
                            SkeletonShape(height: 15)
                            SkeletonShape(width: 220, height: 15)
                            SkeletonShape(height: 22, cornerRadius: 5)
                            SkeletonShape(height: 22, cornerRadius: 5)
                        }
                    }
                    .padding(.vertical, 6)
                }
            } header: {
                Text("Loading markets")
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .disabled(true)
        .shimmer()
    }
}

struct FuturesBrowseStateView: View {
    let title: String
    let message: String
    let systemImage: String
    let actionTitle: String?
    let action: (() -> Void)?

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: systemImage)
        } description: {
            Text(message)
        } actions: {
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}
