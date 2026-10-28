import SwiftUI

/// Presentation only: the production card owns identity, admission and expiry.
/// No fallback to Detail.quoted, no inferred baseline and no local clock policy.
struct NBAScoringChanceComparison9483: View {
    let point: NBALadderCard9483.Point?
    let tint: Color
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 28

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let point {
                Text(point.label)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                if typeSize >= .xxxLarge {
                    VStack(alignment: .leading, spacing: 16) { readings(point) }
                } else {
                    HStack(alignment: .top, spacing: 20) { readings(point) }
                }
            } else {
                Text("Selected market unavailable")
                    .font(.headline)
                Text("Your selection is saved. No probability is available for it in this update.")
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.accessibilitySummary(for: point))
    }

    @ViewBuilder private func readings(_ point: NBALadderCard9483.Point) -> some View {
        reading("Pregame chance", symbol: "circle", value: point.chance)
        reading("Current chance", symbol: "circle.fill", value: point.now)
    }

    private func reading(_ label: String, symbol: String, value: Double?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(label, systemImage: symbol)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            if let value {
                Text(formatProbability(value))
                    .font(.system(size: chanceSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(tint)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Unavailable")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Shared spoken copy for the selected comparison and the chart's marks.
    /// Uses the existing probability formatter; this does not admit values.
    static func accessibilitySummary(for point: NBALadderCard9483.Point?) -> String {
        guard let point else {
            return "Selected market unavailable. Your selection is saved. No probability is available for it in this update."
        }
        let before = point.chance.map { formatProbability($0) } ?? "Unavailable"
        let current = point.now.map { formatProbability($0) } ?? "Unavailable"
        return "\(point.label). Pregame chance: \(before). Current chance: \(current)."
    }
}
