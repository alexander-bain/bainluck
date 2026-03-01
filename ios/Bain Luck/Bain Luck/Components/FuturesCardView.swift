import SwiftUI

/// Futures market card showing top outcomes with probability bars.
struct FuturesCardView: View {
    let futures: FeedFuturesData

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Text(futures.llmSportCategory?.capitalized ?? "Futures")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                PinButton(type: "future", id: futures.id, compact: true)
                if let count = futures.sourceCount, count > 1 {
                    Text("\(count) sources")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                } else if let source = futures.source {
                    Text(source.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            // Market name
            Text(futures.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

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
                Text(formatProbability(prob))
                    .font(.caption)
                    .fontWeight(.semibold)
                    .monospacedDigit()
                    .foregroundStyle(.primary)
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
