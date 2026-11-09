import SwiftUI

/// Futures market card showing top outcomes with probability bars.
struct FuturesCardView: View {
    let futures: FeedFuturesData

    #if os(macOS)
    @State private var isHovered = false
    #endif

    /// #12312 — at accessibility sizes the market and outcome names wrap
    /// instead of stopping at "San Franc…" / "Chicago B…" (Bears or Bulls?).
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// #12312 — the rank (and its column, on the same curve so "#12" keeps
    /// fitting) and the movement mark: each exactly its old point size at the
    /// default text size, growing with it.
    @ScaledMetric(relativeTo: .caption2) private var rankSize: CGFloat = 10
    @ScaledMetric(relativeTo: .caption2) private var rankColumnWidth: CGFloat = 20
    @ScaledMetric(relativeTo: .caption2) private var movementArrowSize: CGFloat = 8
    @ScaledMetric(relativeTo: .caption2) private var movementSize: CGFloat = 9

    private var namesWrap: Bool { dynamicTypeSize.isAccessibilitySize }

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
                if let count = futures.sourceCount, count > 1 {
                    Text("\(count) sources")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                } else if let source = SourceLabels.label(for: futures.source) {
                    Text(source)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            // Market name
            Text(futures.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(namesWrap ? nil : 2)

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

    /// #12312 — at accessibility sizes the number moves under the name: beside
    /// it, the name's column broke "San Francisco" as "Francis- / co".
    private func outcomeRow(_ outcome: FeedFuturesOutcome) -> some View {
        HStack(alignment: namesWrap ? .firstTextBaseline : .center, spacing: 8) {
            if let rank = outcome.rank {
                Text("#\(rank)")
                    .font(.system(size: rankSize, weight: .medium, design: .rounded))
                    .foregroundStyle(.tertiary)
                    .frame(width: rankColumnWidth, alignment: .trailing)
            }
            if namesWrap {
                VStack(alignment: .leading, spacing: 2) {
                    // Its full height: without it the AX5 after-shot of the
                    // Sports feed read "San Francisc…" on one line.
                    Text(outcome.name)
                        .font(.caption)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 8) {
                        probabilityText(outcome)
                        movementIndicator(outcome.movement)
                    }
                }
                Spacer(minLength: 0)
            } else {
                Text(outcome.name)
                    .font(.caption)
                    .lineLimit(1)
                Spacer()
                movementIndicator(outcome.movement)
                probabilityText(outcome)
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
    private func probabilityText(_ outcome: FeedFuturesOutcome) -> some View {
        if let prob = outcome.probability {
            Text(formatProbability(prob, renderedPercent: outcome.renderedPercent))
                .font(.caption)
                .fontWeight(.semibold)
                .monospacedDigit()
                .foregroundStyle(.primary)
        }
    }

    @ViewBuilder
    private func movementIndicator(_ movement: Double?) -> some View {
        if let m = movement, abs(m) >= 0.005 {
            HStack(spacing: 1) {
                Image(systemName: m > 0 ? "arrow.up" : "arrow.down")
                    .font(.system(size: movementArrowSize))
                Text(formatProbability(abs(m)))
                    .font(.system(size: movementSize))
            }
            .foregroundStyle(m > 0 ? .green : .red)
        }
    }
}
