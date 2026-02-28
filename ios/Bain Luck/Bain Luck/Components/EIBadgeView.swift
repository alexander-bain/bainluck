import SwiftUI

/// EI score + emoji in a colored pill. Two sizes: `.sm` for cards, `.md` for detail headers.
struct EIBadgeView: View {
    let ei: EIData
    var size: BadgeSize = .sm

    enum BadgeSize {
        case sm, md
    }

    var body: some View {
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
