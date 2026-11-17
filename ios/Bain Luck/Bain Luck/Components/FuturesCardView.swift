import SwiftUI

/// Futures market card showing top outcomes with probability bars.
struct FuturesCardView: View {
    let futures: FeedFuturesData

    #if os(macOS)
    @State private var isHovered = false
    #endif

    /// #11920 / Ruling 141: collection & list cards never print raw `"both"` or venue names
    /// (`"Kalshi"` / `"Polymarket"`) on the card face.
    /// - When the server sends `source_mark` (`#12581`), the `ⓘ` ring beside the probability
    ///   replaces the header badge and opens `"Where this number comes from"` on tap.
    /// - While `source_mark` is absent, multi-source markets (`sourceCount > 1` or `source == "both"`)
    ///   say the source count in words (`"2 sources"`, matching web `FeedCard.tsx`), and non-venue
    ///   model/sportsbook labels still resolve through `SourceLabels.label(for:)`.
    static func cardFaceSourceBadge(for futures: FeedFuturesData) -> String? {
        if futures.sourceMark?.draws == true {
            return nil
        }
        if futures.topOutcomes?.contains(where: { $0.sourceMark?.draws == true }) == true {
            return nil
        }
        if let count = futures.sourceCount, count > 1 {
            return "\(count) sources"
        }
        let raw = futures.source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if raw == "both" {
            return "2 sources"
        }
        if raw == "kalshi" || raw == "polymarket" {
            return nil
        }
        return SourceLabels.label(for: futures.source)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                // #1938 (Alex, bug report 145): `.capitalized` rendered the raw
                // key "mma" as "Mma". `sportCategoryDisplayName` is the shared
                // resolver the Discover cards already use — it knows the league
                // acronyms AND the non-sport Discover categories, and falls back
                // to acronym-aware title casing rather than to `.capitalized`.
                Text(futures.llmSportCategory.map(sportCategoryDisplayName) ?? "Futures")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                // #490: confidence signal (1-3 bars) — renders nothing when absent.
                SignalBarsView(tier: futures.confidenceTier)
                Spacer()
                PinButton(type: "future", id: futures.id, compact: true)
                if let badge = Self.cardFaceSourceBadge(for: futures) {
                    Text(badge)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            // Market name
            Text(futures.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)

            // Top outcomes
            if let outcomes = futures.topOutcomes?.prefix(3) {
                VStack(spacing: 4) {
                    ForEach(Array(outcomes)) { outcome in
                        outcomeRow(outcome)
                    }
                }
            }

            // Remaining count
            if let total = futures.outcomeCount,
               let shown = futures.topOutcomes?.count,
               total > shown {
                Text("+\(total - shown) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        #if os(macOS)
        .background(isHovered ? Color.primary.opacity(0.04) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .onHover { isHovered = $0 }
        #endif
    }

    private func outcomeRow(_ outcome: FeedFuturesOutcome) -> some View {
        HStack(spacing: 8) {
            if let rank = outcome.rank {
                Text("#\(rank)")
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundStyle(.tertiary)
                    .frame(width: 20, alignment: .trailing)
            }
            Text(outcome.name)
                .font(.caption)
                .lineLimit(1)
            Spacer()
            movementIndicator(outcome.movement)
            if let prob = outcome.probability {
                HStack(spacing: 2) {
                    Text(formatProbability(prob, renderedPercent: outcome.renderedPercent))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                        .foregroundStyle(.primary)
                    if let mark = SourceMarkButton(outcome.sourceMark ?? futures.sourceMark, number: prob, numberSize: 12, compactRow: true) {
                        mark
                    }
                }
            }
        }
        .padding(.vertical, 2)
        .background(
            GeometryReader { geo in
                if let prob = outcome.probability {
                    Rectangle()
                        .fill(categoryColor.opacity(0.06))
                        .frame(width: geo.size.width * min(1, prob))
                }
            }
        )
    }

    private var categoryColor: Color {
        switch futures.llmSportCategory?.lowercased() {
        case "basketball": return .orange
        case "football": return .brown
        case "baseball": return .red
        case "hockey": return .cyan
        case "soccer": return .green
        case "golf": return .mint
        case "tennis": return .yellow
        case "mma", "boxing": return .red
        case "politics": return .purple
        case "entertainment": return .pink
        case "crypto": return Color(hex: "#f59e0b")
        default: return .blue
        }
    }

    @ViewBuilder
    private func movementIndicator(_ movement: Double?) -> some View {
        if let m = movement, abs(m) >= 0.005 {
            HStack(spacing: 1) {
                Image(systemName: m > 0 ? "arrow.up" : "arrow.down")
                    .font(.system(size: 8))
                Text(formatProbability(abs(m)))
                    .font(.system(size: 9))
            }
            .foregroundStyle(m > 0 ? .green : .red)
        }
    }
}
