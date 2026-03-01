import SwiftUI

/// EI score + emoji in a colored pill. Three sizes: `.sm` for cards, `.md` for detail headers, `.lg` for hero sections.
struct EIBadgeView: View {
    let ei: EIData
    var size: BadgeSize = .sm

    enum BadgeSize {
        case sm, md, lg
    }

    var body: some View {
        if size == .lg {
            lgBadge
        } else {
            compactBadge
        }
    }

    // MARK: - Compact (sm/md)

    private var compactBadge: some View {
        HStack(spacing: size == .sm ? 2 : 4) {
            if let emoji = ei.emoji {
                Text(emoji)
                    .font(size == .sm ? .caption2 : .subheadline)
            }
            Text("\(displayScore)")
                .font(size == .sm ? .caption2 : .subheadline)
                .fontWeight(.semibold)
        }
        .padding(.horizontal, size == .sm ? 6 : 10)
        .padding(.vertical, size == .sm ? 2 : 4)
        .background(badgeColor.opacity(0.15))
        .foregroundStyle(badgeColor)
        .clipShape(Capsule())
    }

    // MARK: - Large (lg)

    private var lgBadge: some View {
        VStack(spacing: 4) {
            HStack(spacing: 6) {
                if let emoji = ei.emoji {
                    Text(emoji).font(.title3)
                }
                Text("\(displayScore) / 100")
                    .font(.title3)
                    .fontWeight(.bold)
                    .monospacedDigit()
            }
            if let label = ei.label {
                Text(label)
                    .font(.caption)
                    .fontWeight(.medium)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(
                colors: [badgeColor.opacity(0.15), badgeColor.opacity(0.05)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .foregroundStyle(badgeColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var displayScore: Int {
        ei.score ?? ei.rawScore ?? 0
    }

    private var badgeColor: Color {
        let s = displayScore
        if s >= 81 { return .red }
        if s >= 61 { return .orange }
        if s >= 41 { return Color(hex: "#d97706") } // amber
        return .gray
    }
}
